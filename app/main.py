"""Azure Cost Optimizer — Production API v5.0

Includes:
  - Full Cost Management API (v2024-08-01)
  - All resource type endpoints (Compute, AKS, Storage, Network, DB, Security)
  - Optimization Engine with configurable rules + profiles
  - Engine config CRUD (enable/disable rules, override thresholds per profile)
  - Finding history + remediation status tracking
"""
# ── stdlib ────────────────────────────────────────────────────────────────────
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any, Optional, Union

# ── third-party ───────────────────────────────────────────────────────────────
import structlog
from fastapi import (
    BackgroundTasks,
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Path,
    Query,
    Request,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

# ── application ───────────────────────────────────────────────────────────────
from app.__version__ import __version__
from app.middleware.dynamic_cors import DynamicCORSMiddleware
from app.middleware.app_auth import AppAuthMiddleware
from app.http_cache import cache_control_middleware
from app.runtime_config import invalidate_runtime_config, get_runtime_status
from app.azure_cost import AzureCostClient, CostExportNotConfiguredError, CostExportReadError
from app.cost_db import (
    cost_by_resource_from_db,
    cost_by_resource_type_from_db,
    cost_by_service_from_db,
    cost_summary_from_db,
    daily_cost_response_from_db,
    daily_cost_by_resource_group_from_db,
    empty_cost_by_resource_response,
    empty_cost_by_service_response,
    empty_cost_summary_response,
    empty_daily_cost_response,
    get_latest_cost_changes,
    mtd_period_for_timeframe,
    _date_range_for_timeframe,
    resource_cost_map_from_db,
)
from app.cost_timeframes import list_timeframe_catalog
from app.cost_live_query import (
    query_cost_by_resource_live,
    query_cost_by_service_live,
    query_cost_summary_live,
    query_daily_costs_live,
)
from app.cost_resolve import live_range_kw, resolve_cost_db_then_live
from app.dashboard import (
    get_dashboard_overview,
    get_resource_detail,
    get_sync_status,
    get_top_spend,
    list_advisor_recommendations,
    list_budgets_from_db,
    list_monitor_alert_resources,
    list_underutil_outliers,
)
from app.azure_resources import AzureResourcesClient
from app.vm_utils import filter_standalone_vms
from app.http_client import AzureAPIError
from app.database import get_db, engine, migrate_schema
from app.settings import get_settings
from app.logging_config import configure_logging
from app.validators import (
    ensure_subscription_known,
    validate_subscription_id,
    validate_optional_subscription_id,
    validate_finding_status,
)
from app.models import (
    Base,
    OptimizationRun,
    OptimizationFinding,
    AnalysisJob,
)
from app.billed_resources import list_billed_resources_page
from app.resource_store import (
    get_resources_db,
    get_resources_db_page,
    get_resource_counts,
    list_all_resources_db,
    get_resources_by_type_prefix_db,
    get_aks_clusters_db,
    apply_costs_to_resources,
)
from app.auth import get_token as get_arm_token
from app.db_sync import sync_all, sync_scoped, sync_costs
from app.arm_live_reads import fetch_live_resources
from app.analysis import run_db_analysis
from app.analysis_persist import persist_optimization_run
from app.batch_analyzer import (
    create_analysis_job,
    execute_batch_job,
    expire_stale_analysis_jobs,
    queue_post_sync_analysis,
    queue_rule_config_reanalysis,
    serialize_job,
)
from app.admin_overview import build_optimization_overview
from app.finding_evidence import disk_inventory_properties_map, enrich_finding_for_api
from app.focus_mapping import normalize_arm_id
from app.optimizer.rule_catalog import (
    canonical_resource_rule_catalog,
    list_all_rules,
    list_components,
    list_rules_for_canonical_type,
    resolve_rule_id,
)
from app.resources import list_technical_fetch_specs
from app.optimizer.rule_registry import ALL_KNOWN_RULE_IDS, is_known_rule
from app.ai_analysis import enrich_analysis_with_ai
from app.optimizer.engine import OptimizationEngine
from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.engine_config import get_effective_config, upsert_rule_config, delete_rule_config
from app.ai_client import verify_ai_connection
from app.services.settings_schema import SETTING_CATEGORIES
from app.services.system_settings import (
    apply_database_connection,
    build_database_url,
    get_all_settings,
    get_category_settings,
    get_effective_config as get_system_config,
    mask_database_url,
    save_category_settings,
    test_azure_connection,
    test_database_connection,
)
from app.openapi_config import configure_openapi
from app.spa_utils import should_serve_spa, spa_index_response
from app import auth as azure_auth
from app.user_auth import (
    authenticate_user,
    check_login_rate_limit,
    clear_login_failures,
    create_access_token,
    create_app_user,
    ensure_default_admin,
    ensure_default_viewer,
    list_app_users,
    record_login_failure,
    reset_app_user_password,
    require_admin_user,
    require_authenticated_user,
    serialize_app_user,
    ROLE_ADMIN,
    ROLE_VIEWER,
)
from app.resource_type_catalog import parse_resource_types_param, resource_types_catalog
from app.cost_explorer_worker import request_cost_sync
# ── Advanced tools router (waste heatmap, tag compliance, auto scheduler,
#    notification channels, anomaly detector, optimization timeline) ───────────
from app.routes_advanced import router as advanced_router

# ---------------------------------------------------------------------------
# Module-level: settings object only — no DDL, no logging side-effects.
# configure_logging and validate_startup live in lifespan so they do not
# fire when main.py is imported by the test suite.
# ---------------------------------------------------------------------------
settings = get_settings()
log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Lifespan — replaces the deprecated @app.on_event("startup") pattern.
# DDL (create_all) and schema migrations run here so that importing main.py
# in tests does NOT trigger a database migration or logging configuration.
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── startup ──────────────────────────────────────────────────────────
    configure_logging(
        level=settings.log_level,
        json_logs=settings.is_production,
    )
    if settings.is_production:
        settings.validate_startup()
    log.info(
        "app.startup",
        app_env=settings.app_env,
        log_level=settings.log_level,
        production=settings.is_production,
    )

    Base.metadata.create_all(bind=engine)
    migrate_schema()

    from app.database import SessionLocal
    from app.startup_bootstrap import bootstrap_app_service

    bootstrap_app_service()
    db = SessionLocal()
    try:
        ensure_default_admin(db)
        ensure_default_viewer(db)
        azure_auth.reload_credential(db)
        from app.subscription_store import (
            ensure_subscription_cache_row,
            _default_subscription_from_settings,
        )
        default_sub = _default_subscription_from_settings(db)
        if default_sub:
            ensure_subscription_cache_row(db, default_sub)
            db.commit()
    finally:
        db.close()

    # Daily refresh of cost data from Azure Cost Management API.
    from app import cost_scheduler
    cost_scheduler.start()

    # Subscription-wide ARM resource discovery (maps to inventory layout).
    from app import resource_discovery_worker
    resource_discovery_worker.start()

    # Clear orphaned analysis jobs left running after a process restart.
    _startup_db = SessionLocal()
    try:
        expired = expire_stale_analysis_jobs(_startup_db)
        if expired:
            log.info("analysis.startup_expired_stale_jobs", count=len(expired))
    finally:
        _startup_db.close()

    # Scheduled Azure inventory sync + optimization analysis workers.
    from app import operations_scheduler
    operations_scheduler.start()

    yield  # application runs here

    # ── shutdown (add cleanup here as needed) ────────────────────────────


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="InfinityOps API",
    version=__version__,
    description="API for Azure cost, inventory, and optimization.",
    lifespan=lifespan,
)
configure_openapi(app)


@app.get("/api/openapi.json", include_in_schema=False, tags=["Admin"],
         summary="OpenAPI schema (SPA path, admin only)")
def openapi_json_for_spa(request: Request):
    _ = require_admin_user(request)
    return app.openapi()


app.add_middleware(DynamicCORSMiddleware)
app.add_middleware(AppAuthMiddleware)
app.middleware("http")(cache_control_middleware)

# Register advanced tools router
# Provides: GET/POST /api/waste-heatmap, /api/tag-compliance,
# /api/auto-scheduler, /api/notifications, /api/anomaly-detector, /api/timeline
app.include_router(advanced_router)

# These singletons are intentionally module-level for shared HTTP connection
# pool reuse. They do not hold credentials directly — credentials are resolved
# lazily per-request via get_arm_token(db). Instantiation here is safe because
# no credential loading occurs at construction time.
cost_client     = AzureCostClient()
resource_client = AzureResourcesClient()


@app.exception_handler(AzureAPIError)
async def azure_error_handler(request, exc: AzureAPIError):
    # Upstream Azure 502/503/504 are provider outages — return 503 to the SPA.
    status = 503 if exc.status in {502, 503, 504} else exc.status
    return JSONResponse(
        status_code=status,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request, exc: Exception):
    # Log only the path — never the full URL — to avoid leaking query params
    # (subscription_id, from_date, etc.) into structured logs.
    log.exception(
        "unhandled_error",
        method=request.method,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "An unexpected error occurred."}},
    )


# ─── Schemas ──────────────────────────────────────────────────────────────────

class K8sUtilizationIn(BaseModel):
    cluster_name:   Optional[str] = None
    node_name:      str = Field(..., min_length=1, max_length=253)
    pod_name:       Optional[str] = None
    namespace:      Optional[str] = None
    cpu_usage:      Optional[str] = None
    memory_usage:   Optional[str] = None


# ISO 8601 datetime: YYYY-MM-DDTHH:MM:SS with optional timezone offset or Z
_ISO8601_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$"
)


class K8sSnapshotIn(BaseModel):
    cluster_name:   str = Field(..., min_length=1, max_length=253)
    collected_at:   Optional[str] = None
    summary:        dict = Field(default_factory=dict)
    nodes:          list[dict] = Field(default_factory=list, max_length=500)
    pods:           list[dict] = Field(default_factory=list, max_length=5000)

    @field_validator("collected_at")
    @classmethod
    def _validate_collected_at(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        v = value.strip()
        if not _ISO8601_DATETIME_RE.match(v):
            raise ValueError(
                f"collected_at must be an ISO 8601 datetime (e.g. 2024-01-15T10:30:00Z); got {value!r}"
            )
        return v


def _scoped_subscription(db: Session, subscription_id: str) -> str:
    """Validate format and ensure subscription belongs to this deployment."""
    return ensure_subscription_known(db, subscription_id)


# _DATE_RE enforces exactly YYYY-MM-DD — anchors mean len is implicitly 10.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ISO 8601 duration: P[nD][T[nH][nM][nS]] — e.g. P7D, P1DT12H, PT30M
_ISO8601_DURATION_RE = re.compile(
    r"^P(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+S)?)?$"
)


def _cost_range_kwargs(
    timeframe: str,
    from_date: str | None,
    to_date: str | None,
    *,
    resource_types: str | None = None,
) -> dict:
    kw: dict = {"timeframe": timeframe}
    if (from_date or "").strip():
        raw = from_date.strip()
        if not _DATE_RE.match(raw):
            raise HTTPException(
                status_code=422,
                detail=f"from_date must be YYYY-MM-DD; got {from_date!r}",
            )
        kw["from_date"] = raw
    if (to_date or "").strip():
        raw = to_date.strip()
        if not _DATE_RE.match(raw):
            raise HTTPException(
                status_code=422,
                detail=f"to_date must be YYYY-MM-DD; got {to_date!r}",
            )
        kw["to_date"] = raw
    if timeframe == "Custom" and (not kw.get("from_date") or not kw.get("to_date")):
        raise HTTPException(
            status_code=422,
            detail="from_date and to_date are required when timeframe is Custom",
        )
    types = parse_resource_types_param(resource_types)
    if types:
        kw["resource_types"] = types
    return kw


def _live_cost_token(db: Session) -> str | None:
    try:
        return get_arm_token(db)
    except Exception as exc:
        log.warning("cost_api.token_unavailable", error=str(exc)[:300])
        return None


def _enqueue_cost_sync(subscription_id: str, *, reason: str) -> None:
    """Enqueue a background cost sync. Logs a warning if the worker is unavailable."""
    try:
        request_cost_sync(subscription_id, reason=reason)
    except Exception as exc:
        log.warning(
            "cost_sync.enqueue_failed",
            subscription_id=subscription_id,
            reason=reason,
            error=str(exc)[:300],
        )


def _require_admin_live_arm(
    request: Request,
    db: Session,
    subscription_id: str,
):
    """Gate live Azure Resource Manager reads behind admin + subscription scope."""
    _ = require_admin_user(request)
    return _scoped_subscription(db, subscription_id)


def _verify_k8s_agent_token(
    api_key: Optional[str] = None,
    db: Optional[Session] = None,
) -> None:
    k8s_cfg = get_system_config(db, "kubernetes") if db is not None else {}
    expected = k8s_cfg.get("agent_token") or settings.k8s_agent_token
    require = bool(k8s_cfg.get("require_agent_token") or settings.require_k8s_token)

    # No token configured: fail loudly in any enforcing mode.
    if not expected and (settings.is_production or settings.auth_enabled or require):
        raise HTTPException(
            status_code=503,
            detail="K8s agent authentication is not configured",
        )

    # No token configured and no enforcement (dev mode): allow any call.
    if not expected:
        return

    # Always run compare_digest — even when api_key is empty — so that the
    # comparison takes constant time regardless of whether a key was provided,
    # preventing a timing side-channel that could reveal whether a token is set.
    if not secrets.compare_digest(api_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _verify_k8s_read_access(
    request: Request,
    x_api_key: Optional[str],
    db: Session,
) -> None:
    """Allow cluster snapshot reads via agent token or signed-in app users."""
    if x_api_key:
        _verify_k8s_agent_token(x_api_key, db)
        return
    if settings.auth_enabled:
        require_authenticated_user(request)
        return
    if settings.is_production:
        raise HTTPException(status_code=401, detail="Sign in required")


class RuleConfigIn(BaseModel):
    rule_id:     str = Field(..., description="Rule ID e.g. VM_IDLE, AKS_NO_AUTOSCALER")
    enabled:     bool = True
    overrides:   dict[str, float | int | bool | str] = Field(
        default_factory=dict,
        description='Scalar threshold overrides e.g. {"cpu_idle_pct": 3.0}',
    )
    description: Optional[str] = None


class AnalyzeRequest(BaseModel):
    subscription_id:  str
    profile:          str  = Field("default", description="Engine config profile name")
    engine_version:   str  = Field("extended", description="standard | extended")
    data_source:      str  = Field(
        "db",
        description="db = analyze synced database inventory (default) | live = fetch from Azure (admin)",
    )
    rule_overrides:   dict[str, dict[str, float | int | bool | str]] = Field(
        default_factory=dict,
        description='Per-rule runtime overrides: {"VM_IDLE": {"cpu_idle_pct": 3.0}}',
    )
    components:       Optional[list[str]] = Field(
        None,
        description="Limit analysis to these optimization components (e.g. Virtual Machines)",
    )
    include_metrics:  bool = Field(True, description="Fetch Azure Monitor metrics during analysis (recommended)")
    include_ai:       bool = Field(
        True,
        description="Generate AI recommendations from rule findings and evidence (requires Azure OpenAI config).",
    )
    timespan_metrics: str  = Field("P7D", description="ISO 8601 duration for metric lookback e.g. P7D, P1D")

    @field_validator("subscription_id")
    @classmethod
    def _validate_subscription(cls, value: str) -> str:
        return validate_subscription_id(value)

    @field_validator("data_source")
    @classmethod
    def _validate_data_source(cls, value: str) -> str:
        v = (value or "db").strip().lower()
        if v not in {"db", "live"}:
            raise ValueError("data_source must be 'db' or 'live'")
        return v

    @field_validator("timespan_metrics")
    @classmethod
    def _validate_timespan(cls, value: str) -> str:
        v = (value or "").strip().upper()
        if not _ISO8601_DURATION_RE.match(v) or v == "P":
            raise ValueError(
                f"timespan_metrics must be an ISO 8601 duration (e.g. P7D, P1DT12H); got {value!r}"
            )
        return v


class FindingStatusIn(BaseModel):
    status: str = Field(..., description="open | acknowledged | resolved | ignored")

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return validate_finding_status(value)


class BulkFindingStatusIn(BaseModel):
    finding_ids: list[Annotated[str, Field(max_length=200)]] = Field(
        ..., min_length=1, max_length=500
    )
    status: str = Field(..., description="open | acknowledged | resolved | ignored")

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return validate_finding_status(value)


class ResourceTagsIn(BaseModel):
    # Azure ARM enforces 512-char tag keys and 256-char tag values.
    tags: dict[
        Annotated[str, Field(max_length=512)],
        Annotated[str, Field(max_length=256)],
    ] = Field(default_factory=dict, description="Tag key-value pairs")


class FindingExecutionIn(BaseModel):
    action_type: str = Field(..., description="resize | delete | deallocate | tag | other")
    before_state: dict[str, Any] = Field(default_factory=dict)


class FindingValidationIn(BaseModel):
    after_state: dict[str, Any] = Field(default_factory=dict)
    regressed: bool = False


class ActionWorkflowIn(BaseModel):
    workflow_status: str | None = Field(None, description="proposed | approved | executed | rejected | deferred")
    owner: str | None = None
    note: str | None = None
    clear_owner: bool = False

    @field_validator("workflow_status")
    @classmethod
    def _validate_workflow(cls, value: str | None) -> str | None:
        if value is None:
            return None
        v = value.strip().lower()
        valid = {"proposed", "approved", "executed", "rejected", "deferred"}
        if v not in valid:
            raise ValueError(f"workflow_status must be one of: {sorted(valid)}")
        return v


class BulkActionWorkflowIn(BaseModel):
    action_ids: list[Annotated[str, Field(max_length=200)]] = Field(
        ..., min_length=1, max_length=500
    )
    workflow_status: str = Field(..., description="proposed | approved | executed | rejected | deferred")
    note: str | None = None

    @field_validator("workflow_status")
    @classmethod
    def _validate_workflow(cls, value: str) -> str:
        v = value.strip().lower()
        valid = {"proposed", "approved", "executed", "rejected", "deferred"}
        if v not in valid:
            raise ValueError(f"workflow_status must be one of: {sorted(valid)}")
        return v


class BulkActionAssignIn(BaseModel):
    action_ids: list[Annotated[str, Field(max_length=200)]] = Field(
        ..., min_length=1, max_length=500
    )
    owner: str = Field(..., min_length=1, max_length=200)
    note: str | None = None


class BatchResourceLookupIn(BaseModel):
    subscription_id: str
    resource_ids: list[Annotated[str, Field(max_length=500)]] = Field(
        ..., min_length=1, max_length=25
    )
    timespan: str = Field("P7D", description="ISO 8601 duration for metrics, e.g. P7D")
    include_metrics: bool = True
    include_advanced_analysis: bool = True

    @field_validator("timespan")
    @classmethod
    def _validate_timespan(cls, value: str) -> str:
        v = (value or "").strip().upper()
        if not _ISO8601_DURATION_RE.match(v) or v == "P":
            raise ValueError(
                f"timespan must be an ISO 8601 duration (e.g. P7D, P1DT12H); got {value!r}"
            )
        return v


class BulkResourceTagsIn(BaseModel):
    subscription_id: str
    resource_ids: list[Annotated[str, Field(max_length=500)]] = Field(
        ..., min_length=1, max_length=50
    )
    # Azure ARM tag key/value length limits applied here too.
    tags: dict[
        Annotated[str, Field(max_length=512)],
        Annotated[str, Field(max_length=256)],
    ] = Field(default_factory=dict)


_VALID_AUTH_MODES = {"managed_identity", "default_credential", "service_principal"}
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class AzureSettingsIn(BaseModel):
    auth_mode: Optional[str] = Field(None, description="managed_identity | default_credential | service_principal")
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = Field(None, description="Leave blank to keep the stored secret")
    default_subscription_id: Optional[str] = None

    @field_validator("auth_mode")
    @classmethod
    def _validate_auth_mode(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        v = value.strip().lower()
        if v not in _VALID_AUTH_MODES:
            raise ValueError(f"auth_mode must be one of: {sorted(_VALID_AUTH_MODES)}")
        return v


class DatabaseSettingsIn(BaseModel):
    dialect: Optional[str] = Field("postgresql", description="postgresql | sqlite")
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = Field(None, description="Leave blank to keep the stored password")
    ssl_mode: Optional[str] = None


class ApplicationSettingsIn(BaseModel):
    app_env: Optional[str] = None
    cors_allowed_origins: Optional[str] = None
    request_timeout_seconds: Optional[int] = None
    log_level: Optional[str] = None

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        v = value.strip().upper()
        if v not in _VALID_LOG_LEVELS:
            raise ValueError(f"log_level must be one of: {sorted(_VALID_LOG_LEVELS)}")
        return v


class KubernetesSettingsIn(BaseModel):
    agent_token: Optional[str] = Field(None, description="Leave blank to keep the stored token")
    require_agent_token: Optional[bool] = None


class AiSettingsIn(BaseModel):
    ai_enabled: Optional[bool] = None
    ai_auth_mode: Optional[str] = Field(None, description="api_key | azure_ad")
    openai_key: Optional[str] = Field(None, description="Leave blank to keep the stored key")
    openai_endpoint: Optional[str] = None
    openai_deployment: Optional[str] = None
    openai_api_version: Optional[str] = None
    ai_enrich_all_findings: Optional[bool] = None
    ai_max_findings_per_run: Optional[int] = Field(None, ge=1, le=200)
    ai_batch_size: Optional[int] = Field(None, ge=1, le=25)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def _strip_username(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("username must not be blank")
        return stripped


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=256)
    display_name: Optional[str] = Field(None, max_length=128)
    role: str = Field(ROLE_VIEWER, description="admin or viewer")

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str) -> str:
        v = value.strip().lower()
        valid = {ROLE_ADMIN, ROLE_VIEWER}
        if v not in valid:
            raise ValueError(f"role must be one of: {sorted(valid)}")
        return v


class ResetUserPasswordRequest(BaseModel):
    password: str = Field(..., min_length=8, max_length=256)


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "version": __version__}


@app.get("/health/live", tags=["System"])
def health_live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["System"])
def health_ready(db: Session = Depends(get_db)):
    checks: dict[str, str] = {}
    if (settings.is_production or settings.auth_enabled) and not settings.jwt_configured:
        checks["auth"] = "jwt_secret_missing"
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        log.warning("readiness_check_failed", error=str(exc))
        checks["database"] = "error"
    if any(value != "ok" for value in checks.values()):
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", **checks},
        )
    return {"status": "ready", **checks}


# ─── Application auth ─────────────────────────────────────────────────────────

@app.post("/auth/login", tags=["Auth"], summary="Sign in with username and password")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"

    # Skip rate limiting for unresolvable IPs (e.g. behind a proxy returning None)
    # to avoid locking all users into a shared bucket.
    if client_ip != "unknown":
        if not check_login_rate_limit(db, client_ip):
            raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again later.")

    user = authenticate_user(db, body.username, body.password)
    if not user:
        if client_ip != "unknown":
            record_login_failure(db, client_ip)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if client_ip != "unknown":
        clear_login_failures(db, client_ip)

    if (settings.is_production or settings.auth_enabled) and not settings.jwt_configured:
        log.error("login_blocked", reason="jwt_secret_missing")
        raise HTTPException(
            status_code=503,
            detail="Sign-in is not configured. Ask your administrator to set JWT_SECRET in App Service settings.",
        )

    try:
        token = create_access_token(user_id=user.id, username=user.username, role=user.role)
    except RuntimeError as exc:
        log.error("login_blocked", reason=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Only persist last_login_at once we know the token can be issued.
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
            "role": user.role,
        },
    }


@app.get("/auth/me", tags=["Auth"], summary="Current signed-in user")
def auth_me(request: Request):
    user = require_authenticated_user(request)
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name") or user["username"],
        "role": user["role"],
        "is_admin": user.get("role") == ROLE_ADMIN,
    }


@app.get("/auth/users", tags=["Auth"], summary="List application users (admin only)")
def list_users(request: Request, db: Session = Depends(get_db)):
    _ = require_admin_user(request)
    return list_app_users(db)


@app.post("/auth/users", tags=["Auth"], summary="Create an application user (admin only)")
def create_user(
    request: Request,
    body: CreateUserRequest,
    db: Session = Depends(get_db),
):
    _ = require_admin_user(request)
    try:
        user = create_app_user(
            db,
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            role=body.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "user": serialize_app_user(user)}


@app.patch("/auth/users/{user_id}/password", tags=["Auth"],
           summary="Reset a user's password (admin only)")
def reset_user_password(
    request: Request,
    user_id: str = Path(...),
    body: ResetUserPasswordRequest = Body(...),
    db: Session = Depends(get_db),
):
    _ = require_admin_user(request)
    try:
        user = reset_app_user_password(db, user_id, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "user": serialize_app_user(user)}


# ══════════════════════════════════════════════════════════════════════════════
#  SYSTEM SETTINGS  (Azure, database, application, Kubernetes)
# ══════════════════════════════════════════════════════════════════════════════

# Category → model map used by the generic PUT /settings/{category} endpoint.
# Explicit dispatch avoids Union-matching ambiguity where overlapping field
# names could cause Pydantic to silently coerce the wrong model.
_SETTINGS_MODEL_MAP: dict[str, type[BaseModel]] = {
    "azure":       AzureSettingsIn,
    "database":    DatabaseSettingsIn,
    "application": ApplicationSettingsIn,
    "kubernetes":  KubernetesSettingsIn,
    "ai":          AiSettingsIn,
}


@app.get("/settings/status", tags=["Settings"],
         summary="Runtime status for database, CORS, and encryption")
def settings_status(request: Request):
    _ = require_admin_user(request)
    return get_runtime_status()


@app.get("/settings", tags=["Settings"],
         summary="Get all system settings (secrets masked)")
def list_all_settings(request: Request, db: Session = Depends(get_db)):
    _ = require_admin_user(request)
    return get_all_settings(db, masked=True)


@app.get("/settings/{category}", tags=["Settings"],
         summary="Get settings for a category")
def get_settings_category(request: Request, category: str = Path(...), db: Session = Depends(get_db)):
    _ = require_admin_user(request)
    if category not in SETTING_CATEGORIES:
        raise HTTPException(404, f"Unknown category. Valid: {list(SETTING_CATEGORIES)}")
    return get_category_settings(db, category, masked=True)


@app.put("/settings/{category}", tags=["Settings"],
         summary="Save settings for a category to the database")
def put_settings_category(
    request: Request,
    category: str = Path(...),
    body: dict = Body(...),
    db: Session = Depends(get_db),
):
    _ = require_admin_user(request)
    if category not in SETTING_CATEGORIES:
        raise HTTPException(404, f"Unknown category. Valid: {list(SETTING_CATEGORIES)}")

    model_cls = _SETTINGS_MODEL_MAP.get(category)
    if model_cls is None:
        raise HTTPException(404, f"Unknown category. Valid: {list(_SETTINGS_MODEL_MAP)}")

    try:
        parsed = model_cls.model_validate(body)
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc

    try:
        saved = save_category_settings(db, category, parsed.model_dump(exclude_none=True))
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc

    if category == "azure":
        azure_auth.reload_credential(db)
    if category in {"application", "kubernetes", "ai"}:
        invalidate_runtime_config()
    return {"category": category, "settings": saved, "message": "Settings saved."}


@app.post("/settings/azure", tags=["Settings"],
          summary="Save Azure connection settings")
def save_azure_settings(request: Request, body: AzureSettingsIn, db: Session = Depends(get_db)):
    _ = require_admin_user(request)
    payload = body.model_dump(exclude_none=True)
    if "client_secret" in payload and payload["client_secret"] == "":
        payload.pop("client_secret")
    saved = save_category_settings(db, "azure", payload)
    azure_auth.reload_credential(db)
    return {"category": "azure", "settings": saved, "message": "Azure settings saved."}


@app.post("/settings/database", tags=["Settings"],
          summary="Save database connection settings")
def save_database_settings(request: Request, body: DatabaseSettingsIn, db: Session = Depends(get_db)):
    _ = require_admin_user(request)
    payload = body.model_dump(exclude_none=True)
    if "password" in payload and payload["password"] == "":
        payload.pop("password")
    saved = save_category_settings(db, "database", payload)
    return {
        "category": "database",
        "settings": saved,
        "message": "Database settings saved. Click Apply connection to switch without restarting.",
        "connection_url": mask_database_url(build_database_url(get_system_config(db, "database"))),
    }


@app.post("/settings/application", tags=["Settings"],
          summary="Save application settings")
def save_application_settings(request: Request, body: ApplicationSettingsIn, db: Session = Depends(get_db)):
    _ = require_admin_user(request)
    saved = save_category_settings(db, "application", body.model_dump(exclude_none=True))
    invalidate_runtime_config()
    return {
        "category": "application",
        "settings": saved,
        "message": "Application settings saved. CORS changes are active immediately.",
    }


@app.post("/settings/kubernetes", tags=["Settings"],
          summary="Save Kubernetes agent settings")
def save_kubernetes_settings(request: Request, body: KubernetesSettingsIn, db: Session = Depends(get_db)):
    _ = require_admin_user(request)
    payload = body.model_dump(exclude_none=True)
    if "agent_token" in payload and payload["agent_token"] == "":
        payload.pop("agent_token")
    saved = save_category_settings(db, "kubernetes", payload)
    invalidate_runtime_config()
    return {"category": "kubernetes", "settings": saved, "message": "Kubernetes settings saved."}


@app.post("/settings/ai", tags=["Settings"],
          summary="Save Azure OpenAI settings for analysis enrichment")
def save_ai_settings(request: Request, body: AiSettingsIn, db: Session = Depends(get_db)):
    _ = require_admin_user(request)
    payload = body.model_dump(exclude_none=True)
    if "openai_key" in payload and payload["openai_key"] == "":
        payload.pop("openai_key")
    saved = save_category_settings(db, "ai", payload)
    invalidate_runtime_config()
    return {"category": "ai", "settings": saved, "message": "AI settings saved."}


@app.post("/settings/ai/test", tags=["Settings"],
          summary="Test Azure OpenAI connection")
def test_ai_settings(
    request: Request,
    body: Optional[AiSettingsIn] = None,
    db: Session = Depends(get_db),
):
    _ = require_admin_user(request)
    cfg = get_system_config(db, "ai")
    if body:
        updates = body.model_dump(exclude_none=True)
        if updates.get("openai_key") == "":
            updates.pop("openai_key", None)
        cfg.update(updates)
    result = verify_ai_connection(cfg, db=db)
    if not result.get("ok"):
        raise HTTPException(400, result.get("message") or "AI connection test failed.")
    return result


@app.post("/settings/azure/test", tags=["Settings"],
          summary="Test Azure connection with provided or stored settings")
def test_azure_settings(
    request: Request,
    body: Optional[AzureSettingsIn] = None,
    db: Session = Depends(get_db),
):
    _ = require_admin_user(request)
    config = get_system_config(db, "azure")
    if body:
        overrides = body.model_dump(exclude_none=True)
        if overrides.get("client_secret") == "":
            overrides.pop("client_secret", None)
        config.update(overrides)
    result = test_azure_connection(config)
    if not result.get("ok"):
        raise HTTPException(400, result.get("message", "Azure connection failed"))
    return result


@app.post("/settings/database/test", tags=["Settings"],
          summary="Test database connection with provided or stored settings")
def test_database_settings(
    request: Request,
    body: Optional[DatabaseSettingsIn] = None,
    db: Session = Depends(get_db),
):
    _ = require_admin_user(request)
    config = get_system_config(db, "database")
    if body:
        overrides = body.model_dump(exclude_none=True)
        if overrides.get("password") == "":
            overrides.pop("password", None)
        config.update(overrides)
    result = test_database_connection(config)
    if not result.get("ok"):
        raise HTTPException(400, result.get("message", "Database connection failed"))
    return result


@app.post("/settings/database/apply", tags=["Settings"],
          summary="Apply stored database connection without restarting the API")
def apply_database_settings(request: Request, db: Session = Depends(get_db)):
    _ = require_admin_user(request)
    try:
        result = apply_database_connection(db)
    except Exception as exc:
        raise HTTPException(400, f"Could not apply database connection: {exc}") from exc
    invalidate_runtime_config()
    return result


@app.post("/settings/reload", tags=["Settings"],
          summary="Reload Azure credentials from stored settings")
def reload_settings(request: Request, db: Session = Depends(get_db)):
    _ = require_admin_user(request)
    azure_auth.reload_credential(db)
    return {"status": "ok", "message": "Azure credentials reloaded from database settings."}


# ══════════════════════════════════════════════════════════════════════════════
#  COST MANAGEMENT  (Azure Cost Management API — synced to PostgreSQL)
# ══════════════════════════════════════════════════════════════════════════════

def _cost_api_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CostExportNotConfiguredError):
        log.error("cost_api.not_configured", error=str(exc))
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, CostExportReadError):
        detail = str(exc)
        status = 403 if "authorization" in detail.lower() or "403" in detail else 502
        log.error("cost_api.read_failed", error=detail, status=status)
        return HTTPException(status_code=status, detail=detail)
    log.exception("cost_api.unexpected_error")
    return HTTPException(status_code=500, detail=str(exc))


@app.get("/costs/timeframes", tags=["Cost Management"],
         summary="Supported cost explorer timeframes")
def list_cost_timeframes():
    return {"timeframes": list_timeframe_catalog()}


@app.get("/costs", tags=["Cost Management"],
         summary="Query actual costs from the database (synced from Azure Cost Management)")
def get_costs(
    request: Request,
    subscription_id: Optional[str] = Query(None),
    timeframe:       str = Query("MonthToDate"),
    from_date:       Optional[str] = Query(None, description="YYYY-MM-DD (required for Custom)"),
    to_date:         Optional[str] = Query(None, description="YYYY-MM-DD (required for Custom)"),
    granularity:     str = Query("Daily"),
    resource_types:  Optional[str] = Query(None, description="Comma-separated canonical resource types"),
    db: Session = Depends(get_db),
):
    if should_serve_spa(request, api_query_present=subscription_id is not None):
        spa = spa_index_response()
        if spa:
            return spa
    if not subscription_id:
        raise HTTPException(status_code=422, detail="subscription_id is required")
    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, from_date, to_date, resource_types=resource_types)
    live_kw = live_range_kw(range_kw)
    token = _live_cost_token(db)
    scope = f"/subscriptions/{subscription_id}"
    try:
        db_data, source = resolve_cost_db_then_live(
            db_call=lambda: daily_cost_response_from_db(db, subscription_id, **range_kw),
            live_call=lambda: query_daily_costs_live(
                db, subscription_id, token=token, **live_kw,
            ),
        )
    except (CostExportNotConfiguredError, CostExportReadError, Exception) as exc:
        raise _cost_api_http_error(exc) from exc
    if db_data:
        if source != "database":
            _enqueue_cost_sync(subscription_id, reason="live_fallback_daily")
        log.info(
            "cost_api.get_costs",
            subscription_id=subscription_id,
            timeframe=timeframe,
            source=source,
            rows=len(db_data.get("properties", {}).get("rows", [])),
        )
        return {
            "id": None, "scope": scope, "timeframe": timeframe,
            "granularity": granularity, "data": db_data, "source": source,
        }
    _enqueue_cost_sync(subscription_id, reason="no_synced_rows")
    log.info(
        "cost_api.get_costs",
        subscription_id=subscription_id,
        timeframe=timeframe,
        source="database",
        note="no_synced_rows",
    )
    empty = empty_daily_cost_response()
    return {
        "id": None, "scope": scope, "timeframe": timeframe,
        "granularity": granularity, "data": empty, "source": "database",
        "sync_required": True,
    }


@app.get("/costs/resource-group", tags=["Cost Management"],
         summary="Daily costs for a resource group (database after sync)")
def get_rg_costs(
    subscription_id: str = Query(...),
    resource_group:  str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    from_date:       Optional[str] = Query(None),
    to_date:         Optional[str] = Query(None),
    granularity:     str = Query("Daily"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, from_date, to_date)
    scope = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
    try:
        db_data = daily_cost_by_resource_group_from_db(
            db, subscription_id, resource_group, **range_kw,
        )
    except (CostExportNotConfiguredError, CostExportReadError, Exception) as exc:
        raise _cost_api_http_error(exc) from exc
    if db_data:
        log.info(
            "cost_api.get_rg_costs",
            subscription_id=subscription_id,
            resource_group=resource_group,
            timeframe=timeframe,
            source="database",
        )
        return {"id": None, "scope": scope, "data": db_data, "source": "database"}
    log.info(
        "cost_api.get_rg_costs",
        subscription_id=subscription_id,
        resource_group=resource_group,
        timeframe=timeframe,
        source="database",
        note="no_synced_rows",
    )
    empty = empty_daily_cost_response()
    return {
        "id": None, "scope": scope, "data": empty, "source": "database",
        "sync_required": True,
    }

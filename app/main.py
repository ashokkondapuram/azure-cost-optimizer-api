"""Azure Cost Optimizer — Production API v5.0

Includes:
  - Full Cost Management API (v2024-08-01)
  - All resource type endpoints (Compute, AKS, Storage, Network, DB, Security)
  - Optimization Engine with configurable rules + profiles
  - Engine config CRUD (enable/disable rules, override thresholds per profile)
  - Finding history + remediation status tracking
"""
# ── stdlib ────────────────────────────────────────────────────────────────────
import json
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal, Optional

# ── third-party ───────────────────────────────────────────────────────────────
import structlog
from fastapi import (
    BackgroundTasks,
    Body,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
)
from fastapi.responses import JSONResponse, StreamingResponse
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
from app.http_client import AzureAPIError, arm_fetch_workers
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
    Base, CostRecord, K8sUtilization, K8sSnapshot,
    OptimizationRun, EngineConfig, OptimizationFinding,
    SubscriptionCache, AnalysisJob,
)
from app.billed_resources import list_billed_resources_page
from app.resource_store import (
    get_resources_db,
    get_resources_db_page,
    get_resource_counts,
    list_all_resources_db,
    list_cost_resources_db,
    get_resources_by_type_prefix_db,
    get_aks_clusters_db,
    apply_costs_to_resources,
)
from app.cost_db import resource_cost_map_from_db
from app.auth import arm_bearer_token
from app.db_sync import sync_all, sync_scoped, sync_costs, enrich_aks_arm_clusters
from app.arm_live_reads import fetch_live_resources, paginate_list
from app.arm_resource_enrichment import enrich_arm_resources_for_type
from app.db_clear import clear_synced_data
from app.analysis import run_db_analysis
# fix #1: persist_optimization_run must be imported at module level so that
# _run_live_analysis (and any background task referencing it) never raises
# a NameError at runtime.
from app.analysis_persist import persist_optimization_run
from app.batch_analyzer import (
    create_analysis_job,
    execute_batch_job,
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
from app.optimizer.unified_engine import append_cost_export_findings
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
from app.production_routes import configure_production_routes
from app.openapi_config import configure_openapi
from app.api_explorer import build_api_explorer_context
from app.azure_live_api import register_azure_live_routes
from app.spa_utils import should_serve_spa, spa_index_response
from app import auth as azure_auth
from app.user_auth import (
    authenticate_user,
    create_access_token,
    create_app_user,
    ensure_default_admin,
    ensure_default_viewer,
    list_app_users,
    reset_app_user_password,
    require_admin_user,
    require_authenticated_user,
    serialize_app_user,
    ROLE_ADMIN,
    ROLE_VIEWER,
)

# ---------------------------------------------------------------------------
# Module-level: settings object only — no DDL, no logging side-effects.
# fix #9: configure_logging and validate_startup moved into lifespan so they
# do not fire when main.py is imported by the test suite.
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
    # fix #9: logging + startup validation live here, not at module level.
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
        from app.subscription_store import ensure_subscription_cache_row, _default_subscription_from_settings
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
    from app.batch_analyzer import expire_stale_analysis_jobs

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
    require_admin_user(request)
    return app.openapi()


app.add_middleware(DynamicCORSMiddleware)
app.add_middleware(AppAuthMiddleware)
app.middleware("http")(cache_control_middleware)

cost_client     = AzureCostClient()
resource_client = AzureResourcesClient()


@app.exception_handler(AzureAPIError)
async def azure_error_handler(request, exc: AzureAPIError):
    # Upstream Azure 502/503/504 are provider outages — return 503, not 502, to the SPA.
    status = 503 if exc.status in {502, 503, 504} else exc.status
    return JSONResponse(
        status_code=status,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request, exc: Exception):
    log.exception("unhandled_error", path=str(request.url.path))
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "An unexpected error occurred."}},
    )


# ─── Schemas ──────────────────────────────────────────────────────────────────

class K8sUtilizationIn(BaseModel):
    cluster_name: Optional[str] = None
    node_name: str
    pod_name: Optional[str] = None
    namespace: Optional[str] = None
    cpu_usage: Optional[str] = None
    memory_usage: Optional[str] = None


# fix #10: use max_items (not max_length) on list fields — semantically correct
# for Pydantic v2 sequence constraints.
class K8sSnapshotIn(BaseModel):
    cluster_name: str = Field(..., min_length=1, max_length=253)
    collected_at: Optional[str] = None
    summary: dict = Field(default_factory=dict)
    nodes: list = Field(default_factory=list, max_items=500)
    pods: list = Field(default_factory=list, max_items=5000)


def _scoped_subscription(db: Session, subscription_id: str) -> str:
    """Validate format and ensure subscription belongs to this deployment."""
    return ensure_subscription_known(db, subscription_id)


# fix #8: validate date format before slicing to avoid silently truncating
# invalid dates (e.g. 2026-13-01) into equally-invalid partial strings that
# then cause a confusing 500 downstream instead of a clean 422 here.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _cost_range_kwargs(
    timeframe: str,
    from_date: str | None,
    to_date: str | None,
    *,
    resource_types: str | None = None,
) -> dict:
    kw: dict = {"timeframe": timeframe}
    if (from_date or "").strip():
        raw = from_date.strip()[:10]
        if not _DATE_RE.match(raw):
            raise HTTPException(
                status_code=422,
                detail=f"from_date must be YYYY-MM-DD; got {from_date!r}",
            )
        kw["from_date"] = raw
    if (to_date or "").strip():
        raw = to_date.strip()[:10]
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
    from app.resource_type_catalog import parse_resource_types_param

    types = parse_resource_types_param(resource_types)
    if types:
        kw["resource_types"] = types
    return kw


def _live_cost_token(db: Session) -> str | None:
    try:
        from app.auth import get_token

        return get_token(db)
    except Exception as exc:
        log.warning("cost_api.token_unavailable", error=str(exc)[:300])
        return None


def _enqueue_cost_sync(subscription_id: str, *, reason: str) -> None:
    from app.cost_explorer_worker import request_cost_sync

    request_cost_sync(subscription_id, reason=reason)


def _require_admin_live_arm(
    request: Request,
    db: Session,
    subscription_id: str,
):
    """Gate live Azure Resource Manager reads behind admin + subscription scope."""
    require_admin_user(request)
    return _scoped_subscription(db, subscription_id)


# fix #4: simplify _verify_k8s_agent_token — remove the dead production branch.
# Old logic: `if is_production and not expected → 503` then
#            `if auth_enabled and not expected → 503` was unreachable in prod
#            because the first guard already fired.
# New logic: single ordered set of guards that is easy to follow and safe to
# reorder without breaking behaviour.
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

    # Token is configured: always compare, regardless of environment.
    if not api_key or not secrets.compare_digest(api_key, expected):
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
    rule_id:     str  = Field(..., description="Rule ID e.g. VM_IDLE, AKS_NO_AUTOSCALER")
    enabled:     bool = True
    overrides:   dict = Field(default_factory=dict,
                              description="Threshold overrides e.g. {\"cpu_idle_pct\": 3.0}")
    description: Optional[str] = None


class AnalyzeRequest(BaseModel):
    subscription_id:  str
    profile:          str  = Field("default", description="Engine config profile name")
    engine_version:   str  = Field("extended", description="standard | extended")
    data_source:      str  = Field(
        "db",
        description="db = analyze synced database inventory (default) | live = fetch from Azure (admin)",
    )
    rule_overrides:   dict = Field(
        default_factory=dict,
        description="Per-rule runtime overrides: {\"VM_IDLE\": {\"cpu_idle_pct\": 3.0}}"
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
    timespan_metrics: str  = Field("P7D",  description="ISO 8601 duration for metric lookback e.g. P7D, P1D")

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


class FindingStatusIn(BaseModel):
    status: str = Field(..., description="open | acknowledged | resolved | ignored")

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return validate_finding_status(value)


class BulkFindingStatusIn(BaseModel):
    finding_ids: list[str] = Field(..., min_length=1, max_length=500)
    status: str = Field(..., description="open | acknowledged | resolved | ignored")

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return validate_finding_status(value)


class ResourceTagsIn(BaseModel):
    tags: dict[str, str] = Field(default_factory=dict, description="Tag key-value pairs")


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
    action_ids: list[str] = Field(..., min_length=1, max_length=500)
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
    action_ids: list[str] = Field(..., min_length=1, max_length=500)
    owner: str = Field(..., min_length=1, max_length=200)
    note: str | None = None


class BatchResourceLookupIn(BaseModel):
    subscription_id: str
    resource_ids: list[str] = Field(..., min_length=1, max_length=25)
    timespan: str = Field("P7D", description="ISO 8601 duration for metrics, e.g. P7D")
    include_metrics: bool = True
    include_advanced_analysis: bool = True


class BulkResourceTagsIn(BaseModel):
    subscription_id: str
    resource_ids: list[str] = Field(..., min_length=1, max_length=50)
    tags: dict[str, str] = Field(default_factory=dict)


class AzureSettingsIn(BaseModel):
    auth_mode: Optional[str] = Field(None, description="managed_identity | default_credential | service_principal")
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = Field(None, description="Leave blank to keep the stored secret")
    default_subscription_id: Optional[str] = None


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


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=256)
    display_name: Optional[str] = Field(None, max_length=128)
    role: str = Field(ROLE_VIEWER, description="admin or viewer")


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
    if settings.is_production and not settings.jwt_configured:
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
    from app.user_auth import check_login_rate_limit, record_login_failure, clear_login_failures

    client_ip = request.client.host if request.client else "unknown"
    if not check_login_rate_limit(db, client_ip):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again later.")

    user = authenticate_user(db, body.username, body.password)
    if not user:
        record_login_failure(db, client_ip)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    clear_login_failures(db, client_ip)

    # fix #7: check JWT configuration BEFORE writing last_login_at so that a
    # mis-configured deployment does not leave a committed login timestamp for
    # an attempt that ultimately failed with a 503.
    if settings.is_production and not settings.jwt_configured:
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
    require_admin_user(request)
    return list_app_users(db)


@app.post("/auth/users", tags=["Auth"], summary="Create an application user (admin only)")
def create_user(
    request: Request,
    body: CreateUserRequest,
    db: Session = Depends(get_db),
):
    require_admin_user(request)
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
    require_admin_user(request)
    try:
        user = reset_app_user_password(db, user_id, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "user": serialize_app_user(user)}


# ══════════════════════════════════════════════════════════════════════════════
#  SYSTEM SETTINGS  (Azure, database, application, Kubernetes)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/settings/status", tags=["Settings"],
         summary="Runtime status for database, CORS, and encryption")
def settings_status(request: Request):
    require_admin_user(request)
    return get_runtime_status()


@app.get("/settings", tags=["Settings"],
         summary="Get all system settings (secrets masked)")
def list_all_settings(request: Request, db: Session = Depends(get_db)):
    require_admin_user(request)
    return get_all_settings(db, masked=True)


@app.get("/settings/{category}", tags=["Settings"],
         summary="Get settings for a category")
def get_settings_category(request: Request, category: str = Path(...), db: Session = Depends(get_db)):
    require_admin_user(request)
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
    require_admin_user(request)
    if category not in SETTING_CATEGORIES:
        raise HTTPException(404, f"Unknown category. Valid: {list(SETTING_CATEGORIES)}")
    try:
        saved = save_category_settings(db, category, body)
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
    require_admin_user(request)
    payload = body.model_dump(exclude_none=True)
    if "client_secret" in payload and payload["client_secret"] == "":
        payload.pop("client_secret")
    saved = save_category_settings(db, "azure", payload)
    azure_auth.reload_credential(db)
    return {"category": "azure", "settings": saved, "message": "Azure settings saved."}


@app.post("/settings/database", tags=["Settings"],
          summary="Save database connection settings")
def save_database_settings(request: Request, body: DatabaseSettingsIn, db: Session = Depends(get_db)):
    require_admin_user(request)
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
    require_admin_user(request)
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
    require_admin_user(request)
    payload = body.model_dump(exclude_none=True)
    if "agent_token" in payload and payload["agent_token"] == "":
        payload.pop("agent_token")
    saved = save_category_settings(db, "kubernetes", payload)
    invalidate_runtime_config()
    return {"category": "kubernetes", "settings": saved, "message": "Kubernetes settings saved."}


@app.post("/settings/ai", tags=["Settings"],
          summary="Save Azure OpenAI settings for analysis enrichment")
def save_ai_settings(request: Request, body: AiSettingsIn, db: Session = Depends(get_db)):
    require_admin_user(request)
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
    require_admin_user(request)
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
    require_admin_user(request)
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
    require_admin_user(request)
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
    require_admin_user(request)
    try:
        result = apply_database_connection(db)
    except Exception as exc:
        raise HTTPException(400, f"Could not apply database connection: {exc}") from exc
    invalidate_runtime_config()
    return result


@app.post("/settings/reload", tags=["Settings"],
          summary="Reload Azure credentials from stored settings")
def reload_settings(request: Request, db: Session = Depends(get_db)):
    require_admin_user(request)
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
    if should_serve_spa(request, api_query_present=bool(subscription_id)):
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
    db_data, source = resolve_cost_db_then_live(
        db_call=lambda: daily_cost_response_from_db(db, subscription_id, **range_kw),
        live_call=lambda: query_daily_costs_live(
            db, subscription_id, token=token, **live_kw,
        ),
    )
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
    db_data = daily_cost_by_resource_group_from_db(
        db, subscription_id, resource_group, **range_kw,
    )
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


@app.get("/costs/by-resource", tags=["Cost Management"],
         summary="Cost per resource ID (database after sync)")
def get_costs_by_resource(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    resource_types:  Optional[str] = Query(None, description="Comma-separated canonical resource types"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, None, None, resource_types=resource_types)
    live_kw = live_range_kw(range_kw)
    token = _live_cost_token(db)

    def _live_by_resource() -> dict | None:
        if range_kw.get("resource_types"):
            return None
        return query_cost_by_resource_live(
            db, subscription_id, token=token, **live_kw,
        )

    db_data, source = resolve_cost_db_then_live(
        db_call=lambda: cost_by_resource_from_db(db, subscription_id, **range_kw),
        live_call=_live_by_resource,
    )
    if db_data:
        if source != "database":
            _enqueue_cost_sync(subscription_id, reason="live_fallback_by_resource")
        log.info(
            "cost_api.get_costs_by_resource",
            subscription_id=subscription_id,
            source=source,
            timeframe=timeframe,
            rows=len(db_data.get("properties", {}).get("rows", [])),
        )
        return {**db_data, "source": source}
    _enqueue_cost_sync(subscription_id, reason="no_synced_rows")
    log.info(
        "cost_api.get_costs_by_resource",
        subscription_id=subscription_id,
        source="database",
        timeframe=timeframe,
        note="no_synced_rows",
    )
    return empty_cost_by_resource_response()


@app.get("/costs/by-resource-type", tags=["Cost Management"],
         summary="MTD cost by ARM resource type (cost explorer worker)")
def get_costs_by_resource_type(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    resource_types:  Optional[str] = Query(None, description="Comma-separated canonical resource types"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, None, None, resource_types=resource_types)
    db_data = cost_by_resource_type_from_db(db, subscription_id, **range_kw)
    if db_data:
        log.info(
            "cost_api.get_costs_by_resource_type",
            subscription_id=subscription_id,
            source="database",
            timeframe=timeframe,
        )
        return db_data
    log.info(
        "cost_api.get_costs_by_resource_type",
        subscription_id=subscription_id,
        source="database",
        timeframe=timeframe,
        note="no_synced_rows",
    )
    return {
        "properties": {
            "columns": [
                {"name": "ResourceType"},
                {"name": "DisplayName"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [],
        },
        "billing_currency": "CAD",
        "source": "database",
        "sync_required": True,
    }


@app.get("/costs/by-service", tags=["Cost Management"],
         summary="Cost by Azure service (database after sync)")
def get_costs_by_service(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    from_date:       Optional[str] = Query(None),
    to_date:         Optional[str] = Query(None),
    resource_types:  Optional[str] = Query(None, description="Comma-separated canonical resource types"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, from_date, to_date, resource_types=resource_types)
    live_kw = live_range_kw(range_kw)
    token = _live_cost_token(db)
    db_data, source = resolve_cost_db_then_live(
        db_call=lambda: cost_by_service_from_db(db, subscription_id, **range_kw),
        live_call=lambda: query_cost_by_service_live(
            db, subscription_id, token=token, **live_kw,
        ),
    )
    if db_data:
        if source != "database":
            _enqueue_cost_sync(subscription_id, reason="live_fallback_by_service")
        log.info(
            "cost_api.get_costs_by_service",
            subscription_id=subscription_id,
            source=source,
            timeframe=timeframe,
        )
        return {**db_data, "source": source}
    _enqueue_cost_sync(subscription_id, reason="no_synced_rows")
    log.info(
        "cost_api.get_costs_by_service",
        subscription_id=subscription_id,
        source="database",
        timeframe=timeframe,
        note="no_synced_rows",
    )
    return empty_cost_by_service_response()


@app.get("/costs/summary", tags=["Cost Management"],
         summary="Subscription totals (database after sync)")
def get_costs_summary(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    from_date:       Optional[str] = Query(None),
    to_date:         Optional[str] = Query(None),
    resource_types:  Optional[str] = Query(None, description="Comma-separated canonical resource types"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, from_date, to_date, resource_types=resource_types)
    live_kw = live_range_kw(range_kw)
    token = _live_cost_token(db)
    db_summary, source = resolve_cost_db_then_live(
        db_call=lambda: cost_summary_from_db(db, subscription_id, **range_kw),
        live_call=lambda: query_cost_summary_live(
            db, subscription_id, token=token, **live_kw,
        ),
    )
    if db_summary:
        if source != "database":
            _enqueue_cost_sync(subscription_id, reason="live_fallback_summary")
        log.info(
            "cost_api.get_costs_summary",
            subscription_id=subscription_id,
            source=source,
            timeframe=timeframe,
        )
        return {
            "subscription_id": subscription_id,
            "timeframe": timeframe,
            "api_version": source or "database",
            **db_summary,
            "source": source,
            "fields": {
                "pretax_total": "Subscription MTD PreTaxCost from Azure (single query)",
                "cost_usd_total": "Subscription MTD CostUSD from Azure",
                "billing_currency": "Billing currency from Azure",
                "synced_at": "Last successful cost sync timestamp",
            },
        }
    _enqueue_cost_sync(subscription_id, reason="no_synced_rows")
    log.info(
        "cost_api.get_costs_summary",
        subscription_id=subscription_id,
        source="database",
        timeframe=timeframe,
        note="no_synced_rows",
    )
    empty = empty_cost_summary_response(**range_kw)
    return {
        "subscription_id": subscription_id,
        "timeframe": timeframe,
        "api_version": "database",
        **empty,
        "fields": {
            "pretax_total": "Sum of BilledCost per service (billing currency)",
            "cost_usd_total": "Sum of CostUSD per service",
            "billing_currency": "Billing currency from export",
        },
    }


@app.get("/costs/changes", tags=["Cost Management"],
         summary="MTD cost increases since the previous Fetch costs run")
def get_costs_changes(
    subscription_id: str = Query(...),
    month: Optional[str] = Query(None, description="YYYY-MM (defaults to current month)"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    data = get_latest_cost_changes(db, subscription_id, month)
    if not data:
        period = mtd_period_for_timeframe("MonthToDate")
        return {
            "subscription_id": subscription_id,
            "has_previous": False,
            "services": [],
            **period,
            "source": "database",
        }
    return {"subscription_id": subscription_id, **data}


@app.get("/costs/forecast", tags=["Cost Management"],
         summary="Forecast costs for the current billing period (admin, live Azure)")
def get_cost_forecast(
    request: Request,
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return cost_client.query_forecast(sub, timeframe)


# fix #5: always require admin auth for budget data, regardless of whether the
# result comes from cache or a live Azure call. Budget amounts are sensitive and
# should not be readable by viewer-role users via a cache hit.
@app.get("/costs/budgets", tags=["Cost Management"],
         summary="List all budgets configured on a subscription")
def get_budgets(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    subscription_id = _scoped_subscription(db, subscription_id)
    cached = list_budgets_from_db(db, subscription_id)
    if cached:
        return cached
    return cost_client.list_budgets(subscription_id)


# ══════════════════════════════════════════════════════════════════════════════
#  DASHBOARD API — PostgreSQL-backed (spec: azure_dashboard_advanced_backend)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/dashboard/overview", tags=["Dashboard"],
         summary="Full dashboard payload (costs from Azure Cost Management when available)")
def dashboard_overview(
    subscription_id: str = Query(...),
    timeframe: str = Query("MonthToDate"),
    resource_types: Optional[str] = Query(None, description="Comma-separated canonical resource types"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    from app.resource_type_catalog import parse_resource_types_param

    types = parse_resource_types_param(resource_types)
    return get_dashboard_overview(
        db, subscription_id, timeframe=timeframe, resource_types=types,
    )


@app.get("/resource-types", tags=["Resources"],
         summary="Canonical resource types grouped by category (for cost filters)")
def list_resource_types():
    from app.resource_type_catalog import resource_types_catalog

    return resource_types_catalog()


@app.get("/sync/status", tags=["Dashboard"],
         summary="Last sync status per data type (inventory, cost, analysis)")
def dashboard_sync_status(
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_sync_status(db, subscription_id)


@app.get("/resources/detail", tags=["Dashboard"],
         summary="Single resource detail by ARM ID (database)")
def dashboard_resource_detail(
    subscription_id: str = Query(...),
    resource_id: str = Query(..., description="Full ARM resource ID"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    detail = get_resource_detail(db, subscription_id, resource_id)
    if not detail:
        raise HTTPException(404, "Resource not found in synced inventory")
    return detail


@app.get("/cost/topspend", tags=["Dashboard"],
         summary="Top resources by month-to-date cost")
def dashboard_cost_topspend(
    subscription_id: str = Query(...),
    limit: int = Query(10, ge=1, le=100),
    timeframe: str = Query("MonthToDate"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_top_spend(db, subscription_id, limit=limit, timeframe=timeframe)


@app.get("/cost/daily", tags=["Dashboard"],
         summary="Daily cost series (alias for /costs)")
def dashboard_cost_daily(
    subscription_id: str = Query(...),
    timeframe: str = Query("MonthToDate"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    db_data = daily_cost_response_from_db(db, subscription_id, timeframe)
    if db_data:
        return db_data
    return empty_daily_cost_response()


@app.get("/advisor", tags=["Dashboard"],
         summary="Cost optimization recommendations (database)")
def dashboard_advisor(
    subscription_id: str = Query(...),
    limit: int = Query(50, ge=1, le=500),
    min_savings: float = Query(0.0, ge=0),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return list_advisor_recommendations(
        db, subscription_id, limit=limit, min_savings=min_savings,
    )


@app.get("/alerts", tags=["Dashboard"],
         summary="Synced metric alert rules")
def dashboard_monitor_alerts(
    subscription_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return list_monitor_alert_resources(db, subscription_id, limit=limit)


@app.get("/outliers/underutil", tags=["Dashboard"],
         summary="Top underutilized resources from open findings")
def dashboard_underutil_outliers(
    subscription_id: str = Query(...),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return list_underutil_outliers(db, subscription_id, limit=limit)


@app.get("/budgets", tags=["Dashboard"],
         summary="Budgets with current spend (database)")
def dashboard_budgets(
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return list_budgets_from_db(db, subscription_id)


@app.get("/costs/dimensions", tags=["Cost Management"],
         summary="Available Cost Management filter dimensions (admin, live Azure)")
def get_dimensions(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return cost_client.list_dimensions(sub)


# fix #6: omit internal DB primary key `r.id` from the API response — it leaks
# record counts and enables enumeration attacks.
@app.get("/costs/history", tags=["Cost Management"],
         summary="Synced cost records from PostgreSQL (scoped by subscription)")
def cost_history(
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    """Returns the 100 most recent synced CostRecord rows for the subscription."""
    sub = _scoped_subscription(db, subscription_id)
    records = (
        db.query(CostRecord)
        .filter(CostRecord.subscription_id == sub)
        .order_by(CostRecord.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "subscription_id": r.subscription_id,
            "resource_group": r.resource_group,
            "timeframe": r.timeframe,
            "granularity": r.granularity,
            "created_at": str(r.created_at),
        }
        for r in records
    ]


# fix #3: use _scoped_subscription instead of raw .strip().lower() so that
# trigger_cost_sync enforces the same format validation and deployment guard
# as every other cost endpoint.
@app.post("/costs/sync", tags=["Cost Management"],
          summary="Refresh Dashboard and Cost explorer costs (subscription + resource type)")
def trigger_cost_sync(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    require_admin_user(request)
    try:
        subscription_id = _scoped_subscription(db, subscription_id)
        log.info("cost_api.sync_start", subscription_id=subscription_id, source="azure_cost_management")
        synced = sync_costs(subscription_id, db, token)
        log.info("cost_api.sync_done", subscription_id=subscription_id, synced=synced)
        return {"status": "ok", "synced": synced, "source": "azure_cost_management"}
    except CostExportReadError as exc:
        log.error("cost_api.sync_read_failed", subscription_id=subscription_id, error=str(exc))
        raise _cost_api_http_error(exc) from exc
    except Exception as exc:
        log.exception("cost_sync_failed", subscription_id=subscription_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/resources/discovery/sync", tags=["Resources"],
          summary="Discover all subscription resources from ARM list API")
def trigger_resource_discovery_sync(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    require_admin_user(request)
    from app.resource_discovery_sync import sync_resource_discovery

    try:
        subscription_id = subscription_id.strip().lower()
        log.info("resource_discovery_api.sync_start", subscription_id=subscription_id)
        result = sync_resource_discovery(subscription_id, db, token)
        log.info("resource_discovery_api.sync_done", subscription_id=subscription_id, **{
            k: result.get(k) for k in ("total_listed", "synced_types", "unmapped_count")
        })
        return {"status": "ok", **result}
    except Exception as exc:
        log.exception("resource_discovery_sync_failed", subscription_id=subscription_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/resources/cost-audit", tags=["Resources"],
         summary="Cost-bearing resource types (skips free unmapped types)")
def get_resource_cost_audit(
    request: Request,
    subscription_id: str = Query(...),
    live: bool = Query(False, description="When true, list ARM resources and join with synced MTD costs"),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    """Return billable ARM types first; free unmapped resources are omitted from gaps."""
    require_admin_user(request)
    from app.auth import arm_auth_context
    from app.azure_resources import AzureResourcesClient
    from app.http_client import arm_patient_sync
    from app.resource_cost_audit import audit_from_arm_items, audit_from_cost_db

    subscription_id = subscription_id.strip().lower()
    if live:
        with arm_auth_context(db=db, token=token):
            client = AzureResourcesClient(db=db)
            with arm_patient_sync():
                items = client.list_resources(subscription_id)
        audit = audit_from_arm_items(db, subscription_id, items)
        audit["source"] = "arm_resources_list"
    else:
        audit = audit_from_cost_db(db, subscription_id)
    return {"status": "ok", **audit}


@app.get(
    "/resources/azure-service-cost-catalog",
    tags=["Resources"],
    summary="Azure services and resource types with cost classification",
)
def get_azure_service_cost_catalog(request: Request):
    """Return costed vs free classification for Azure services and ARM types."""
    require_admin_user(request)
    from app.azure_service_cost_catalog import (
        arm_type_catalog_rows,
        canonical_type_catalog_rows,
        catalog_aliases,
        catalog_metadata,
        catalog_table_rows,
    )
    from app.free_tier_reference import official_free_services_catalog, reference_metadata
    from app.resource_pricing import sku_pricing_table_rows

    return {
        "status": "ok",
        "catalog": catalog_metadata(),
        "free_tier_reference": reference_metadata(),
        "official_free_services": official_free_services_catalog(),
        "cost_types": {
            "costed": "Directly billable when deployed; shown on dashboard when inventory exists.",
            "free": "No Azure charge for this resource type.",
            "conditional": "Billable meters exist but base resource is often $0; shown when MTD spend > 0.",
        },
        "pricing_models": {
            "always_free": "No charge for this SKU or resource type.",
            "pay_as_you_go": "Consumption-based hourly/unit metering.",
            "free_tier_limited": "Free SKU or allowance with paid upgrade path.",
            "free_tier_monthly": "Recurring monthly free allowance (e.g. 5 GB ingestion).",
            "free_tier_12_months": "Free allowance for 12 months on new Azure accounts.",
            "hybrid": "Base resource or operations free; specific features or overages bill.",
            "reserved_capable": "Pay-as-you-go with reservation pricing available.",
        },
        "free_tier_durations": {
            "always": "Perpetual free allowance or free SKU.",
            "12_months_new_account": "Included with Azure free account for first 12 months.",
            "30_days_new_account": "Covered by USD 200 credit during first 30 days of a new Azure account.",
            "trial": "Time-limited trial SKU or evaluation period; bills at paid rates after trial.",
            "none": "No free tier.",
        },
        "services": catalog_table_rows(),
        "aliases": catalog_aliases(),
        "service_free_tiers": {
            row["service_name"]: row["free_tier"]
            for row in catalog_table_rows()
            if row.get("free_tier")
        },
        "sku_tiers": sku_pricing_table_rows(),
        "canonical_types": canonical_type_catalog_rows(),
        "arm_types": arm_type_catalog_rows(),
    }


@app.get(
    "/resources/pricing-profiles",
    tags=["Resources"],
    summary="Per-resource SKU and pricing model profiles",
)
def get_resource_pricing_profiles(
    request: Request,
    subscription_id: str = Query(...),
    resource_type: str | None = Query(None, description="Canonical resource type filter"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List resolved SKU and pricing model for each synced resource."""
    require_admin_user(request)
    from app.resource_pricing import list_pricing_profiles_db

    return {
        "status": "ok",
        **list_pricing_profiles_db(
            db,
            subscription_id,
            canonical_type=resource_type,
            limit=limit,
            offset=offset,
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  RESOURCES — COMPUTE
# ══════════════════════════════════════════════════════════════════════════════

def _db_or_live(
    subscription_id: str,
    db: Session,
    resource_type: str,
    live_fn,
    # fix #2: Literal type here makes _db_or_live itself correct, but FastAPI
    # generates 422 validation only when the individual route handler's Query
    # param also carries the Literal annotation. Each route below uses
    # `source: Literal["db", "live"] = Query("db")` for this reason.
    source: Literal["db", "live"] = "db",
    *,
    request: Request,
    limit: int | None = None,
    offset: int = 0,
):
    """DB reads by default; live ARM only for admins with source=live."""
    subscription_id = _scoped_subscription(db, subscription_id)

    if source == "live":
        require_admin_user(request)
        return fetch_live_resources(
            subscription_id, db, resource_client, resource_type, live_fn,
            limit=limit, offset=offset,
        )

    include_properties = request.query_params.get("include_properties", "").lower() in {"1", "true", "yes"}
    if "include_properties" not in request.query_params and resource_type in {
        "containers/aks", "network/vnet", "network/appgateway", "network/privateendpoint",
        "network/privatelinkservice", "network/privatedns",
        "appservice/webapp", "appservice/plan",
    }:
        include_properties = True

    from app.cost_db import resource_cost_map_from_db
    from app.perf_cache import cached_cost_map

    cost_map = cached_cost_map(
        f"cost_map:{subscription_id.lower()}",
        lambda: resource_cost_map_from_db(db, subscription_id),
    )

    if limit is not None:
        return get_resources_db_page(
            db, subscription_id, resource_type,
            limit=limit, offset=offset,
            include_properties=include_properties,
            cost_map=cost_map,
        )
    return get_resources_db(
        db, subscription_id, resource_type,
        include_properties=include_properties,
        cost_map=cost_map,
    )


@app.get("/resources/counts", tags=["Resources"],
         summary="Resource counts by category (single DB query for dashboard)")
def resource_counts(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return get_resource_counts(db, _scoped_subscription(db, subscription_id))


@app.get("/resources/from-cost", tags=["Resources"],
         summary="Azure inventory merged with MTD costs (lazy-loaded)")
def list_resources_from_cost(
    subscription_id: str = Query(...),
    limit: int | None = Query(None, ge=1, le=200, description="Page size for lazy loading"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    if limit is not None:
        return list_billed_resources_page(db, subscription_id, limit=limit, offset=offset)
    return list_cost_resources_db(db, subscription_id)


@app.get("/resources/billed", tags=["Resources"],
         summary="Azure inventory merged with MTD costs (paginated)")
def list_billed_resources(
    subscription_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return list_billed_resources_page(db, subscription_id, limit=limit, offset=offset)


@app.get("/resources/billed/properties", tags=["Resources"],
         summary="Lazy-load ARM properties for a billed resource")
def get_billed_resource_properties(
    resource_id: str = Query(..., description="Full ARM resource ID"),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    from app.arm_resource_probe import probe_billed_resource

    subscription_id = _scoped_subscription(db, subscription_id)
    try:
        return probe_billed_resource(db, subscription_id, resource_id, token)
    except Exception as exc:
        log.exception("billed_resource_probe_failed", resource_id=resource_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── Resource type endpoints — fix #2 applied: each handler declares
# `source: Literal["db", "live"] = Query("db")` so FastAPI generates a 422
# when any value other than "db" or "live" is supplied by the caller.

@app.get("/resources/vms", tags=["Compute"],
         summary="Virtual machines (database or live ARM)")
def list_vms(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    standalone_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    result = _db_or_live(
        subscription_id, db, "compute/vm",
        lambda sub, tok: resource_client.list_vms(sub),
        source, request=request, limit=limit, offset=offset,
    )
    if standalone_only and isinstance(result, list):
        result = filter_standalone_vms(result)
    return result


@app.get("/resources/disks", tags=["Compute"],
         summary="Managed disks (database or live ARM)")
def list_disks(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "compute/disk",
        lambda sub, tok: resource_client.list_disks(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.get("/resources/snapshots", tags=["Compute"],
         summary="Disk snapshots (database or live ARM)")
def list_snapshots(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "compute/snapshot",
        lambda sub, tok: resource_client.list_snapshots(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.get("/resources/images", tags=["Compute"],
         summary="Custom VM images (database or live ARM)")
def list_images(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "compute/image",
        lambda sub, tok: resource_client.list_images(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.get("/resources/aks", tags=["Containers"],
         summary="AKS clusters (database or live ARM)")
def list_aks(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "containers/aks",
        lambda sub, tok: resource_client.list_aks_clusters(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.get("/resources/storage", tags=["Storage"],
         summary="Storage accounts (database or live ARM)")
def list_storage(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "storage/account",
        lambda sub, tok: resource_client.list_storage_accounts(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.get("/resources/vnets", tags=["Network"],
         summary="Virtual networks (database or live ARM)")
def list_vnets(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/vnet",
        lambda sub, tok: resource_client.list_vnets(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.get("/resources/public-ips", tags=["Network"],
         summary="Public IP addresses (database or live ARM)")
def list_public_ips(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/publicip",
        lambda sub, tok: resource_client.list_public_ips(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.get("/resources/load-balancers", tags=["Network"],
         summary="Load balancers (database or live ARM)")
def list_load_balancers(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/loadbalancer",
        lambda sub, tok: resource_client.list_load_balancers(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.get("/resources/app-gateways", tags=["Network"],
         summary="Application gateways (database or live ARM)")
def list_app_gateways(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/appgateway",
        lambda sub, tok: resource_client.list_app_gateways(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.get("/resources/sql-servers", tags=["Databases"],
         summary="SQL servers (database or live ARM)")
def list_sql_servers(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "database/sql",
        lambda sub, tok: resource_client.list_sql_servers(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.get("/resources/cosmos", tags=["Databases"],
         summary="Cosmos DB accounts (database or live ARM)")
def list_cosmos(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "database/cosmos",
        lambda sub, tok: resource_client.list_cosmos_accounts(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.get("/resources/key-vaults", tags=["Security"],
         summary="Key vaults (database or live ARM)")
def list_key_vaults(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "security/keyvault",
        lambda sub, tok: resource_client.list_key_vaults(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.get("/resources/web-apps", tags=["App Service"],
         summary="App Service web apps (database or live ARM)")
def list_web_apps(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "appservice/webapp",
        lambda sub, tok: resource_client.list_web_apps(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.get("/resources/app-service-plans", tags=["App Service"],
         summary="App Service plans (database or live ARM)")
def list_app_service_plans(
    request: Request,
    subscription_id: str = Query(...),
    source: Literal["db", "live"] = Query("db"),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "appservice/plan",
        lambda sub, tok: resource_client.list_app_service_plans(sub),
        source, request=request, limit=limit, offset=offset,
    )


@app.patch("/resources/{resource_id:path}/tags", tags=["Resources"],
           summary="Update Azure resource tags (admin)")
def patch_resource_tags(
    request: Request,
    resource_id: str = Path(..., description="Full ARM resource ID"),
    body: ResourceTagsIn = ...,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    from app.http_client import AzureAPIError
    from app.models import ResourceSnapshot

    require_admin_user(request)
    sub = _scoped_subscription(db, subscription_id)
    rid = (resource_id or "").strip()
    if not rid.startswith("/"):
        rid = f"/{rid}"
    rid_lower = rid.lower()
    if sub not in rid_lower:
        raise HTTPException(400, "resource_id does not match subscription_id")

    tags = {str(k): str(v) for k, v in (body.tags or {}).items()}
    try:
        arm_result = resource_client.patch_resource_tags(rid, tags, db=db)
    except AzureAPIError as exc:
        raise HTTPException(status_code=exc.status or 502, detail=exc.message) from exc

    row = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.resource_id == rid_lower,
        )
        .first()
    )
    if row:
        row.tags_json = json.dumps(tags)
        db.commit()

    return {
        "resource_id": rid,
        "tags": arm_result.get("tags") or tags,
        "updated": True,
    }

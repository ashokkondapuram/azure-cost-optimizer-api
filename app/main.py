"""Azure Cost Optimizer — Production API v5.0

Includes:
  - Full Cost Management API (v2024-08-01)
  - All resource type endpoints (Compute, AKS, Storage, Network, DB, Security)
  - Optimization Engine with configurable rules + profiles
  - Engine config CRUD (enable/disable rules, override thresholds per profile)
  - Finding history + remediation status tracking
"""
import uuid
import json
import os
import secrets
import structlog
from fastapi import FastAPI, HTTPException, Query, Depends, Path, BackgroundTasks, Header, Body, Request
from app.middleware.dynamic_cors import DynamicCORSMiddleware
from app.middleware.app_auth import AppAuthMiddleware
from app.http_cache import cache_control_middleware
from app.runtime_config import invalidate_runtime_config, get_runtime_status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Any, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
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
from datetime import datetime, timezone

Base.metadata.create_all(bind=engine)
migrate_schema()
settings = get_settings()
configure_logging(
    level=settings.log_level,
    json_logs=settings.is_production,
)
if settings.is_production:
    settings.validate_startup()
log = structlog.get_logger()
log.info(
    "app.startup",
    app_env=settings.app_env,
    log_level=settings.log_level,
    production=settings.is_production,
)

app = FastAPI(
    title="InfinityOps API",
    version="5.0.0",
    description="API for Azure cost, inventory, and optimization.",
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


@app.on_event("startup")
def bootstrap_settings():
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
    from app.database import SessionLocal

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


class K8sSnapshotIn(BaseModel):
    cluster_name: str = Field(..., min_length=1, max_length=253)
    collected_at: Optional[str] = None
    summary: dict = Field(default_factory=dict)
    nodes: list = Field(default_factory=list, max_length=500)
    pods: list = Field(default_factory=list, max_length=5000)


def _scoped_subscription(db: Session, subscription_id: str) -> str:
    """Validate format and ensure subscription belongs to this deployment."""
    return ensure_subscription_known(db, subscription_id)


def _cost_range_kwargs(
    timeframe: str,
    from_date: str | None,
    to_date: str | None,
    *,
    resource_types: str | None = None,
) -> dict:
    kw: dict = {"timeframe": timeframe}
    if (from_date or "").strip():
        kw["from_date"] = from_date.strip()[:10]
    if (to_date or "").strip():
        kw["to_date"] = to_date.strip()[:10]
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


def _verify_k8s_agent_token(
    api_key: Optional[str] = None,
    db: Optional[Session] = None,
) -> None:
    k8s_cfg = get_system_config(db, "kubernetes") if db is not None else {}
    expected = k8s_cfg.get("agent_token") or settings.k8s_agent_token
    require = bool(k8s_cfg.get("require_agent_token") or settings.require_k8s_token)
    if settings.is_production and not expected:
        raise HTTPException(status_code=503, detail="K8s agent authentication is not configured")
    if require and not expected:
        raise HTTPException(status_code=503, detail="K8s agent authentication is not configured")
    if not expected:
        if settings.auth_enabled:
            raise HTTPException(status_code=503, detail="K8s agent authentication is not configured")
        return
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
    return {"status": "ok", "version": "5.0.0"}


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

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

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


@app.get("/costs/budgets", tags=["Cost Management"],
         summary="List all budgets configured on a subscription")
def get_budgets(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    cached = list_budgets_from_db(db, subscription_id)
    if cached:
        return cached
    require_admin_user(request)
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


@app.get("/costs/history", tags=["Cost Management"],
         summary="Audit log of cost queries from PostgreSQL (scoped by subscription)")
def cost_history(
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    sub = _scoped_subscription(db, subscription_id)
    records = (
        db.query(CostRecord)
        .filter(CostRecord.subscription_id == sub)
        .order_by(CostRecord.created_at.desc())
        .limit(100)
        .all()
    )
    return [{"id": r.id, "subscription_id": r.subscription_id,
             "resource_group": r.resource_group, "timeframe": r.timeframe,
             "granularity": r.granularity, "created_at": str(r.created_at)}
            for r in records]


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
        subscription_id = subscription_id.strip().lower()
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
    source: str = "db",
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
            cost_map=cost_map,
            include_properties=include_properties,
        )
    return get_resources_db(
        db, subscription_id, resource_type,
        cost_map=cost_map,
        include_properties=include_properties,
        limit=limit,
        offset=offset,
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


@app.patch("/resources/bulk-tags", tags=["Resources"],
           summary="Apply the same tags to multiple resources (admin)")
def bulk_resource_tags(
    request: Request,
    body: BulkResourceTagsIn,
    db: Session = Depends(get_db),
):
    from app.http_client import AzureAPIError
    from app.models import ResourceSnapshot
    from app.validators import ensure_subscription_known, require_subscription_id

    require_admin_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(body.subscription_id))
    tags = {str(k): str(v) for k, v in (body.tags or {}).items()}
    if not tags:
        raise HTTPException(400, "tags are required")

    updated = []
    errors = []
    for raw_id in body.resource_ids:
        rid = (raw_id or "").strip()
        if not rid.startswith("/"):
            rid = f"/{rid}"
        rid_lower = rid.lower()
        if sub not in rid_lower:
            errors.append({"resource_id": rid, "error": "subscription mismatch"})
            continue
        try:
            arm_result = resource_client.patch_resource_tags(rid, tags, db=db)
            row = (
                db.query(ResourceSnapshot)
                .filter(
                    ResourceSnapshot.subscription_id == sub,
                    ResourceSnapshot.resource_id == rid_lower,
                )
                .first()
            )
            if row:
                row.tags_json = json.dumps(arm_result.get("tags") or tags)
            updated.append(rid_lower)
        except AzureAPIError as exc:
            errors.append({"resource_id": rid, "error": exc.message})

    if updated:
        db.commit()

    return {
        "updated": len(updated),
        "resource_ids": updated,
        "errors": errors,
    }


@app.post("/resources/sync", tags=["Resources"],
          summary="Pull fresh Azure inventory and costs into the local database")
def trigger_resource_sync(
    request: Request,
    background_tasks: BackgroundTasks,
    subscription_id: str = Query(...),
    types: Optional[str] = Query(
        None,
        description="Comma-separated canonical types or API paths (scoped sync). Omit for full inventory.",
    ),
    include_costs: bool = Query(
        False,
        description="Sync cost export after scoped inventory. Full sync always includes costs.",
    ),
    components: Optional[str] = Query(
        None,
        description="Comma-separated optimization components for scoped analysis after sync",
    ),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    require_admin_user(request)
    try:
        subscription_id = subscription_id.strip().lower()
        type_list = None
        if types:
            type_list = [t.strip() for t in types.split(",") if t.strip()]
            synced = sync_scoped(
                subscription_id,
                db,
                token,
                type_list,
                include_costs=include_costs,
            )
        else:
            synced = sync_all(subscription_id, db, token)
        analysis = queue_post_sync_analysis(
            db,
            background_tasks,
            subscription_id=subscription_id,
            type_list=type_list,
            components=components,
        )
        return {"status": "ok", "synced": synced, "analysis": analysis}
    except Exception as exc:
        log.exception("sync_failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/admin/data/clear", tags=["Admin"],
          summary="Clear synced inventory, costs, findings, and runs (admin only)")
def clear_database_data(
    request: Request,
    subscription_id: Optional[str] = Query(
        None,
        description="Clear one subscription only; omit to clear all synced data",
    ),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    try:
        return {"status": "ok", **clear_synced_data(db, subscription_id=subscription_id)}
    except Exception as exc:
        log.exception("db_clear_failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/resources/all", tags=["Resources"],
         summary="List all resources with optional type filter (DB-first)")
def all_resources(
    request: Request,
    subscription_id: str = Query(...),
    resource_type:   Optional[str] = Query(None, description="e.g. compute/vm"),
    source:          str = Query("db", description="db (default) or live"),
    db:              Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    if source == "live":
        require_admin_user(request)
        arm_type = None
        if resource_type:
            _arm_map = {
                "compute/vm": "Microsoft.Compute/virtualMachines",
                "compute/vmss": "Microsoft.Compute/virtualMachineScaleSets",
                "compute/disk": "Microsoft.Compute/disks",
            }
            arm_type = _arm_map.get(resource_type, resource_type)
        return resource_client.list_resources(subscription_id, arm_type)
    return list_all_resources_db(db, subscription_id, resource_type)


@app.get("/resources/subscriptions", tags=["Resources"],
         summary="List subscriptions from database (cache + synced data)")
def list_subscriptions(db: Session = Depends(get_db)):
    from app.subscription_store import list_subscriptions_db
    return list_subscriptions_db(db)


@app.post("/resources/subscriptions/sync", tags=["Resources"],
          summary="Refresh subscription list from Azure into the database (admin)")
def refresh_subscriptions(
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.subscription_store import list_subscriptions_db, sync_subscription_catalog
    try:
        count = sync_subscription_catalog(db)
        return {
            "status": "ok",
            "synced": count,
            "subscriptions": list_subscriptions_db(db),
        }
    except Exception as exc:
        log.exception("subscription_sync_failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/resources/resource-groups", tags=["Resources"],
         summary="List resource groups in a subscription (admin, live Azure)")
def list_resource_groups(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_resource_groups(sub)


@app.get("/resources/vms", tags=["Compute"],
         summary="Virtual machines (DB-first; source=live for ARM)")
def list_vms(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "compute/vm",
        lambda: filter_standalone_vms(
            resource_client.list_vms(subscription_id, include_instance_view=False),
        ),
        source,
        request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/vmss", tags=["Compute"],
         summary="Virtual machine scale sets (DB-first; source=live for ARM)")
def list_vmss(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "compute/vmss",
        lambda: resource_client.list_vm_scale_sets(subscription_id),
        source,
        request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/vms/{resource_group}/{vm_name}", tags=["Compute"],
         summary="Single VM with instanceView (power state, extensions, OS)")
def get_vm(
    request: Request,
    resource_group: str = Path(...),
    vm_name:        str = Path(...),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.get_vm(sub, resource_group, vm_name)


@app.get("/resources/vms/{resource_group}/{vm_name}/sizing", tags=["Compute"],
         summary="VM CPU/memory utilization and SKU rightsizing recommendation")
def get_vm_sizing(
    request: Request,
    resource_group: str = Path(...),
    vm_name: str = Path(...),
    subscription_id: str = Query(...),
    timespan: str = Query("P7D", description="Azure Monitor lookback e.g. P7D, P30D"),
    db: Session = Depends(get_db),
):
    from app.vm_sizing import parse_vm_sku
    from app.vm_sizing_persist import compute_vm_sizing_recommendation
    from app.cost_db import resource_cost_map_from_db
    from app.cost_utils import resource_cost_billing_from_map

    sub = _require_admin_live_arm(request, db, subscription_id)
    vm = resource_client.get_vm(sub, resource_group, vm_name)
    props = vm.get("properties") or {}
    sku = (props.get("hardwareProfile") or {}).get("vmSize") or ""
    location = vm.get("location") or ""
    catalog = resource_client.list_vm_sizes(sub, location) if location else []
    catalog_entry = next((row for row in catalog if row.get("name") == sku), None)
    parsed = parse_vm_sku(sku, catalog_entry=catalog_entry)

    metrics: dict = {}
    rid = vm.get("id") or ""
    if rid:
        try:
            metrics = resource_client.get_vm_cpu_metrics(rid, timespan) or {}
        except Exception as exc:
            log.warning("vm_sizing.metrics_failed", vm=vm_name, error=str(exc))

    rule_overrides = get_effective_config(db, "default")
    cost_map = resource_cost_map_from_db(db, sub)
    monthly_cost = resource_cost_billing_from_map(cost_map, rid)
    util, recommendation, pricing = compute_vm_sizing_recommendation(
        vm=vm,
        catalog=catalog,
        metrics=metrics,
        timespan=timespan,
        rule_overrides=rule_overrides,
        monthly_cost=monthly_cost,
    )

    return {
        "subscription_id": sub,
        "resource_id": rid,
        "resource_name": vm_name,
        "resource_group": resource_group,
        "location": location,
        "current_sku": sku,
        "sku_profile": {
            "family": parsed.family if parsed else None,
            "family_label": parsed.family_label if parsed else None,
            "vcpus": parsed.vcpus if parsed else None,
            "memory_gb": parsed.memory_gb if parsed else None,
            "variant": parsed.variant if parsed else None,
            "version": parsed.version if parsed else None,
        } if parsed else None,
        "utilization": util.as_dict(),
        "recommendation": recommendation.as_dict() if recommendation else None,
        "pricing": pricing,
        "timespan": timespan,
    }


@app.post("/resources/vms/{resource_group}/{vm_name}/sizing/open-finding", tags=["Compute"],
          summary="Persist live VM sizing recommendation as an open optimization finding")
def persist_vm_sizing_open_finding(
    request: Request,
    resource_group: str = Path(...),
    vm_name: str = Path(...),
    subscription_id: str = Query(...),
    timespan: str = Query("P7D", description="Azure Monitor lookback e.g. P7D, P30D"),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.validators import ensure_subscription_known, validate_subscription_id
    from app.vm_sizing_persist import compute_vm_sizing_recommendation, upsert_vm_sizing_open_finding

    sub = ensure_subscription_known(db, validate_subscription_id(subscription_id))
    vm = resource_client.get_vm(sub, resource_group, vm_name)
    location = vm.get("location") or ""
    catalog = resource_client.list_vm_sizes(sub, location) if location else []

    metrics: dict = {}
    rid = vm.get("id") or ""
    if rid:
        try:
            metrics = resource_client.get_vm_cpu_metrics(rid, timespan) or {}
        except Exception as exc:
            log.warning("vm_sizing.metrics_failed", vm=vm_name, error=str(exc))

    rule_overrides = get_effective_config(db, "default")
    from app.cost_db import resource_cost_map_from_db
    from app.cost_utils import resource_cost_billing_from_map

    cost_map = resource_cost_map_from_db(db, sub)
    monthly_cost = resource_cost_billing_from_map(cost_map, rid)
    util, recommendation, pricing = compute_vm_sizing_recommendation(
        vm=vm,
        catalog=catalog,
        metrics=metrics,
        timespan=timespan,
        rule_overrides=rule_overrides,
        monthly_cost=monthly_cost,
    )
    if not recommendation or not recommendation.suggested_sku or recommendation.action not in {"downgrade", "cross_family", "upgrade"}:
        raise HTTPException(404, "No VM rightsizing recommendation available for this VM.")

    vm_metrics = {rid.lower(): metrics} if rid and metrics else {}
    row = upsert_vm_sizing_open_finding(
        db,
        subscription_id=sub,
        vm=vm,
        recommendation=recommendation.as_dict(),
        utilization=util.as_dict(),
        pricing=pricing,
        monthly_cost=monthly_cost or 0.0,
        rule_overrides=rule_overrides,
        vm_metrics=vm_metrics,
    )
    if not row:
        raise HTTPException(422, "Could not create an open finding from the sizing recommendation.")

    evidence = json.loads(row.evidence_json or "{}")
    return enrich_finding_for_api({
        "id": row.id,
        "run_id": row.run_id,
        "rule_id": row.rule_id,
        "rule_name": row.rule_name,
        "category": row.category,
        "severity": row.severity,
        "resource_id": row.resource_id,
        "resource_name": row.resource_name,
        "resource_type": row.resource_type,
        "resource_group": row.resource_group,
        "location": row.location,
        "detail": row.detail,
        "recommendation": row.recommendation,
        "estimated_savings_usd": row.estimated_savings_usd,
        "annualized_savings_usd": row.annualized_savings_usd,
        "waste_score": row.waste_score,
        "confidence_score": row.confidence_score,
        "action_priority": row.action_priority,
        "impact": row.impact,
        "evidence": evidence,
        "status": row.status,
        "detected_at": str(row.detected_at),
        "resolved_at": str(row.resolved_at) if row.resolved_at else None,
    })


@app.get("/resources/vm-skus", tags=["Compute"],
         summary="All VM SKUs in a region — vCPUs, memory, max disks, capabilities (Resource SKUs API 2021-07-01)")
def list_vm_skus(
    request: Request,
    subscription_id: str = Query(...),
    location:        str = Query(..., description="Azure region e.g. eastus, westeurope"),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_vm_skus(sub, location)


@app.get("/resources/vm-sizes", tags=["Compute"],
         summary="VM sizes in a location — core count and memory (Compute API 2024-03-01)")
def list_vm_sizes(
    request: Request,
    subscription_id: str = Query(...),
    location:        str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_vm_sizes(sub, location)


@app.get("/resources/disks", tags=["Compute"],
         summary="Managed disks (DB-first; source=live for ARM)")
def list_disks(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "compute/disk",
        lambda: resource_client.list_disks(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/snapshots", tags=["Compute"],
         summary="Disk snapshots (DB-first; source=live for ARM)")
def list_snapshots(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "compute/snapshot",
        lambda: resource_client.list_snapshots(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  RESOURCES — KUBERNETES / AKS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/resources/aks", tags=["Kubernetes"],
         summary="AKS clusters (DB-first; source=live for ARM)")
def list_aks(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    if source == "live":
        require_admin_user(request)

        def _fetch_aks() -> list:
            clusters = resource_client.list_aks_clusters(subscription_id)
            return enrich_aks_arm_clusters(resource_client, subscription_id, clusters)

        return fetch_live_resources(
            subscription_id, db, resource_client, "containers/aks", _fetch_aks,
            limit=limit, offset=offset,
        )

    # Version/Network columns need kubernetesVersion & networkProfile from properties_json.
    include_properties = request.query_params.get("include_properties", "").lower() in {"1", "true", "yes"}
    if "include_properties" not in request.query_params:
        include_properties = True

    from app.cost_db import resource_cost_map_from_db
    from app.perf_cache import cached_cost_map

    cost_map = cached_cost_map(
        f"cost_map:{subscription_id.lower()}",
        lambda: resource_cost_map_from_db(db, subscription_id),
    )

    if limit is not None:
        return get_resources_db_page(
            db, subscription_id, "containers/aks",
            limit=limit, offset=offset,
            cost_map=cost_map,
            include_properties=include_properties,
        )
    return get_aks_clusters_db(db, subscription_id)


@app.get("/resources/aks/{resource_group}/{cluster_name}", tags=["Kubernetes"],
         summary="Single AKS cluster detail (admin, live Azure)")
def get_aks_cluster(
    request: Request,
    resource_group: str = Path(...),
    cluster_name:   str = Path(...),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.get_aks_cluster(sub, resource_group, cluster_name)


@app.get("/resources/aks/{resource_group}/{cluster_name}/node-pools", tags=["Kubernetes"],
         summary="AKS node pools (agent pools) for a cluster (admin, live Azure)")
def list_aks_node_pools(
    request: Request,
    resource_group: str = Path(...),
    cluster_name:   str = Path(...),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_aks_node_pools(sub, resource_group, cluster_name)


@app.get("/resources/aks/{resource_group}/{cluster_name}/upgrades", tags=["Kubernetes"],
         summary="Available Kubernetes version upgrades for a cluster (admin, live Azure)")
def get_aks_upgrades(
    request: Request,
    resource_group: str = Path(...),
    cluster_name:   str = Path(...),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_aks_upgrades(sub, resource_group, cluster_name)


@app.get("/resources/aks/kubernetes-versions", tags=["Kubernetes"],
         summary="Supported Kubernetes versions for an Azure region (live ARM)")
def list_aks_kubernetes_versions(
    request: Request,
    subscription_id: str = Query(...),
    location: str = Query(..., description="Azure region name, e.g. eastus"),
    refresh: bool = Query(False, description="Bypass cache and fetch from Azure"),
    db: Session = Depends(get_db),
):
    """Returns full version metadata from Azure Container Service for the region."""
    require_admin_user(request)
    from app.aks_versions import fetch_kubernetes_versions_for_location
    return fetch_kubernetes_versions_for_location(
        subscription_id.lower(),
        location,
        db=db,
        force_refresh=refresh,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  RESOURCES — STORAGE / WEB / DATABASE / NETWORKING / SECURITY
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/resources/storage", tags=["Storage"], summary="Storage accounts (DB-first)")
def list_storage(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "storage/account",
        lambda: resource_client.list_storage_accounts(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/appservices", tags=["App Services"], summary="Web/Function apps (DB-first)")
def list_appservices(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "appservice/webapp",
        lambda: resource_client.list_app_services(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/appserviceplans", tags=["App Services"], summary="App Service plans (DB-first)")
def list_asp(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "appservice/plan",
        lambda: resource_client.list_app_service_plans(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/sql", tags=["Databases"], summary="SQL Servers (DB-first)")
def list_sql(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "database/sql",
        lambda: resource_client.list_sql_servers(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/sql/{resource_group}/{server_name}/databases", tags=["Databases"],
         summary="Databases on a SQL Server (admin, live Azure)")
def list_sql_databases(
    request: Request,
    resource_group: str = Path(...),
    server_name: str = Path(...),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_sql_databases(sub, resource_group, server_name)


@app.get("/resources/postgresql", tags=["Databases"], summary="PostgreSQL Flexible Servers (DB-first)")
def list_postgresql(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "database/postgresql",
        lambda: resource_client.list_postgresql_flexible(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/mysql", tags=["Databases"], summary="MySQL Flexible Servers (admin, live Azure)")
def list_mysql(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_mysql_flexible(sub)


@app.get("/resources/cosmosdb", tags=["Databases"], summary="Cosmos DB accounts (DB-first)")
def list_cosmosdb(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "database/cosmosdb",
        lambda: resource_client.list_cosmosdb(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/publicips", tags=["Networking"], summary="Public IPs (DB-first)")
def list_publicips(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/publicip",
        lambda: resource_client.list_public_ips(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/vnets", tags=["Networking"], summary="Virtual networks (DB-first)")
def list_vnets(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/vnet",
        lambda: resource_client.list_vnets(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/nics", tags=["Networking"], summary="Network interfaces (DB-first)")
def list_nics(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/nic",
        lambda: resource_client.list_network_interfaces(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/natgateways", tags=["Networking"], summary="NAT gateways (DB-first)")
def list_nat_gateways(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/nat",
        lambda: resource_client.list_nat_gateways(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/redis", tags=["Databases"], summary="Azure Cache for Redis (DB-first)")
def list_redis(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "database/redis",
        lambda: resource_client.list_redis_caches(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/loadbalancers", tags=["Networking"], summary="Load Balancers (DB-first)")
def list_lbs(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/loadbalancer",
        lambda: resource_client.list_load_balancers(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/appgateways", tags=["Networking"], summary="Application Gateways (DB-first)")
def list_agws(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/appgateway",
        lambda: resource_client.list_application_gateways(subscription_id),
        source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/nsgs", tags=["Networking"], summary="Network Security Groups (DB-first)")
def list_nsgs(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/nsg",
        lambda: resource_client.list_network_security_groups(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/privateendpoints", tags=["Networking"], summary="Private endpoints (DB-first)")
def list_private_endpoints(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/privateendpoint",
        lambda: resource_client.list_private_endpoints(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/privatelinkservices", tags=["Networking"], summary="Private link services (DB-first)")
def list_private_link_services(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/privatelinkservice",
        lambda: resource_client.list_private_link_services(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/privatedns", tags=["Networking"], summary="Private DNS zones (DB-first)")
def list_private_dns_zones(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/privatedns",
        lambda: resource_client.list_private_dns_zones(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/keyvaults", tags=["Security"], summary="Key Vaults (DB-first)")
def list_kvs(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "security/keyvault",
        lambda: resource_client.list_keyvaults(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@app.get("/resources/acr", tags=["Containers"], summary="Container Registries (DB-first)")
def list_acr(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "containers/acr",
        lambda: resource_client.list_container_registries(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


def _inventory_type_list_handler(canonical_type: str):
    def handler(
        request: Request,
        subscription_id: str = Query(...),
        source: str = Query("db"),
        limit: Optional[int] = Query(None, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
    ):
        return _db_or_live(
            subscription_id,
            db,
            canonical_type,
            lambda: [],
            source,
            request=request,
            limit=limit,
            offset=offset,
        )

    return handler


from app.resource_page_registry import inventory_pages as _inventory_pages  # noqa: E402

for _page in _inventory_pages():
    app.add_api_route(
        f"/resources/{_page.api_slug}",
        _inventory_type_list_handler(_page.canonical_type),
        methods=["GET"],
        tags=[_page.openapi_tag],
        summary=f"{_page.title} (DB-first)",
    )


@app.get("/resources/pages", tags=["Resources"], summary="Per-type inventory page catalog")
def list_inventory_page_catalog():
    from app.resource_page_registry import pages_catalog

    return pages_catalog()


@app.get("/resources/monitoring", tags=["Monitoring"], summary="[Legacy] Log Analytics and Application Insights")
def list_monitoring(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_resources_by_type_prefix_db(db, subscription_id, "monitoring")


@app.get("/resources/integration", tags=["Integration"], summary="[Legacy] API Management, Data Factory, Logic Apps")
def list_integration(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_resources_by_type_prefix_db(db, subscription_id, "integration")


@app.get("/resources/messaging", tags=["Messaging"], summary="[Legacy] Event Hubs and Service Bus")
def list_messaging(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_resources_by_type_prefix_db(db, subscription_id, "messaging")


@app.get("/resources/analytics", tags=["Analytics"], summary="[Legacy] Databricks, Synapse, ADX, ML")
def list_analytics(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_resources_by_type_prefix_db(db, subscription_id, "analytics")


@app.get("/resources/backup", tags=["Backup"], summary="[Legacy] Recovery Services vaults")
def list_backup(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_resources_by_type_prefix_db(db, subscription_id, "backup")


@app.get("/resources/search", tags=["Search"], summary="[Legacy] Azure AI Search")
def list_search(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_resources_by_type_prefix_db(db, subscription_id, "search")


# ══════════════════════════════════════════════════════════════════════════════
#  AZURE MONITOR METRICS  (API 2023-10-01)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/resources/monitor-plan", tags=["Monitor"],
         summary="Azure Monitor metric definitions per resource type (from technical fetch specs)")
def list_monitor_plan():
    from app.monitor_metrics import monitor_fetch_plan
    return monitor_fetch_plan()


@app.get("/metrics/profiles", tags=["Monitor"],
         summary="Catalog of monitor profiles and metric names per ARM resource type")
def metrics_profiles(request: Request):
    require_authenticated_user(request)
    from app.metrics_api import monitor_profiles_catalog
    return monitor_profiles_catalog()


@app.get("/metrics/resource/plan", tags=["Monitor"],
         summary="Metric names that apply to one resource (by ARM type)")
def metrics_resource_plan(
    request: Request,
    resource_id: str = Query(..., description="Full ARM resource ID"),
):
    require_authenticated_user(request)
    from app.metrics_api import plan_for_resource
    return plan_for_resource(resource_id)


@app.get("/metrics/resource/auto", tags=["Monitor"],
         summary="Fetch Azure Monitor metrics for one resource (profile-driven)")
def metrics_resource_auto(
    request: Request,
    resource_id: str = Query(..., description="Full ARM resource ID"),
    timespan: str = Query("P7D"),
    db: Session = Depends(get_db),
):
    require_authenticated_user(request)
    from app.metrics_api import fetch_metrics_for_resource
    return fetch_metrics_for_resource(resource_id, timespan=timespan, db=db)


@app.get("/metrics/triggers", tags=["Monitor"],
         summary="Metric trigger registry — thresholds and cost vs performance effects")
def metrics_triggers_catalog(request: Request):
    require_authenticated_user(request)
    from app.metrics_api import triggers_catalog
    return triggers_catalog()


@app.get("/metrics/resource-cost-mapping", tags=["Monitor"],
         summary="Resource type → cost-driving properties and metrics")
def metrics_resource_cost_mapping(
    request: Request,
    canonical_type: str | None = Query(None, description="Filter by canonical type, e.g. compute/vm"),
    resource_id: str | None = Query(None, description="ARM resource ID for resource-specific mapping"),
):
    require_authenticated_user(request)
    from app.metrics_api import resource_cost_mapping_catalog
    return resource_cost_mapping_catalog(canonical_type, resource_id=resource_id)


@app.get("/metrics/by-type", tags=["Monitor"],
         summary="Fetch metrics for all synced resources of one type in a subscription (admin)")
def metrics_by_type(
    request: Request,
    subscription_id: str = Query(...),
    canonical_type: str = Query(..., description="e.g. compute/vm, storage/account"),
    timespan: str = Query("P7D"),
    limit: int = Query(0, ge=0, le=500, description="Max resources per type (0 = all)"),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.metrics_api import fetch_metrics_by_canonical_type
    subscription_id = _scoped_subscription(db, subscription_id)
    return fetch_metrics_by_canonical_type(
        db, subscription_id, canonical_type.strip().lower(),
        timespan=timespan,
        limit_per_type=limit,
    )


@app.get("/metrics/subscription", tags=["Monitor"],
         summary="Fetch metrics for synced inventory (admin; all types or one canonical type)")
def metrics_subscription(
    request: Request,
    subscription_id: str = Query(...),
    canonical_type: Optional[str] = Query(None, description="Optional filter, e.g. compute/vm"),
    timespan: str = Query("P7D"),
    limit: int = Query(0, ge=0, le=500, description="Max resources per type (0 = all)"),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.metrics_api import fetch_metrics_for_subscription
    subscription_id = _scoped_subscription(db, subscription_id)
    return fetch_metrics_for_subscription(
        db, subscription_id,
        canonical_type=canonical_type.strip().lower() if canonical_type else None,
        timespan=timespan,
        limit_per_type=limit,
    )


@app.get("/metrics/vm-cpu", tags=["Monitor"],
         summary="CPU % + Available Memory for a VM (P7D default, admin)")
def get_vm_cpu(
    request: Request,
    resource_id: str = Query(..., description="Full ARM resource ID"),
    timespan:    str = Query("P7D"),
):
    require_admin_user(request)
    return resource_client.get_vm_cpu_metrics(resource_id, timespan)


@app.get("/metrics/resource", tags=["Monitor"],
         summary="Generic metric query for any ARM resource (admin)")
def get_resource_metric(
    request: Request,
    resource_id:  str = Query(...),
    metric_names: str = Query(..., description="Comma-separated"),
    timespan:     str = Query("PT1H"),
    interval:     str = Query("PT5M"),
    aggregation:  str = Query("Average"),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    return resource_client.get_resource_metrics(
        resource_id,
        metric_names=[m.strip() for m in metric_names.split(",")],
        timespan=timespan, interval=interval, aggregation=aggregation,
        db=db,
    )


@app.get("/metrics/diagnostics", tags=["Monitor"],
         summary="Probe Azure Monitor access for one resource (admin)")
def probe_monitor_access(
    request: Request,
    resource_id: str = Query(..., description="Full ARM resource ID"),
    metric_names: str = Query("Percentage CPU", description="Comma-separated metric names"),
    timespan: str = Query("P7D"),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.monitor_metrics import probe_monitor_metrics

    names = [m.strip() for m in metric_names.split(",") if m.strip()]
    return probe_monitor_metrics(resource_id, names or None, timespan=timespan, db=db)


# ══════════════════════════════════════════════════════════════════════════════
#  OPTIMIZATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/optimize/analyze", tags=["Optimization Engine"],
          summary="Run optimization analysis on DB inventory or live Azure (admin)")
def run_analysis(
    req: AnalyzeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    DB-first analysis (default):
    - Queues a batched background job (one component at a time) to avoid memory spikes
    - Persists findings when the job completes

    Live analysis (data_source=live, admin only):
    - Fetches fresh Azure inventory before analyzing (synchronous)
    """
    require_admin_user(request)
    ensure_subscription_known(db, req.subscription_id)
    if req.data_source == "db":
        scoped = bool(req.components)
        try:
            job = create_analysis_job(
                db,
                subscription_id=req.subscription_id,
                profile=req.profile,
                engine_version=req.engine_version,
                rule_overrides=req.rule_overrides,
                scope_components=req.components,
            )
            background_tasks.add_task(execute_batch_job, job.id)
            return {
                "status": "queued",
                "job_id": job.id,
                "analysis_mode": "scoped" if scoped else "full",
                "message": (
                    "Scoped analysis started in the background using synced database inventory."
                    if scoped
                    else "Analysis started in the background using synced database inventory."
                ),
                "subscription_id": req.subscription_id.lower(),
                "engine_version": req.engine_version.lower(),
                "data_source": "db",
            }
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _run_live_analysis(req, db)


@app.post("/optimize/analyze/batch", tags=["Optimization Engine"],
          summary="Start batched DB analysis (one component per step, admin)")
def start_batch_analysis(
    req: AnalyzeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Queue a background job that analyzes synced inventory component-by-component."""
    require_admin_user(request)
    ensure_subscription_known(db, req.subscription_id)
    if req.data_source != "db":
        raise HTTPException(400, "Batch analysis only supports data_source=db")

    try:
        job = create_analysis_job(
            db,
            subscription_id=req.subscription_id,
            profile=req.profile,
            engine_version=req.engine_version,
            rule_overrides=req.rule_overrides,
            scope_components=req.components,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(execute_batch_job, job.id)
    return serialize_job(job)


@app.get("/optimize/jobs/{job_id}", tags=["Optimization Engine"],
         summary="Get batch analysis job status and per-component progress")
def get_analysis_job(
    job_id: str = Path(...),
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_job_accessible, ensure_subscription_known, require_subscription_id

    ensure_subscription_known(db, require_subscription_id(subscription_id))
    from app.batch_analyzer import expire_stale_analysis_jobs

    sub = require_subscription_id(subscription_id)
    expire_stale_analysis_jobs(db, subscription_id=sub)
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    ensure_job_accessible(db, job, subscription_id)
    return serialize_job(job)


@app.post("/optimize/jobs/{job_id}/cancel", tags=["Optimization Engine"],
          summary="Cancel a queued or running analysis job (admin)")
def cancel_analysis_job_endpoint(
    request: Request,
    job_id: str = Path(...),
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    from app.batch_analyzer import cancel_analysis_job, expire_stale_analysis_jobs, serialize_job
    from app.validators import ensure_subscription_known, require_subscription_id

    require_admin_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    expire_stale_analysis_jobs(db, subscription_id=sub)
    try:
        job = cancel_analysis_job(db, job_id, sub)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return serialize_job(job)


@app.get("/optimize/jobs", tags=["Optimization Engine"],
         summary="List recent batch analysis jobs")
def list_analysis_jobs(
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    limit: int = Query(20, ge=1, le=100),
    active_only: bool = Query(False, description="Return only queued or running jobs"),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_subscription_known, require_subscription_id

    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    from app.batch_analyzer import expire_stale_analysis_jobs

    expire_stale_analysis_jobs(db, subscription_id=sub)
    q = db.query(AnalysisJob).filter(AnalysisJob.subscription_id == sub)
    if active_only:
        q = q.filter(AnalysisJob.status.in_(["queued", "running"]))
    q = q.order_by(AnalysisJob.created_at.desc())
    jobs = q.limit(limit).all()
    return [serialize_job(j) for j in jobs]


@app.get("/events/jobs/{subscription_id}", tags=["Events"],
         summary="SSE stream for batch analysis job progress")
async def job_events_stream(
    request: Request,
    subscription_id: str = Path(..., description="Azure subscription ID"),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_subscription_known, require_subscription_id
    from app.batch_analyzer import expire_stale_analysis_jobs, serialize_job
    from app.job_events import subscribe_job_events

    require_authenticated_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    expire_stale_analysis_jobs(db, subscription_id=sub)

    async def event_generator():
        active = (
            db.query(AnalysisJob)
            .filter(
                AnalysisJob.subscription_id == sub,
                AnalysisJob.status.in_(["queued", "running"]),
            )
            .order_by(AnalysisJob.created_at.desc())
            .all()
        )
        for job in active:
            payload = json.dumps({"type": "snapshot", "job": serialize_job(job)}, default=str)
            yield f"data: {payload}\n\n"
        async for chunk in subscribe_job_events(sub):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/admin/api-explorer/context", tags=["Admin"],
         summary="OpenAPI + token cache metadata for in-app API explorer")
def admin_api_explorer_context(
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    return build_api_explorer_context(db)


@app.get("/admin/optimization/overview", tags=["Admin"],
         summary="Per-component usage, waste, savings, and rule coverage (admin)")
def admin_optimization_overview(
    request: Request,
    subscription_id: str = Query(...),
    profile: str = Query("default"),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    return build_optimization_overview(db, subscription_id=subscription_id, profile=profile)


def _run_live_analysis(req: AnalyzeRequest, db: Session) -> dict:
    """Fetch live Azure data, analyze, and persist results to the database."""
    from app.auth import arm_auth_context, get_token

    sub = req.subscription_id

    # 1. Fetch all resources in parallel
    import concurrent.futures
    fetch_tasks = {
        "vms":            lambda: resource_client.list_vms(sub, include_instance_view=False),
        "vmss":           lambda: resource_client.list_vm_scale_sets(sub),
        "disks":          lambda: resource_client.list_disks(sub),
        "snapshots":      lambda: resource_client.list_snapshots(sub),
        "aks":            lambda: resource_client.list_aks_clusters(sub),
        "storage":        lambda: resource_client.list_storage_accounts(sub),
        "public_ips":     lambda: resource_client.list_public_ips(sub),
        "load_balancers": lambda: resource_client.list_load_balancers(sub),
        "app_gateways":   lambda: resource_client.list_application_gateways(sub),
        "app_services":   lambda: resource_client.list_app_services(sub),
        "app_service_plans": lambda: resource_client.list_app_service_plans(sub),
        "network_interfaces": lambda: resource_client.list_network_interfaces(sub),
        "nat_gateways":   lambda: resource_client.list_nat_gateways(sub),
        "redis_caches":   lambda: resource_client.list_redis_caches(sub),
        "sql_servers":    lambda: resource_client.list_sql_servers(sub),
        "cosmosdb":       lambda: resource_client.list_cosmosdb(sub),
        "keyvaults":      lambda: resource_client.list_keyvaults(sub),
        "nsgs":           lambda: resource_client.list_network_security_groups(sub),
        "postgresql":     lambda: resource_client.list_postgresql_flexible(sub),
        "acr":            lambda: resource_client.list_container_registries(sub),
        "budgets":        lambda: cost_client.list_budgets(sub),
    }

    fetched: dict = {}
    errors:  dict = {}
    with arm_auth_context(db=db, token=get_token(db)):
        with concurrent.futures.ThreadPoolExecutor(max_workers=arm_fetch_workers()) as pool:
            futs = {pool.submit(fn): key for key, fn in fetch_tasks.items()}
            for fut in concurrent.futures.as_completed(futs):
                key = futs[fut]
                try:
                    fetched[key] = fut.result()
                except Exception as exc:
                    log.warning("fetch.failed", resource=key, error=str(exc))
                    errors[key]  = str(exc)
                    fetched[key] = []

    LIVE_FETCH_ENRICH: dict[str, str] = {
        "vms": "compute/vm",
        "vmss": "compute/vmss",
        "disks": "compute/disk",
        "snapshots": "compute/snapshot",
        "aks": "containers/aks",
        "storage": "storage/account",
        "public_ips": "network/publicip",
        "load_balancers": "network/loadbalancer",
        "app_gateways": "network/appgateway",
        "app_services": "appservice/webapp",
        "app_service_plans": "appservice/plan",
        "network_interfaces": "network/nic",
        "nat_gateways": "network/nat",
        "redis_caches": "database/redis",
        "sql_servers": "database/sql",
        "cosmosdb": "database/cosmosdb",
        "keyvaults": "security/keyvault",
        "nsgs": "network/nsg",
        "postgresql": "database/postgresql",
        "acr": "containers/acr",
    }
    for key, canonical in LIVE_FETCH_ENRICH.items():
        if not fetched.get(key):
            continue
        try:
            fetched[key] = enrich_arm_resources_for_type(
                resource_client, sub, fetched[key], canonical,
            )
        except Exception as exc:
            log.warning("fetch.arm_enrich_failed", resource=key, error=str(exc))

    try:
        from app.vm_uptime import enrich_vmss_list_with_instance_uptime
        if fetched.get("vmss"):
            fetched["vmss"] = enrich_vmss_list_with_instance_uptime(
                resource_client, sub, fetched["vmss"],
            )
    except Exception as exc:
        log.warning("fetch.vmss_uptime_enrich_failed", error=str(exc))

    # 2. Fetch AKS node pools for each cluster (batched)
    aks_node_pools: dict[str, list] = {}
    clusters = fetched.get("aks", [])
    def _fetch_pools(cluster):
        cid = cluster.get("id", "")
        rg  = cid.split("/resourceGroups/")[1].split("/")[0] if "/resourceGroups/" in cid else ""
        cname = cluster.get("name", "")
        try:
            pools = resource_client.list_aks_node_pools(sub, rg, cname)
            return cid, pools
        except Exception:
            return cid, cluster.get("properties", {}).get("agentPoolProfiles", [])

    if clusters:
        with concurrent.futures.ThreadPoolExecutor(max_workers=arm_fetch_workers()) as pool:
            for cid, pools in pool.map(_fetch_pools, clusters):
                aks_node_pools[cid] = pools

    # 2b. Fetch SQL databases for each server
    sql_databases: list[dict] = []
    sql_servers = fetched.get("sql_servers", [])

    def _fetch_sql_dbs(server):
        sid = server.get("id", "")
        rg  = sid.split("/resourceGroups/")[1].split("/")[0] if "/resourceGroups/" in sid else ""
        sname = server.get("name", "")
        try:
            return resource_client.list_sql_databases(sub, rg, sname)
        except Exception:
            return []

    if sql_servers:
        with concurrent.futures.ThreadPoolExecutor(max_workers=arm_fetch_workers()) as pool:
            for dbs in pool.map(_fetch_sql_dbs, sql_servers):
                sql_databases.extend(dbs)

    # 3. Cost by resource for savings estimates and monitor fetch prioritization
    from app.cost_db import resource_cost_map_from_db

    cost_by_resource: dict = {}
    try:
        cost_map = resource_cost_map_from_db(db, sub, "MonthToDate")
        if cost_map:
            cost_by_resource = {
                rid: {
                    "pretax": d.get("pretax", 0),
                    "usd": d.get("usd", 0),
                    "currency": d.get("currency", "USD"),
                }
                for rid, d in cost_map.items()
            }
        else:
            log.info("cost_by_resource.empty_db", subscription_id=sub)
    except Exception as exc:
        log.warning("cost_by_resource.failed", error=str(exc))

    # 4. Fetch Azure Monitor metrics (spec-driven for all resource types with profiles)
    vm_metrics: dict = {}
    node_metrics: dict = {}
    resource_metrics: dict = {}
    resource_facts: dict = {}
    monitor_stats: dict = {}
    if req.include_metrics:
        from app.metrics_loader import (
            analysis_inventory_buckets,
            group_resources_by_canonical_type,
            load_k8s_node_metrics,
        )
        from app.monitor_metrics import load_azure_monitor_metrics

        inventory_buckets = analysis_inventory_buckets(
            vms=fetched.get("vms", []),
            vmss=fetched.get("vmss", []),
            disks=fetched.get("disks", []),
            snapshots=fetched.get("snapshots", []),
            aks_clusters=clusters,
            container_registries=fetched.get("acr", []),
            storage=fetched.get("storage", []),
            public_ips=fetched.get("public_ips", []),
            load_balancers=fetched.get("load_balancers", []),
            app_gateways=fetched.get("app_gateways", []),
            nat_gateways=fetched.get("nat_gateways", []),
            sql_servers=fetched.get("sql_servers", []),
            sql_databases=sql_databases,
            cosmosdb=fetched.get("cosmosdb", []),
            postgresql=fetched.get("postgresql", []),
            redis_caches=fetched.get("redis_caches", []),
            app_services=fetched.get("app_services", []),
            app_service_plans=fetched.get("app_service_plans", []),
            keyvaults=fetched.get("keyvaults", []),
            network_interfaces=fetched.get("network_interfaces", []),
            nsgs=fetched.get("nsgs", []),
        )
        grouped = group_resources_by_canonical_type(inventory_buckets)
        resource_metrics, resource_facts, monitor_stats = load_azure_monitor_metrics(
            grouped,
            cost_by_resource,
            timespan=req.timespan_metrics,
            db=db,
        )
        try:
            node_metrics = load_k8s_node_metrics(db, clusters)
        except Exception as exc:
            log.warning("live_analysis.k8s_metrics_failed", error=str(exc))
        vm_metrics = {
            rid: payload
            for rid, payload in resource_metrics.items()
            if "/virtualmachines/" in rid or "/virtualmachinescalesets/" in rid
        }

    # 5. Build engine with DB profile + runtime overrides merged
    db_overrides      = get_effective_config(db, req.profile)
    merged_overrides  = {**db_overrides, **req.rule_overrides}
    engine_version = req.engine_version.lower()
    if engine_version not in {"standard", "extended"}:
        raise HTTPException(400, "engine_version must be 'standard' or 'extended'")
    eng = (
        ExtendedOptimizationEngine(rule_overrides=merged_overrides)
        if engine_version == "extended"
        else OptimizationEngine(rule_overrides=merged_overrides)
    )

    # 6. Run analysis
    if engine_version == "extended":
        result = eng.analyze(
            subscription_id=sub,
            vms=fetched.get("vms", []),
            vmss=fetched.get("vmss", []),
            disks=fetched.get("disks", []),
            snapshots=fetched.get("snapshots", []),
            aks_clusters=clusters,
            aks_node_pools=aks_node_pools,
            storage=fetched.get("storage", []),
            public_ips=fetched.get("public_ips", []),
            load_balancers=fetched.get("load_balancers", []),
            app_gateways=fetched.get("app_gateways", []),
            app_services=fetched.get("app_services", []),
            app_service_plans=fetched.get("app_service_plans", []),
            network_interfaces=fetched.get("network_interfaces", []),
            nat_gateways=fetched.get("nat_gateways", []),
            redis_caches=fetched.get("redis_caches", []),
            sql_databases=sql_databases,
            cosmosdb=fetched.get("cosmosdb", []),
            keyvaults=fetched.get("keyvaults", []),
            nsgs=fetched.get("nsgs", []),
            postgresql=fetched.get("postgresql", []),
            container_registries=fetched.get("acr", []),
            vm_metrics=vm_metrics,
            node_metrics=node_metrics,
            resource_metrics=resource_metrics,
            resource_facts=resource_facts,
            cost_by_resource=cost_by_resource,
            budgets=fetched.get("budgets", []),
        )
    else:
        result = eng.analyze(
            vms=fetched.get("vms", []),
            disks=fetched.get("disks", []),
            snapshots=fetched.get("snapshots", []),
            aks_clusters=clusters,
            aks_node_pools=aks_node_pools,
            storage=fetched.get("storage", []),
            public_ips=fetched.get("public_ips", []),
            load_balancers=fetched.get("load_balancers", []),
            app_gateways=fetched.get("app_gateways", []),
            app_services=fetched.get("app_services", []),
            app_service_plans=fetched.get("app_service_plans", []),
            network_interfaces=fetched.get("network_interfaces", []),
            nat_gateways=fetched.get("nat_gateways", []),
            redis_caches=fetched.get("redis_caches", []),
            sql_servers=fetched.get("sql_servers", []),
            sql_databases=sql_databases,
            cosmosdb=fetched.get("cosmosdb", []),
            keyvaults=fetched.get("keyvaults", []),
            vm_metrics=vm_metrics,
            cost_by_resource=cost_by_resource,
            budgets=fetched.get("budgets", []),
        )
        result["engine_version"] = "standard"

    result = append_cost_export_findings(
        db,
        sub,
        result,
        profile=req.profile,
        rule_overrides=req.rule_overrides,
        engine_version=engine_version,
    )

    result = enrich_analysis_with_ai(db, result, include_ai=req.include_ai)

    if engine_version == "extended":
        from app.analysis_summary import summarize_findings
        from app.commitment_findings import dedupe_commitment_findings

        findings = result.get("findings") or []
        if fetched.get("vms"):
            from app.vm_sizing_persist import supplement_vm_rightsizing_findings

            merged_overrides = {**get_effective_config(db, req.profile), **req.rule_overrides}
            findings = supplement_vm_rightsizing_findings(
                findings,
                subscription_id=sub,
                vms=fetched.get("vms") or [],
                vm_metrics=vm_metrics or {},
                cost_by_resource={
                    normalize_arm_id(rid_key): float(d.get("usd") or d.get("pretax") or 0)
                    for rid_key, d in (cost_by_resource or {}).items()
                } if cost_by_resource else {},
                rule_overrides=merged_overrides,
            )
        findings = dedupe_commitment_findings(findings)
        result["findings"] = findings
        result["summary"] = summarize_findings(
            findings,
            engine_version,
            metrics_context=result.get("metrics_context"),
        )

    run_id = persist_optimization_run(
        db,
        subscription_id=sub,
        profile=req.profile,
        engine_version=engine_version,
        result=result,
        data_source="live",
    )

    result["run_id"]         = run_id
    result["data_source"]    = "live"
    result["fetch_errors"]   = errors
    result["resources_analyzed"] = {k: len(v) for k, v in fetched.items()}
    if req.include_metrics:
        from app.metrics_loader import analysis_metrics_summary
        result["metrics_context"] = analysis_metrics_summary(
            vm_metrics, node_metrics, resource_metrics, resource_facts, monitor_stats,
        )
    return result


@app.get("/optimize/runs", tags=["Optimization Engine"],
         summary="List past optimization runs with savings totals")
def list_runs(
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    limit:           int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_subscription_known, require_subscription_id

    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    q = db.query(OptimizationRun).filter(OptimizationRun.subscription_id == sub).order_by(OptimizationRun.analyzed_at.desc())
    runs = q.limit(limit).all()
    from app.batch_analyzer import job_history_snapshot, jobs_by_run_ids

    job_map = jobs_by_run_ids(db, sub, [r.id for r in runs])
    return [{
        "id": r.id, "subscription_id": r.subscription_id,
        "profile": r.profile,
        "engine_version": getattr(r, "engine_version", None) or "standard",
        "total_findings": r.total_findings,
        "critical": r.critical_count,
        "high": r.high_count,
        "critical_count": r.critical_count,
        "high_count": r.high_count,
        "medium": r.medium_count, "low": r.low_count,
        "total_savings_usd": r.total_savings_usd,
        "analyzed_at": str(r.analyzed_at),
        "job": job_history_snapshot(job_map.get(r.id)),
    } for r in runs]


def _coerce_evidence_dict(value: Any) -> dict:
    """Normalize persisted evidence payloads for API enrichment."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


@app.get("/optimize/runs/{run_id}", tags=["Optimization Engine"],
         summary="Full findings for a specific optimization run")
def get_run(
    run_id: str = Path(...),
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_run_accessible, ensure_subscription_known, require_subscription_id

    ensure_subscription_known(db, require_subscription_id(subscription_id))
    run = db.query(OptimizationRun).filter(OptimizationRun.id == run_id).first()
    ensure_run_accessible(db, run, subscription_id)
    from app.batch_analyzer import job_for_run, job_history_snapshot

    job_row = job_for_run(db, run.subscription_id or "", run.id)
    raw_findings = json.loads(run.findings_json or "[]")
    disk_props = disk_inventory_properties_map(
        db,
        run.subscription_id or "",
        [f.get("resource_id") for f in raw_findings if f.get("resource_id")],
    )
    findings = [
        enrich_finding_for_api({
            "rule_id": f.get("rule_id"),
            "rule_name": f.get("rule_name"),
            "category": f.get("category"),
            "severity": f.get("severity"),
            "resource_id": f.get("resource_id"),
            "resource_name": f.get("resource_name"),
            "resource_type": f.get("resource_type"),
            "resource_group": f.get("resource_group"),
            "location": f.get("location"),
            "detail": f.get("detail"),
            "recommendation": f.get("recommendation"),
            "estimated_savings_usd": f.get("estimated_savings_usd"),
            "annualized_savings_usd": f.get("annualized_savings_usd"),
            "waste_score": f.get("waste_score"),
            "confidence_score": f.get("confidence_score"),
            "action_priority": f.get("action_priority"),
            "impact": f.get("impact"),
            "evidence": _coerce_evidence_dict(f.get("evidence")),
            "status": f.get("status", "open"),
        }, inventory_properties=disk_props.get(normalize_arm_id(f.get("resource_id") or "")))
        for f in raw_findings
    ]
    return {
        "id": run.id, "subscription_id": run.subscription_id,
        "profile": run.profile,
        "engine_version": getattr(run, "engine_version", None) or "standard",
        "total_findings": run.total_findings,
        "total_savings_usd": run.total_savings_usd,
        "analyzed_at": str(run.analyzed_at),
        "findings": findings,
        "job": job_history_snapshot(job_row),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  ENGINE CONFIGURATION (Rules + Profiles)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/optimize/rules", tags=["Engine Config"],
         summary="List all rules with component-specific settings")
def list_rules():
    """Returns every rule with only the settings that apply to it."""
    return list_all_rules()


@app.get("/optimize/rules/by-component", tags=["Engine Config"],
         summary="Rules grouped by Azure component")
def list_rules_by_component():
    return list_components()


@app.get("/optimize/rules/by-resource", tags=["Engine Config"],
         summary="Applicable rules per canonical resource type")
def list_rules_by_resource(
    canonical_type: Optional[str] = Query(None, description="Filter by canonical type, e.g. compute/vm"),
):
    if canonical_type:
        rule_ids = list_rules_for_canonical_type(canonical_type)
        return {
            "canonical_type": canonical_type.strip().lower(),
            "rule_count": len(rule_ids),
            "rule_ids": rule_ids,
        }
    return {"count": len(canonical_resource_rule_catalog()), "resources": canonical_resource_rule_catalog()}


@app.get("/optimize/technical-fetch-specs", tags=["Engine Config"],
         summary="Technical fetch definitions per Azure resource type")
def get_technical_fetch_specs(
    canonical_type: Optional[str] = Query(None, description="Filter by canonical type, e.g. compute/vm"),
):
    """Returns ARM properties to sync, technical fields, and usage metrics per resource type."""
    specs = list_technical_fetch_specs()
    if canonical_type:
        key = canonical_type.strip().lower()
        specs = [s for s in specs if s["canonical_type"] == key]
    return {"count": len(specs), "specs": specs}


@app.get("/optimize/sub-engines", tags=["Engine Config"],
         summary="Per-resource optimization sub-engines aligned to analysis batches")
def get_sub_engines():
    from app.optimizer.resource_engines import list_sub_engines

    engines = list_sub_engines()
    return {"count": len(engines), "sub_engines": engines}


@app.get("/optimize/config/{profile}", tags=["Engine Config"],
         summary="Get all rule overrides for a named profile (admin)")
def get_profile_config(
    request: Request,
    profile: str = Path(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    rows = db.query(EngineConfig).filter(EngineConfig.profile == profile).all()
    return [
        {
            "rule_id":     r.rule_id,
            "enabled":     r.enabled,
            "overrides":   json.loads(r.overrides_json or "{}"),
            "description": r.description,
            "updated_at":  str(r.updated_at),
        }
        for r in rows
    ]


@app.post("/optimize/config/{profile}", tags=["Engine Config"],
          summary="Create or update a rule override in a profile")
def upsert_config(
    request: Request,
    profile: str = Path(..., description="Profile name e.g. default, aggressive, conservative"),
    body:    RuleConfigIn = ...,
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    if not is_known_rule(body.rule_id):
        raise HTTPException(400, f"Unknown rule_id '{body.rule_id}'. Valid: {sorted(ALL_KNOWN_RULE_IDS)}")
    row = upsert_rule_config(
        db, profile=profile, rule_id=body.rule_id,
        overrides=body.overrides, enabled=body.enabled,
        description=body.description or "",
    )
    return {
        "profile":   profile,
        "rule_id":   row.rule_id,
        "enabled":   row.enabled,
        "overrides": json.loads(row.overrides_json),
        "updated_at": str(row.updated_at),
    }


@app.delete("/optimize/config/{profile}/{rule_id}", tags=["Engine Config"],
            summary="Remove a rule override (resets to default thresholds)")
def delete_config(
    request: Request,
    profile: str = Path(...),
    rule_id: str = Path(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    deleted = delete_rule_config(db, profile=profile, rule_id=rule_id)
    if not deleted:
        raise HTTPException(404, "Config not found")
    return {"deleted": True, "profile": profile, "rule_id": rule_id}


@app.post("/optimize/config/{profile}/reanalyze", tags=["Engine Config"],
          summary="Re-run recommendations after rule changes (DB inventory + cached metrics, no Azure fetch)")
def reanalyze_after_rule_config(
    request: Request,
    profile: str = Path(..., description="Profile whose rule overrides should be applied"),
    background_tasks: BackgroundTasks = ...,
    db: Session = Depends(get_db),
    engine_version: str = Query("extended", description="standard or extended"),
):
    require_admin_user(request)
    return queue_rule_config_reanalysis(
        db,
        background_tasks,
        profile=profile,
        engine_version=engine_version.lower(),
    )


@app.get("/optimize/config", tags=["Engine Config"],
         summary="List all profiles that have been configured (admin)")
def list_profiles(request: Request, db: Session = Depends(get_db)):
    require_admin_user(request)
    rows = db.query(EngineConfig.profile).distinct().all()
    return {"profiles": [r[0] for r in rows]}


# ══════════════════════════════════════════════════════════════════════════════
#  FINDINGS — Remediation Tracking
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/optimize/findings/cleanup", tags=["Findings"],
          summary="Clean duplicate or supersede stale open recommendations (admin only)")
def cleanup_findings(
    request: Request,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    mode: str = Query(
        "dedupe",
        description="dedupe — collapse duplicate open rows; supersede — resolve all open (use before re-analyze)",
    ),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_subscription_known, require_subscription_id
    from app.analysis_persist import cleanup_duplicate_open_findings, supersede_open_findings

    require_admin_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    mode_norm = (mode or "dedupe").strip().lower()
    if mode_norm not in {"dedupe", "supersede"}:
        raise HTTPException(400, "mode must be dedupe or supersede")

    duplicates_resolved = cleanup_duplicate_open_findings(db, sub, commit=False)
    superseded = 0
    if mode_norm == "supersede":
        superseded = supersede_open_findings(db, sub, commit=False)

    db.commit()
    return {
        "status": "ok",
        "subscription_id": sub,
        "mode": mode_norm,
        "duplicates_resolved": duplicates_resolved,
        "open_superseded": superseded,
    }


@app.get("/optimize/findings", tags=["Findings"],
         summary="Query findings with filters — subscription, severity, category, status")
def list_findings(
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    severity:        Optional[str] = Query(None, description="CRITICAL|HIGH|MEDIUM|LOW|INFO"),
    category:        Optional[str] = Query(None, description="COMPUTE|KUBERNETES|STORAGE|NETWORK|DATABASE|SECURITY|COST"),
    status:          Optional[str] = Query(None, description="open|acknowledged|implemented|resolved|ignored"),
    rule_id:         Optional[str] = Query(None),
    resource_id:     Optional[str] = Query(None, description="Filter by Azure resource ID (case-insensitive)"),
    limit:           int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_subscription_known, require_subscription_id
    from sqlalchemy import func

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    if not status or status.lower() == "open":
        from app.analysis_persist import cleanup_duplicate_open_findings
        cleanup_duplicate_open_findings(db, subscription_id)
    q = db.query(OptimizationFinding).order_by(
        OptimizationFinding.detected_at.desc()
    )
    if subscription_id: q = q.filter(func.lower(OptimizationFinding.subscription_id) == subscription_id)
    if severity:        q = q.filter(OptimizationFinding.severity  == severity.upper())
    if category:        q = q.filter(OptimizationFinding.category  == category.upper())
    status_norm = (status or "").lower()
    if status and status_norm not in {"implemented"}:
        q = q.filter(OptimizationFinding.status == status_norm)
    if rule_id:         q = q.filter(OptimizationFinding.rule_id   == rule_id.upper())
    if resource_id:     q = q.filter(func.lower(OptimizationFinding.resource_id) == resource_id.lower())

    if status_norm == "implemented":
        from app.recommendation_execution import implemented_findings_for_subscription

        findings = implemented_findings_for_subscription(db, subscription_id or "")
        if severity:
            findings = [f for f in findings if f.severity == severity.upper()]
        if category:
            findings = [f for f in findings if f.category == category.upper()]
        if rule_id:
            findings = [f for f in findings if f.rule_id == rule_id.upper()]
        if resource_id:
            rid = resource_id.lower()
            findings = [f for f in findings if (f.resource_id or "").lower() == rid]
        findings = findings[:limit]
    elif status_norm == "resolved":
        from app.finding_dedupe import actionable_resolved_rows, collect_open_identity_keys

        open_rows = (
            db.query(OptimizationFinding)
            .filter(
                func.lower(OptimizationFinding.subscription_id) == subscription_id,
                OptimizationFinding.status == "open",
            )
            .all()
        )
        open_keys = collect_open_identity_keys(open_rows)
        resolved_rows = q.all()
        findings = actionable_resolved_rows(resolved_rows, open_keys)[:limit]
    else:
        findings = q.limit(limit).all()
        if not status or status_norm == "open":
            from app.analysis_persist import dedupe_open_findings_for_display
            findings = dedupe_open_findings_for_display(findings)
    disk_props = disk_inventory_properties_map(
        db,
        subscription_id or "",
        [f.resource_id for f in findings],
    )
    enriched_list = [
        enrich_finding_for_api({
            "id": f.id, "run_id": f.run_id,
            "rule_id": f.rule_id, "rule_name": f.rule_name,
            "category": f.category, "severity": f.severity,
            "resource_id": f.resource_id, "resource_name": f.resource_name,
            "resource_type": f.resource_type,
            "resource_group": f.resource_group, "location": f.location,
            "detail": f.detail, "recommendation": f.recommendation,
            "estimated_savings_usd": f.estimated_savings_usd,
            "annualized_savings_usd": getattr(f, "annualized_savings_usd", None),
            "waste_score": f.waste_score,
            "confidence_score": getattr(f, "confidence_score", None),
            "action_priority": getattr(f, "action_priority", None),
            "impact": getattr(f, "impact", None),
            "evidence": _coerce_evidence_dict(json.loads(getattr(f, "evidence_json", None) or "{}")),
            "status": f.status, "detected_at": str(f.detected_at),
            "resolved_at": str(f.resolved_at) if f.resolved_at else None,
            "chain_id": getattr(f, "chain_id", None),
            "chain_step": getattr(f, "chain_step", None),
            "chain_total": getattr(f, "chain_total", None),
        }, inventory_properties=disk_props.get(normalize_arm_id(f.resource_id or "")))
        for f in findings
    ]

    def _attach_ai_flags(payload: dict) -> dict:
        ev = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
        ai_block = ev.get("ai_insight") if isinstance(ev.get("ai_insight"), dict) else {}
        payload["ai_enriched"] = bool(ai_block)
        if ai_block.get("risk_level"):
            payload["ai_risk_level"] = ai_block["risk_level"]
        return payload

    return [_attach_ai_flags(item) for item in enriched_list]


@app.patch("/optimize/findings/{finding_id}/status", tags=["Findings"],
           summary="Update remediation status of a finding")
def update_finding_status(
    request: Request,
    finding_id: str = Path(...),
    body:       FindingStatusIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    user = require_authenticated_user(request)
    sub = ensure_subscription_known(db, subscription_id)
    valid = {"open", "acknowledged", "resolved", "ignored"}
    if body.status not in valid:
        raise HTTPException(400, f"status must be one of: {valid}")
    if body.status in {"resolved", "open"} and user.get("role") != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    f = db.query(OptimizationFinding).filter(OptimizationFinding.id == finding_id).first()
    if not f:
        raise HTTPException(404, "Finding not found")
    if (f.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Finding not found")
    from app.analysis_persist import refresh_resource_analysis_summary

    _apply_finding_status_update(db, f, body.status, user=user)
    db.commit()
    refresh_resource_analysis_summary(
        db,
        subscription_id=f.subscription_id,
        resource_id=f.resource_id or "",
    )
    return {"id": f.id, "status": f.status, "resolved_at": str(f.resolved_at) if f.resolved_at else None}


def _apply_finding_status_update(
    db: Session,
    finding: OptimizationFinding,
    status: str,
    *,
    user: dict | None = None,
) -> None:
    from datetime import datetime, timezone
    from app.finding_activity import log_finding_status_change

    previous = (finding.status or "").lower()
    normalized = status.lower()
    finding.status = normalized
    if normalized == "resolved":
        finding.resolved_at = datetime.now(timezone.utc)
    elif normalized == "open":
        finding.resolved_at = None
    if previous != normalized:
        log_finding_status_change(
            db,
            finding_id=finding.id,
            subscription_id=finding.subscription_id or "",
            from_status=previous or None,
            to_status=normalized,
            user=user,
        )


@app.patch("/optimize/findings/bulk-status", tags=["Findings"],
           summary="Update remediation status for multiple findings")
def bulk_update_finding_status(
    request: Request,
    body: BulkFindingStatusIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    user = require_authenticated_user(request)
    sub = ensure_subscription_known(db, subscription_id)
    valid = {"open", "acknowledged", "resolved", "ignored"}
    if body.status not in valid:
        raise HTTPException(400, f"status must be one of: {valid}")
    if body.status in {"resolved", "open"} and user.get("role") != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    unique_ids = list(dict.fromkeys(body.finding_ids))
    rows = (
        db.query(OptimizationFinding)
        .filter(OptimizationFinding.id.in_(unique_ids))
        .all()
    )
    if len(rows) != len(unique_ids):
        found = {row.id for row in rows}
        missing = [fid for fid in unique_ids if fid not in found]
        raise HTTPException(404, f"Finding(s) not found: {', '.join(missing[:5])}")

    for row in rows:
        if (row.subscription_id or "").lower() != sub:
            raise HTTPException(404, f"Finding not found: {row.id}")

    for row in rows:
        _apply_finding_status_update(db, row, body.status, user=user)
    db.commit()

    from app.analysis_persist import refresh_resource_analysis_summary

    resource_ids = {row.resource_id or "" for row in rows if row.resource_id}
    for resource_id in resource_ids:
        refresh_resource_analysis_summary(
            db,
            subscription_id=sub,
            resource_id=resource_id,
        )
    return {
        "updated": len(rows),
        "status": body.status,
        "finding_ids": unique_ids,
    }


@app.get("/optimize/findings/{finding_id}/activity", tags=["Findings"],
         summary="Activity log for a finding")
def finding_activity(
    finding_id: str = Path(...),
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    from app.finding_activity import list_finding_activity
    from app.validators import ensure_subscription_known, require_subscription_id

    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    f = db.query(OptimizationFinding).filter(OptimizationFinding.id == finding_id).first()
    if not f or (f.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Finding not found")
    return {"items": list_finding_activity(db, finding_id=finding_id, limit=limit)}


@app.post("/optimize/findings/{finding_id}/execute", tags=["Findings"],
          summary="Log execution of a recommendation")
def log_finding_execution(
    request: Request,
    finding_id: str = Path(...),
    body: FindingExecutionIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    from app.recommendation_execution import log_execution, serialize_execution
    from app.validators import ensure_subscription_known, require_subscription_id

    user = require_authenticated_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    f = db.query(OptimizationFinding).filter(OptimizationFinding.id == finding_id).first()
    if not f or (f.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Finding not found")
    row = log_execution(
        db,
        finding_id=finding_id,
        executed_by=user.get("display_name") or user.get("username") or user.get("id", "user"),
        action_type=body.action_type,
        before_state=body.before_state,
    )
    db.commit()
    return serialize_execution(row)


@app.post("/optimize/findings/{finding_id}/validate", tags=["Findings"],
          summary="Validate a logged recommendation execution")
def validate_finding_execution(
    request: Request,
    finding_id: str = Path(...),
    body: FindingValidationIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    from app.recommendation_execution import serialize_execution, validate_execution
    from app.models import RecommendationExecution
    from app.validators import ensure_subscription_known, require_subscription_id

    require_authenticated_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    f = db.query(OptimizationFinding).filter(OptimizationFinding.id == finding_id).first()
    if not f or (f.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Finding not found")
    row = (
        db.query(RecommendationExecution)
        .filter(RecommendationExecution.finding_id == finding_id)
        .order_by(RecommendationExecution.executed_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(404, "No execution record found for this finding")
    validate_execution(db, row, after_state=body.after_state, regressed=body.regressed)
    db.commit()
    return serialize_execution(row)


@app.get("/optimize/findings/summary", tags=["Findings"],
         summary="Aggregated findings summary by status, severity, and category")
def findings_summary(
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    from app.findings_summary import build_findings_summary
    from app.validators import ensure_subscription_known, require_subscription_id
    from app.analysis_persist import cleanup_duplicate_open_findings

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    cleanup_duplicate_open_findings(db, subscription_id)
    from app.perf_cache import cached_findings_summary

    return cached_findings_summary(
        subscription_id,
        lambda: build_findings_summary(db, subscription_id),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  AZURE ADVISOR  (Microsoft.Advisor snapshots — distinct from GET /advisor)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/optimize/advisor/generate", tags=["Azure Advisor"],
          summary="Trigger Azure Advisor recommendation generation (admin)")
def trigger_advisor_generate(
    request: Request,
    subscription_id: str = Query(...),
    wait: bool = Query(False, description="Poll until recommendations refresh or timeout"),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    require_admin_user(request)
    from app.advisor_sync import sync_azure_advisor_recommendations
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    try:
        return sync_azure_advisor_recommendations(
            subscription_id,
            db,
            token,
            trigger_generate=True,
            wait_for_generate=wait,
        )
    except Exception as exc:
        log.exception("advisor_generate_failed", subscription_id=subscription_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/optimize/advisor/sync", tags=["Azure Advisor"],
          summary="Sync Azure Advisor recommendations into the database (admin)")
def trigger_advisor_sync(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    require_admin_user(request)
    from app.advisor_sync import sync_azure_advisor_recommendations
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    try:
        return sync_azure_advisor_recommendations(subscription_id, db, token)
    except Exception as exc:
        log.exception("advisor_sync_failed", subscription_id=subscription_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/optimize/advisor/list", tags=["Azure Advisor"],
         summary="List stored Azure Advisor recommendations")
def list_azure_advisor_recommendations(
    subscription_id: str = Query(...),
    category: str | None = Query(None, description="Cost, Performance, Security, etc."),
    impact: str | None = Query(None),
    status: str | None = Query("Active"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    from app.advisor_sync import list_stored_advisor_recommendations
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    return list_stored_advisor_recommendations(
        db,
        subscription_id,
        category=category,
        impact=impact,
        status=status,
        limit=limit,
        offset=offset,
    )


@app.get("/optimize/actions/list", tags=["Optimization actions"],
         summary="List synthesized optimization actions")
def list_optimization_actions_route(
    subscription_id: str = Query(...),
    workflow_status: str | None = Query(None),
    action_type: str | None = Query(None),
    confidence: str | None = Query(None),
    resource_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    from app.optimization_actions import list_optimization_actions
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    return list_optimization_actions(
        db,
        subscription_id,
        workflow_status=workflow_status,
        action_type=action_type,
        confidence=confidence,
        resource_type=resource_type,
        limit=limit,
        offset=offset,
    )


@app.post("/optimize/actions/decide", tags=["Optimization actions"],
          summary="Run decision engine and synthesize actions (admin)")
def decide_optimization_actions(
    request: Request,
    subscription_id: str = Query(...),
    force_refresh: bool = Query(False),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.optimizer.decision_engine import generate_optimization_actions
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    try:
        return generate_optimization_actions(db, subscription_id, force_refresh=force_refresh)
    except Exception as exc:
        log.exception("decision_engine_failed", subscription_id=subscription_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.patch("/optimize/actions/{action_id}", tags=["Optimization actions"],
           summary="Update workflow status or owner for an action")
def patch_optimization_action(
    request: Request,
    action_id: str = Path(...),
    body: ActionWorkflowIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    user = require_authenticated_user(request)
    from app.optimization_actions import serialize_action, update_optimization_action
    from app.validators import ensure_subscription_known, require_subscription_id

    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    if body.workflow_status in {"approved", "executed", "rejected"} and user.get("role") != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.models import OptimizationAction

    row = db.query(OptimizationAction).filter(OptimizationAction.id == action_id).first()
    if not row or (row.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Action not found")

    try:
        update_optimization_action(
            db,
            row,
            workflow_status=body.workflow_status,
            owner=body.owner,
            note=body.note,
            user=user,
            unset_owner=body.clear_owner,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    db.commit()
    return serialize_action(row)


@app.patch("/optimize/actions/bulk-status", tags=["Optimization actions"],
           summary="Bulk update workflow status for actions")
def bulk_patch_optimization_actions(
    request: Request,
    body: BulkActionWorkflowIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    user = require_authenticated_user(request)
    from app.optimization_actions import bulk_update_optimization_actions
    from app.validators import ensure_subscription_known, require_subscription_id

    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    if body.workflow_status in {"approved", "executed", "rejected"} and user.get("role") != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        return bulk_update_optimization_actions(
            db,
            subscription_id=sub,
            action_ids=body.action_ids,
            workflow_status=body.workflow_status,
            user=user,
            note=body.note,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.patch("/optimize/actions/bulk-assign", tags=["Optimization actions"],
           summary="Bulk assign owner to optimization actions")
def bulk_assign_optimization_actions_route(
    request: Request,
    body: BulkActionAssignIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    user = require_authenticated_user(request)
    from app.optimization_actions import bulk_assign_optimization_actions
    from app.validators import ensure_subscription_known, require_subscription_id

    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    try:
        return bulk_assign_optimization_actions(
            db,
            subscription_id=sub,
            action_ids=body.action_ids,
            owner=body.owner,
            user=user,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/optimize/engine/score", tags=["Advanced engine"],
          summary="Score all resources with the advanced optimization engine (admin)")
def score_subscription_advanced(
    request: Request,
    subscription_id: str = Query(...),
    force_rescore: bool = Query(False),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.advanced_scoring import score_subscription
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    try:
        return score_subscription(db, subscription_id, force_rescore=force_rescore)
    except Exception as exc:
        log.exception("advanced_engine_score_failed", subscription_id=subscription_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/optimize/engine/scoreboard", tags=["Advanced engine"],
         summary="List multi-dimensional optimization scorecards")
def get_optimization_scoreboard(
    subscription_id: str = Query(...),
    tier: str | None = Query(None, description="tier1_safe | tier2_balanced | tier3_risky | blocked"),
    resource_type: str | None = Query(None),
    min_score: float | None = Query(None, ge=0, le=100),
    evaluation_date: str | None = Query(None, description="YYYY-MM-DD, defaults to today"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    from app.advanced_scoring import list_scoreboard
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    return list_scoreboard(
        db,
        subscription_id,
        tier=tier,
        resource_type=resource_type,
        min_score=min_score,
        evaluation_date=evaluation_date,
        limit=limit,
        offset=offset,
    )


@app.post("/optimize/rollout/plan", tags=["Advanced engine"],
          summary="Plan rollout stages from tiered optimization actions (admin)")
def plan_rollout(
    request: Request,
    subscription_id: str = Query(...),
    replace_existing: bool = Query(False),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.optimizer.rollout_orchestrator import plan_rollout_stages
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    return plan_rollout_stages(db, subscription_id, replace_existing=replace_existing)


@app.get("/optimize/rollout/stages", tags=["Advanced engine"],
         summary="List optimization rollout stages")
def get_rollout_stages(
    subscription_id: str = Query(...),
    status: str | None = Query(None),
    tier: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.optimizer.rollout_orchestrator import list_rollout_stages
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    return list_rollout_stages(db, subscription_id, status=status, tier=tier)


@app.post("/optimize/rollout/stages/{stage_id}/start", tags=["Advanced engine"],
          summary="Start rollout stage and capture baseline metrics (admin)")
def start_rollout_stage_route(
    request: Request,
    stage_id: str = Path(...),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.models import OptimizationRolloutStage
    from app.optimizer.rollout_orchestrator import serialize_rollout_stage, start_rollout_stage
    from app.validators import ensure_subscription_known, require_subscription_id

    user = require_authenticated_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    stage = db.query(OptimizationRolloutStage).filter(OptimizationRolloutStage.id == stage_id).first()
    if not stage or (stage.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Rollout stage not found")
    if stage.status not in {"proposed"}:
        raise HTTPException(400, "Stage has already started")
    start_rollout_stage(db, stage, user=user)
    db.commit()
    return serialize_rollout_stage(stage)


@app.post("/optimize/rollout/stages/{stage_id}/expand", tags=["Advanced engine"],
          summary="Complete rollout stage after observation window (admin)")
def expand_rollout_stage_route(
    request: Request,
    stage_id: str = Path(...),
    subscription_id: str = Query(...),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.models import OptimizationRolloutStage
    from app.validators import ensure_subscription_known, require_subscription_id

    user = require_authenticated_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    stage = db.query(OptimizationRolloutStage).filter(OptimizationRolloutStage.id == stage_id).first()
    if not stage or (stage.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Rollout stage not found")
    from app.optimizer.rollout_orchestrator import expand_rollout_stage

    try:
        return expand_rollout_stage(db, stage, user=user, force=force)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/optimize/rollout/stages/{stage_id}/rollback", tags=["Advanced engine"],
          summary="Rollback rollout stage and reject linked actions (admin)")
def rollback_rollout_stage_route(
    request: Request,
    stage_id: str = Path(...),
    subscription_id: str = Query(...),
    reason: str = Query(..., min_length=3, max_length=500),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.models import OptimizationRolloutStage
    from app.optimizer.rollout_orchestrator import rollback_rollout_stage
    from app.validators import ensure_subscription_known, require_subscription_id

    user = require_authenticated_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    stage = db.query(OptimizationRolloutStage).filter(OptimizationRolloutStage.id == stage_id).first()
    if not stage or (stage.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Rollout stage not found")
    return rollback_rollout_stage(db, stage, reason=reason, user=user)


@app.get("/optimize/trends", tags=["Advanced engine"],
         summary="Optimization trends and rollout health summary")
def get_optimization_trends_route(
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    from app.optimization_trends import get_optimization_trends
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    return get_optimization_trends(db, subscription_id)


@app.get("/optimize/resources/analysis", tags=["Advanced engine"],
         summary="Advanced engine deep-dive for one resource")
def get_resource_advanced_analysis_route(
    subscription_id: str = Query(...),
    resource_id: str = Query(..., description="ARM resource ID"),
    db: Session = Depends(get_db),
):
    from app.resource_advanced_analysis import get_resource_advanced_analysis
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    if not (resource_id or "").strip():
        raise HTTPException(400, "resource_id is required")
    return get_resource_advanced_analysis(db, subscription_id, resource_id)


@app.post("/optimize/resources/batch-lookup", tags=["Advanced engine"],
          summary="Batch metrics and advanced analysis for multiple resources")
def batch_resource_lookup_route(
    request: Request,
    payload: BatchResourceLookupIn,
    db: Session = Depends(get_db),
):
    require_authenticated_user(request)
    from app.metrics_api import fetch_metrics_for_resource
    from app.resource_advanced_analysis import get_resource_advanced_analysis
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(payload.subscription_id))
    items: dict[str, dict] = {}
    for raw_id in payload.resource_ids:
        rid = (raw_id or "").strip()
        if not rid:
            continue
        entry: dict = {}
        if payload.include_metrics:
            entry["metrics"] = fetch_metrics_for_resource(rid, timespan=payload.timespan, db=db)
        if payload.include_advanced_analysis:
            entry["advanced_analysis"] = get_resource_advanced_analysis(db, subscription_id, rid)
        items[rid.lower()] = entry
    return {"items": items, "count": len(items)}


@app.post("/optimize/rollout/observe", tags=["Advanced engine"],
          summary="Run rollout observation check (admin)")
def observe_rollout_stages(
    request: Request,
    subscription_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.rollout_observer import check_all_subscriptions, check_rollout_observations
    from app.validators import ensure_subscription_known, require_subscription_id

    if subscription_id:
        sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
        return check_rollout_observations(db, sub)
    return check_all_subscriptions(db)


# ══════════════════════════════════════════════════════════════════════════════
#  KUBERNETES UTILIZATION  (push from cluster agents)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/k8s/utilization", tags=["Kubernetes"])
def save_k8s(
    payload: K8sUtilizationIn,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    _verify_k8s_agent_token(x_api_key, db)
    record = K8sUtilization(id=str(uuid.uuid4()), **payload.dict())
    db.add(record); db.commit()
    return {"status": "saved", "id": record.id}


@app.post("/k8s/snapshot", tags=["Kubernetes"],
          summary="Ingest batched cluster snapshot from utilization agent")
def save_k8s_snapshot(
    payload: K8sSnapshotIn,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    _verify_k8s_agent_token(x_api_key, db)
    summary = payload.summary or {}
    record = K8sSnapshot(
        id=str(uuid.uuid4()),
        cluster_name=payload.cluster_name,
        node_count=int(summary.get("node_count") or len(payload.nodes)),
        pod_count=int(summary.get("pod_count") or len(payload.pods)),
        payload_json=json.dumps(payload.dict()),
    )
    db.add(record)
    db.commit()
    return {
        "status": "saved",
        "id": record.id,
        "cluster_name": record.cluster_name,
        "node_count": record.node_count,
        "pod_count": record.pod_count,
    }


@app.get("/k8s/snapshot", tags=["Kubernetes"],
         summary="Latest cluster snapshot from utilization agent")
def get_k8s_snapshot(
    request: Request,
    cluster_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    _verify_k8s_read_access(request, x_api_key, db)
    q = db.query(K8sSnapshot).order_by(K8sSnapshot.recorded_at.desc())
    if cluster_name:
        q = q.filter(K8sSnapshot.cluster_name == cluster_name)
    record = q.first()
    if not record:
        raise HTTPException(404, "No snapshot found")
    return {
        "id": record.id,
        "cluster_name": record.cluster_name,
        "node_count": record.node_count,
        "pod_count": record.pod_count,
        "recorded_at": str(record.recorded_at),
        "snapshot": json.loads(record.payload_json or "{}"),
    }


@app.get("/k8s/snapshots", tags=["Kubernetes"],
         summary="List recent cluster snapshots")
def list_k8s_snapshots(
    request: Request,
    cluster_name: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    _verify_k8s_read_access(request, x_api_key, db)
    q = db.query(K8sSnapshot).order_by(K8sSnapshot.recorded_at.desc())
    if cluster_name:
        q = q.filter(K8sSnapshot.cluster_name == cluster_name)
    records = q.limit(limit).all()
    return [{
        "id": r.id,
        "cluster_name": r.cluster_name,
        "node_count": r.node_count,
        "pod_count": r.pod_count,
        "recorded_at": str(r.recorded_at),
    } for r in records]


@app.get("/k8s/utilization", tags=["Kubernetes"])
def get_k8s(
    request: Request,
    cluster_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    _verify_k8s_read_access(request, x_api_key, db)
    q = db.query(K8sUtilization).order_by(K8sUtilization.recorded_at.desc())
    if cluster_name:
        q = q.filter(K8sUtilization.cluster_name == cluster_name)
    records = q.limit(500).all()
    return [{"id": r.id, "cluster": r.cluster_name, "node": r.node_name,
             "pod": r.pod_name, "namespace": r.namespace,
             "cpu": r.cpu_usage, "memory": r.memory_usage,
             "recorded_at": str(r.recorded_at)}
            for r in records]


# ─── Frontend (React build) ───────────────────────────────────────────────────
register_azure_live_routes(app, resource_client, require_admin_user=require_admin_user)
_FRONTEND_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "frontend", "build")
)
configure_production_routes(app, _FRONTEND_DIR)

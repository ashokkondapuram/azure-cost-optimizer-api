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
from typing import Annotated, Any, Literal, Optional, Union

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
# fix G: move previously lazy in-handler imports to module level
from app.resource_type_catalog import parse_resource_types_param, resource_types_catalog

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


# fix I: assign require_admin_user return to _ for consistency with every
# other admin endpoint (raises on failure, but consistent style).
@app.get("/api/openapi.json", include_in_schema=False, tags=["Admin"],
         summary="OpenAPI schema (SPA path, admin only)")
def openapi_json_for_spa(request: Request):
    _ = require_admin_user(request)
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


# fix E: log method + full URL (including query string) for better debuggability.
@app.exception_handler(Exception)
async def unhandled_error_handler(request, exc: Exception):
    log.exception(
        "unhandled_error",
        method=request.method,
        url=str(request.url),
    )
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


# fix A: max_items is NOT a valid Pydantic v2 Field constraint and is silently
# ignored. Use max_length on list fields — Pydantic v2 applies max_length to
# sequences correctly (it is the documented constraint for list size).
class K8sSnapshotIn(BaseModel):
    cluster_name: str = Field(..., min_length=1, max_length=253)
    collected_at: Optional[str] = None
    summary: dict = Field(default_factory=dict)
    nodes: list = Field(default_factory=list, max_length=500)
    pods: list = Field(default_factory=list, max_length=5000)


def _scoped_subscription(db: Session, subscription_id: str) -> str:
    """Validate format and ensure subscription belongs to this deployment."""
    return ensure_subscription_known(db, subscription_id)


# fix #8 / F: validate the *original* stripped string, then slice only after
# the regex passes. Slicing before validation produced a truncated string in
# the error message (e.g. '2026-1-1ex' instead of '2026-1-1extra') and could
# also accept malformed-but-10-char inputs that still fail date parsing later.
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
        raw = from_date.strip()
        if not _DATE_RE.match(raw[:10]) or len(raw) < 10:
            raise HTTPException(
                status_code=422,
                detail=f"from_date must be YYYY-MM-DD; got {from_date!r}",
            )
        kw["from_date"] = raw[:10]
    if (to_date or "").strip():
        raw = to_date.strip()
        if not _DATE_RE.match(raw[:10]) or len(raw) < 10:
            raise HTTPException(
                status_code=422,
                detail=f"to_date must be YYYY-MM-DD; got {to_date!r}",
            )
        kw["to_date"] = raw[:10]
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


# fix H: add per-item max_length cap on string list fields to prevent a single
# oversized item from slipping through the list-level length constraint.
class BulkFindingStatusIn(BaseModel):
    finding_ids: list[Annotated[str, Field(max_length=200)]] = Field(
        ..., min_length=1, max_length=500
    )
    status: str = Field(..
"""Azure Cost Optimizer — Production API v5.0

Includes:
  - Full Cost Management API (v2024-08-01)
  - All resource type endpoints (Compute, AKS, Storage, Network, DB, Security)
  - Optimization Engine with configurable rules + profiles
  - Engine config CRUD (enable/disable rules, override thresholds per profile)
  - Finding history + remediation status tracking
"""
# ── stdlib ────────────────────────────────────────────────────────────────────
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

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
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.http_cache import CacheControlMiddleware
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
    ensure_default_superuser,
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
from app.router_registry import register_api_routers
from app.azure_live_api import register_azure_live_routes

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
        ensure_default_superuser(db)
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

    # Planned maintenance sync (Azure → DB every 2 hours).
    from app import maintenance_worker
    maintenance_worker.start()

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


# ── Middleware stack (outermost → innermost call order) ───────────────────────
# SecurityHeadersMiddleware must wrap everything so headers are added even
# when inner middleware short-circuits (e.g. CORS pre-flight, auth 401).
app.add_middleware(SecurityHeadersMiddleware, is_production=settings.is_production)
app.add_middleware(DynamicCORSMiddleware)
app.add_middleware(AppAuthMiddleware)
app.add_middleware(CacheControlMiddleware)

# Trust the Azure-injected X-Forwarded-For header from App Service / App Gateway
# so that client_ip resolution in rate-limiting sees the real caller IP, not the
# proxy address.  ONLY enable this when the app sits behind a known trusted proxy.
if settings.is_production:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

# Register all API domain routers (dashboard, resources, costs, optimize, advanced tools, …)
register_api_routers(app)

# These singletons are intentionally module-level for shared HTTP connection
# pool reuse. They do not hold credentials directly — credentials are resolved
# lazily per-request via get_arm_token(db). Instantiation here is safe because
# no credential loading occurs at construction time.
cost_client     = AzureCostClient()
resource_client = AzureResourcesClient()

register_azure_live_routes(app, resource_client, require_admin_user=require_admin_user)


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


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    # Version omitted — avoid disclosing build info to unauthenticated callers.
    return {"status": "ok"}


@app.get("/health/live", tags=["System"])
def health_live():
    return {"status": "ok"}


@app.get("/health/microservices", tags=["System"])
def health_microservices():
    """Report strangler migration status — monolith remains fallback for unmigrated types."""
    import sys
    from pathlib import Path

    core_pkg = Path(__file__).resolve().parents[1] / "packages" / "costoptimizer-core"
    if str(core_pkg) not in sys.path:
        sys.path.insert(0, str(core_pkg))

    from app.microservices import GATEWAY_URL, MICROSERVICES_ENABLED, MONOLITH_FALLBACK_URL
    from costoptimizer_core.registry import MIGRATED_SERVICES, all_service_configs

    return {
        "enabled": MICROSERVICES_ENABLED,
        "gateway_url": GATEWAY_URL,
        "monolith_url": MONOLITH_FALLBACK_URL,
        "migrated_services": sorted(MIGRATED_SERVICES),
        "total_services": len(all_service_configs()),
    }


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
    # Version is exposed here — only reached by authenticated infra probes.
    return {"status": "ready", "version": __version__, **checks}


# Wire production routing AFTER all routes registered: /api mirrors + SPA serving
import os
from app.production_routes import configure_production_routes
_FRONTEND_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "frontend", "build")
)
configure_production_routes(app, _FRONTEND_DIR)

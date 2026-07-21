from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
import os
import threading
import structlog

from app.platform import get_app_service_database_url, normalize_database_url

logger = structlog.get_logger(__name__)

DEFAULT_SQLITE_URL = "sqlite:///./azurefinops.db"


def get_bootstrap_database_url() -> str:
    """URL used on process start. App Service connection strings take precedence."""
    app_service_url = get_app_service_database_url()
    if app_service_url:
        return app_service_url
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return normalize_database_url(env_url)
    return DEFAULT_SQLITE_URL


def _pool_size(url: str) -> int:
    if url.startswith("sqlite"):
        return 1
    from app.settings import get_settings

    return get_settings().database_pool_size


def _max_overflow(url: str) -> int:
    if url.startswith("sqlite"):
        return 0
    from app.settings import get_settings

    return get_settings().database_max_overflow


def _pool_timeout(url: str) -> float:
    if url.startswith("sqlite"):
        return 30.0
    from app.settings import get_settings

    return get_settings().database_pool_timeout_sec


def _pool_recycle(url: str) -> int:
    if url.startswith("sqlite"):
        return 1800
    from app.settings import get_settings

    return get_settings().database_pool_recycle_sec


def _make_engine(url: str):
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        eng = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        eng = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=_pool_size(url),
            max_overflow=_max_overflow(url),
            pool_timeout=_pool_timeout(url),
            pool_recycle=_pool_recycle(url),
        )

    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return eng


_active_url = get_bootstrap_database_url()
engine = _make_engine(_active_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
_engine_lock = threading.RLock()


def get_active_database_url() -> str:
    return _active_url


def get_db():
    with _engine_lock:
        db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def reconfigure_engine(url: str) -> None:
    """Switch the active SQLAlchemy engine without restarting the process."""
    global engine, SessionLocal, _active_url

    if url == _active_url:
        return

    with _engine_lock:
        if url == _active_url:
            return

        old_engine = engine
        engine = _make_engine(url)
        SessionLocal.configure(bind=engine)
        _active_url = url
        logger.info("database_reconfigured", old_url=_active_url, new_url=url)
        old_engine.dispose(close=True)


def init_db():
    """Create all tables. Called on startup."""
    from .models import Base
    Base.metadata.create_all(bind=engine)
    migrate_schema()


def migrate_schema():
    """Add new columns to existing tables without Alembic."""
    from sqlalchemy import inspect, text

    is_pg = engine.dialect.name == "postgresql"
    datetime_type = "TIMESTAMP WITH TIME ZONE" if is_pg else "DATETIME"

    insp = inspect(engine)
    if not insp.has_table("optimization_findings"):
        # Fresh database — create all tables including system_settings.
        from .models import Base
        Base.metadata.create_all(bind=engine)
        from app.data_store.enrichment_registry import ensure_priority_enrichment_tables
        ensure_priority_enrichment_tables(engine)
        return

    finding_cols = {c["name"] for c in insp.get_columns("optimization_findings")}
    for col, typedef in {
        "annualized_savings_usd": "FLOAT DEFAULT 0",
        "confidence_score": "INTEGER DEFAULT 0",
        "action_priority": "VARCHAR",
        "impact": "TEXT",
        "evidence_json": "TEXT DEFAULT '{}'",
        "chain_id": "VARCHAR(64)",
        "chain_step": "INTEGER",
        "chain_total": "INTEGER",
    }.items():
        if col not in finding_cols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE optimization_findings ADD COLUMN {col} {typedef}"))

    if insp.has_table("optimization_runs"):
        run_cols = {c["name"] for c in insp.get_columns("optimization_runs")}
        if "engine_version" not in run_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE optimization_runs ADD COLUMN engine_version VARCHAR DEFAULT 'standard'"))

    if not insp.has_table("system_settings"):
        from .models import SystemSetting
        SystemSetting.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("app_users"):
        from .models import AppUser
        AppUser.__table__.create(bind=engine, checkfirst=True)
        from app.user_auth import ensure_default_admin, ensure_default_viewer, ensure_default_superuser
        db = SessionLocal()
        try:
            ensure_default_admin(db)
            ensure_default_viewer(db)
            ensure_default_superuser(db)
        finally:
            db.close()

    if insp.has_table("cost_by_service"):
        cbs_cols = {c["name"] for c in insp.get_columns("cost_by_service")}
        for col, typedef in {
            "cost_billing": "FLOAT",
            "billing_currency": "VARCHAR DEFAULT 'CAD'",
        }.items():
            if col not in cbs_cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE cost_by_service ADD COLUMN {col} {typedef}"))

    if insp.has_table("resource_snapshots"):
        rs_cols = {c["name"] for c in insp.get_columns("resource_snapshots")}
        for col, typedef in {
            "analysis_findings_count": "INTEGER DEFAULT 0",
            "analysis_savings_usd": "FLOAT DEFAULT 0",
            "analysis_top_severity": "VARCHAR",
            "analysis_updated_at": datetime_type,
            "analysis_run_id": "VARCHAR",
            "analysis_data_source": "VARCHAR",
            "analysis_summary_json": "TEXT DEFAULT '[]'",
            "monthly_cost_billing": "FLOAT DEFAULT 0",
            "billing_currency": "VARCHAR DEFAULT 'CAD'",
            "azure_service_name": "VARCHAR",
            "sku_json": "TEXT DEFAULT '{}'",
        }.items():
            if col not in rs_cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE resource_snapshots ADD COLUMN {col} {typedef}"))

    if not insp.has_table("analysis_jobs"):
        from .models import AnalysisJob
        AnalysisJob.__table__.create(bind=engine, checkfirst=True)
    elif insp.has_table("analysis_jobs"):
        aj_cols = {c["name"] for c in insp.get_columns("analysis_jobs")}
        if "rule_overrides_json" not in aj_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE analysis_jobs ADD COLUMN rule_overrides_json TEXT DEFAULT '{}'"))

    if insp.has_table("cost_snapshots"):
        cs_cols = {c["name"] for c in insp.get_columns("cost_snapshots")}
        if "cost_billing" not in cs_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE cost_snapshots ADD COLUMN cost_billing FLOAT"))

    if not insp.has_table("cost_daily_by_service"):
        from .models import CostDailyByServiceSnapshot
        CostDailyByServiceSnapshot.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("cost_by_resource"):
        from .models import CostByResourceSnapshot
        CostByResourceSnapshot.__table__.create(bind=engine, checkfirst=True)
    elif insp.has_table("cost_by_resource"):
        cbr_cols = {c["name"] for c in insp.get_columns("cost_by_resource")}
        for col, typedef in {
            "azure_exists": "BOOLEAN",
            "azure_checked_at": datetime_type,
        }.items():
            if col not in cbr_cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE cost_by_resource ADD COLUMN {col} {typedef}"))

    if not insp.has_table("cost_sync_runs"):
        from .models import CostSyncRun
        CostSyncRun.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("cost_period_totals"):
        from .models import CostPeriodTotalSnapshot
        CostPeriodTotalSnapshot.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("k8s_utilization"):
        from .models import K8sUtilization
        K8sUtilization.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("k8s_snapshots"):
        from .models import K8sSnapshot
        K8sSnapshot.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("k8s_cluster_connections"):
        from .models import K8sClusterConnection
        K8sClusterConnection.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("login_attempts"):
        from .models import LoginAttempt
        LoginAttempt.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("azure_token_cache"):
        from .models import AzureTokenCache
        AzureTokenCache.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("component_sync_state"):
        from .models import ComponentSyncState
        ComponentSyncState.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("maintenance_sync_runs"):
        from .models import MaintenanceSyncRun
        MaintenanceSyncRun.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("planned_maintenance_items"):
        from .models import PlannedMaintenanceItem
        PlannedMaintenanceItem.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("cost_by_resource_type"):
        from .models import CostByResourceTypeSnapshot
        CostByResourceTypeSnapshot.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("resource_pricing_profiles"):
        from .models import ResourcePricingProfile
        ResourcePricingProfile.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("resource_sku_pricing"):
        from .models import ResourceSkuPricing
        ResourceSkuPricing.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("finding_activity"):
        from .models import FindingActivity
        FindingActivity.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("resource_dependencies"):
        from .models import ResourceDependency
        ResourceDependency.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("recommendation_executions"):
        from .models import RecommendationExecution
        RecommendationExecution.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("advisor_recommendations"):
        from .models import AdvisorRecommendation
        AdvisorRecommendation.__table__.create(bind=engine, checkfirst=True)
    elif insp.has_table("advisor_recommendations"):
        advisor_cols = {c["name"] for c in insp.get_columns("advisor_recommendations")}
        for col, typedef in {
            "recommendation_type_id": "VARCHAR",
            "current_sku": "VARCHAR",
            "target_sku": "VARCHAR",
        }.items():
            if col not in advisor_cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE advisor_recommendations ADD COLUMN {col} {typedef}"))

    if not insp.has_table("optimization_actions"):
        from .models import OptimizationAction
        OptimizationAction.__table__.create(bind=engine, checkfirst=True)
    elif insp.has_table("optimization_actions"):
        oa_cols = {c["name"] for c in insp.get_columns("optimization_actions")}
        for col, typedef in {
            "recommendation_tier": "VARCHAR",
            "overall_score": "FLOAT",
        }.items():
            if col not in oa_cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE optimization_actions ADD COLUMN {col} {typedef}"))

    if not insp.has_table("workload_profiles"):
        from .models import WorkloadProfile
        WorkloadProfile.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("optimization_scoring"):
        from .models import OptimizationScoring
        OptimizationScoring.__table__.create(bind=engine, checkfirst=True)

    if not insp.has_table("optimization_rollout_stages"):
        from .models import OptimizationRolloutStage
        OptimizationRolloutStage.__table__.create(bind=engine, checkfirst=True)

    if insp.has_table("resource_dependencies"):
        rd_cols = {c["name"] for c in insp.get_columns("resource_dependencies")}
        if "criticality" not in rd_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE resource_dependencies ADD COLUMN criticality VARCHAR DEFAULT 'medium'"))

    if insp.has_table("optimization_findings"):
        finding_cols = {c["name"] for c in insp.get_columns("optimization_findings")}
        for col, typedef in {
            "advisor_recommendation_id": "VARCHAR",
            "linked_action_id": "VARCHAR",
        }.items():
            if col not in finding_cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE optimization_findings ADD COLUMN {col} {typedef}"))

    if is_pg and insp.has_table("resource_snapshots"):
        with engine.begin() as conn:
            try:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_rs_props_gin ON resource_snapshots "
                    "USING gin ((properties_json::jsonb))"
                ))
            except Exception:
                pass
            try:
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_rs_sub_resource "
                    "ON resource_snapshots (subscription_id, resource_id)"
                ))
            except Exception:
                pass

    if insp.has_table("optimization_findings"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE optimization_findings SET status = lower(status) WHERE status IS NOT NULL"))

    if insp.has_table("resource_snapshots"):
        rs_cols = {c["name"] for c in insp.get_columns("resource_snapshots")}
        if "is_cost_export_only" not in rs_cols:
            bool_default = "false" if is_pg else "0"
            bool_true = "true" if is_pg else "1"
            with engine.begin() as conn:
                conn.execute(text(
                    f"ALTER TABLE resource_snapshots ADD COLUMN is_cost_export_only BOOLEAN DEFAULT {bool_default}"
                ))
                conn.execute(text(
                    f"UPDATE resource_snapshots SET is_cost_export_only = {bool_true} "
                    "WHERE properties_json LIKE '%\"source\": \"cost_export\"%'"
                ))
        for index_name, ddl in {
            "ix_rs_sub_type": "CREATE INDEX IF NOT EXISTS ix_rs_sub_type ON resource_snapshots (subscription_id, resource_type)",
            "ix_rs_sub_active": "CREATE INDEX IF NOT EXISTS ix_rs_sub_active ON resource_snapshots (subscription_id, is_active)",
            "ix_rs_type": "CREATE INDEX IF NOT EXISTS ix_rs_type ON resource_snapshots (resource_type)",
            "ix_rs_sub_export": "CREATE INDEX IF NOT EXISTS ix_rs_sub_export ON resource_snapshots (subscription_id, is_cost_export_only)",
        }.items():
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
            except Exception:
                pass

    for table_name, model_cls in (
        ("resource_assessment_results", "ResourceAssessmentResult"),
        ("pipeline_runs", "PipelineRun"),
    ):
        if not insp.has_table(table_name):
            from app import models as app_models
            getattr(app_models, model_cls).__table__.create(bind=engine, checkfirst=True)

    from app.data_store.enrichment_registry import (
        drop_deprecated_tables,
        ensure_priority_enrichment_tables,
        migrate_enrichment_table_columns,
        migrate_unified_enrichment_table,
    )

    migrate_unified_enrichment_table(engine)
    ensure_priority_enrichment_tables(engine)
    migrate_enrichment_table_columns(engine)
    drop_deprecated_tables(engine)

    from app.data_store.enrichment_properties import (
        ensure_property_values_table,
        migrate_properties_from_enrichment_json,
    )

    ensure_property_values_table(engine)
    try:
        migrate_properties_from_enrichment_json(engine)
    except Exception:
        pass

    if insp.has_table("analysis_jobs"):
        aj_cols = {c["name"] for c in insp.get_columns("analysis_jobs")}
        for col, typedef in {
            "pipeline_stage": "VARCHAR",
            "stage_results_json": "TEXT DEFAULT '{}'",
        }.items():
            if col not in aj_cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE analysis_jobs ADD COLUMN {col} {typedef}"))

    if not insp.has_table("full_sync_pipeline_runs"):
        from app.models import FullSyncPipelineRun
        FullSyncPipelineRun.__table__.create(bind=engine, checkfirst=True)

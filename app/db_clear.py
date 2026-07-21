"""Clear synced Azure data or every application table in the database."""

from __future__ import annotations

import structlog
from typing import Literal, Optional

from sqlalchemy.orm import Session

from app.models import (
    AdvisorRecommendation,
    AnalysisJob,
    AppUser,
    AzureTokenCache,
    BudgetSnapshot,
    ComponentSyncState,
    CostByResourceSnapshot,
    CostByResourceTypeSnapshot,
    CostByServiceSnapshot,
    CostDailyByServiceSnapshot,
    CostPeriodTotalSnapshot,
    CostRecord,
    CostSnapshot,
    CostSyncRun,
    CustomBudget,
    EngineConfig,
    FindingActivity,
    K8sSnapshot,
    K8sClusterConnection,
    K8sUtilization,
    LoginAttempt,
    MaintenanceSyncRun,
    OptimizationAction,
    OptimizationFinding,
    OptimizationRolloutStage,
    OptimizationRun,
    OptimizationScoring,
    PipelineRun,
    PlannedMaintenanceItem,
    RecommendationExecution,
    ResourceAssessmentResult,
    ResourceDependency,
    ResourcePricingProfile,
    ResourceSkuPricing,
    ResourceSnapshot,
    SubscriptionCache,
    SystemSetting,
    WorkloadProfile,
)
from app.data_store.enrichment_registry import iter_existing_enrichment_models

log = structlog.get_logger(__name__)

ClearMode = Literal["synced", "all"]

_PRESERVED_SYNCED = ("app_users", "system_settings", "engine_configs", "login_attempts")

# Child/workflow rows first; no FK constraints but logical ordering helps debugging.
_SYNCED_MODELS = (
    FindingActivity,
    OptimizationAction,
    OptimizationFinding,
    OptimizationRun,
    AnalysisJob,
    OptimizationRolloutStage,
    OptimizationScoring,
    WorkloadProfile,
    ResourceDependency,
    ResourceAssessmentResult,
    ResourcePricingProfile,
    AdvisorRecommendation,
    PipelineRun,
    ResourceSnapshot,
    CostSnapshot,
    CostDailyByServiceSnapshot,
    CostByResourceSnapshot,
    CostByResourceTypeSnapshot,
    CostByServiceSnapshot,
    CostPeriodTotalSnapshot,
    CostSyncRun,
    BudgetSnapshot,
    CustomBudget,
    CostRecord,
    MaintenanceSyncRun,
    PlannedMaintenanceItem,
    SubscriptionCache,
)

# Tables without subscription_id — cleared only for full subscription scope.
_GLOBAL_SYNCED_MODELS = (
    K8sUtilization,
    K8sSnapshot,
    K8sClusterConnection,
    ComponentSyncState,
    AzureTokenCache,
)

_ALL_EXTRA_MODELS = (
    AppUser,
    SystemSetting,
    EngineConfig,
    LoginAttempt,
)


def _norm_sub(subscription_id: Optional[str]) -> Optional[str]:
    return subscription_id.lower() if subscription_id else None


def _delete_model_rows(
    db: Session,
    model,
    subscription_id: Optional[str] = None,
) -> int:
    q = db.query(model)
    if subscription_id and hasattr(model, "subscription_id"):
        q = q.filter(model.subscription_id == subscription_id)
    return q.delete(synchronize_session=False)


def _delete_recommendation_executions(
    db: Session,
    subscription_id: Optional[str] = None,
) -> int:
    q = db.query(RecommendationExecution)
    if subscription_id:
        finding_ids = [
            row[0]
            for row in db.query(OptimizationFinding.id)
            .filter(OptimizationFinding.subscription_id == subscription_id)
            .all()
        ]
        if not finding_ids:
            return 0
        q = q.filter(RecommendationExecution.finding_id.in_(finding_ids))
    return q.delete(synchronize_session=False)


def _delete_enrichment_rows(db: Session, subscription_id: Optional[str] = None) -> dict[str, int]:
    deleted: dict[str, int] = {}
    for model in iter_existing_enrichment_models(db.get_bind()):
        deleted[model.__tablename__] = _delete_model_rows(db, model, subscription_id)
    return deleted


def clear_synced_data(db: Session, subscription_id: Optional[str] = None) -> dict[str, int]:
    """Delete synced operational data. Optionally scope to one subscription."""
    sub = _norm_sub(subscription_id)
    deleted: dict[str, int] = {}

    deleted[RecommendationExecution.__tablename__] = _delete_recommendation_executions(db, sub)

    for model in _SYNCED_MODELS:
        deleted[model.__tablename__] = _delete_model_rows(db, model, sub)

    deleted.update(_delete_enrichment_rows(db, sub))

    if not sub:
        for model in _GLOBAL_SYNCED_MODELS:
            deleted[model.__tablename__] = _delete_model_rows(db, model)

    db.commit()
    log.info("db_clear_synced_complete", subscription_id=sub or "all", deleted=deleted)
    return deleted


def clear_all_tables(db: Session) -> dict[str, int]:
    """Delete every row from every application table."""
    deleted: dict[str, int] = {}

    deleted[RecommendationExecution.__tablename__] = _delete_recommendation_executions(db)

    for model in _SYNCED_MODELS:
        deleted[model.__tablename__] = _delete_model_rows(db, model)

    deleted.update(_delete_enrichment_rows(db))

    for model in _GLOBAL_SYNCED_MODELS:
        deleted[model.__tablename__] = _delete_model_rows(db, model)

    for model in _ALL_EXTRA_MODELS:
        deleted[model.__tablename__] = _delete_model_rows(db, model)

    db.commit()
    log.info("db_clear_all_complete", deleted=deleted)
    return deleted


def clear_database(
    db: Session,
    *,
    subscription_id: Optional[str] = None,
    mode: ClearMode = "synced",
) -> dict:
    """Clear database rows. mode=synced keeps users/settings; mode=all wipes every table."""
    if mode == "all":
        if subscription_id:
            log.warning(
                "db_clear_all_ignores_subscription_scope",
                subscription_id=subscription_id,
            )
        deleted = clear_all_tables(db)
        return {
            "mode": "all",
            "subscription_id": None,
            "deleted": deleted,
            "preserved_tables": [],
        }

    sub = _norm_sub(subscription_id)
    deleted = clear_synced_data(db, subscription_id=sub)
    return {
        "mode": "synced",
        "subscription_id": sub,
        "deleted": deleted,
        "preserved_tables": list(_PRESERVED_SYNCED),
    }


if __name__ == "__main__":
    import sys

    from app.database import SessionLocal, migrate_schema

    migrate_schema()
    sub_arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else None
    mode_arg: ClearMode = "all" if "--all" in sys.argv else "synced"
    db = SessionLocal()
    try:
        result = clear_database(db, subscription_id=sub_arg, mode=mode_arg)
        print(f"Cleared database ({result['mode']}):")
        for table, count in result["deleted"].items():
            print(f"  {table}: {count} rows")
        preserved = result.get("preserved_tables") or []
        if preserved:
            print("Preserved:", ", ".join(preserved))
    finally:
        db.close()

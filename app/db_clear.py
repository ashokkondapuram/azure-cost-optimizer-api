"""Clear synced Azure inventory, costs, findings, and analysis runs from the database.

Preserves app_users, system_settings, and engine_configs.
"""

from __future__ import annotations

import structlog
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    AnalysisJob,
    BudgetSnapshot,
    CostByResourceSnapshot,
    CostByServiceSnapshot,
    CostDailyByServiceSnapshot,
    CostRecord,
    CostSnapshot,
    K8sSnapshot,
    K8sUtilization,
    OptimizationFinding,
    OptimizationRun,
    ResourceSnapshot,
    SubscriptionCache,
)

log = structlog.get_logger(__name__)

# Order: findings before runs (logical); no FK constraints in schema.
_CLEAR_MODELS = (
    OptimizationFinding,
    OptimizationRun,
    AnalysisJob,
    ResourceSnapshot,
    CostSnapshot,
    CostDailyByServiceSnapshot,
    CostByResourceSnapshot,
    CostByServiceSnapshot,
    BudgetSnapshot,
    CostRecord,
    SubscriptionCache,
    K8sUtilization,
    K8sSnapshot,
)

_PRESERVED = ("app_users", "system_settings", "engine_configs")


def clear_synced_data(db: Session, subscription_id: Optional[str] = None) -> dict[str, int]:
    """Delete synced operational data. Optionally scope to one subscription."""
    sub = subscription_id.lower() if subscription_id else None
    deleted: dict[str, int] = {}

    for model in _CLEAR_MODELS:
        q = db.query(model)
        if sub and hasattr(model, "subscription_id"):
            q = q.filter(model.subscription_id == sub)
        count = q.delete(synchronize_session=False)
        deleted[model.__tablename__] = count

    db.commit()
    log.info("db_clear_complete", subscription_id=sub or "all", deleted=deleted)
    return {
        "subscription_id": sub,
        "deleted": deleted,
        "preserved_tables": list(_PRESERVED),
    }


if __name__ == "__main__":
    import sys

    from app.database import SessionLocal, migrate_schema

    migrate_schema()
    sub_arg = sys.argv[1] if len(sys.argv) > 1 else None
    db = SessionLocal()
    try:
        result = clear_synced_data(db, subscription_id=sub_arg)
        print("Cleared database:")
        for table, count in result["deleted"].items():
            print(f"  {table}: {count} rows")
        print("Preserved:", ", ".join(result["preserved_tables"]))
    finally:
        db.close()

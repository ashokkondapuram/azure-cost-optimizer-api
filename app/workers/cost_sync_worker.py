"""Pipeline cost sync — refresh cost export before metrics and analysis."""

from __future__ import annotations

import os
import structlog
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import CostSyncRun

log = structlog.get_logger(__name__)


def cost_freshness_max_hours() -> float:
    return max(1.0, float(os.getenv("PIPELINE_COST_FRESHNESS_HOURS", "30")))


def cost_data_fresh(db: Session, subscription_id: str) -> bool:
    sub = subscription_id.lower()
    run = (
        db.query(CostSyncRun)
        .filter(CostSyncRun.subscription_id == sub)
        .order_by(desc(CostSyncRun.synced_at))
        .first()
    )
    if not run or not run.synced_at:
        return False
    synced = run.synced_at
    if synced.tzinfo is None:
        synced = synced.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - synced) <= timedelta(hours=cost_freshness_max_hours())


def cost_sync_worker_enabled() -> bool:
    return os.getenv("PIPELINE_COST_SYNC_ENABLED", "true").lower() not in {"0", "false", "no"}


def run_cost_sync_worker(
    db: Session,
    subscription_id: str,
    *,
    token: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Sync cost export when stale. Failures are recorded but do not raise."""
    sub = subscription_id.lower()
    stats: dict[str, Any] = {"subscription_id": sub}

    if not cost_sync_worker_enabled():
        stats["status"] = "disabled"
        return stats

    if not force and cost_data_fresh(db, sub):
        stats["status"] = "fresh"
        stats["skipped"] = True
        return stats

    try:
        from app.auth import get_token
        from app.db_sync import sync_costs

        bearer = token or get_token(db)
        result = sync_costs(sub, db, bearer)
        stats["status"] = "ok"
        stats["synced"] = result
        stats["completed_at"] = datetime.now(timezone.utc).isoformat()
        log.info("cost_sync_worker.done", subscription_id=sub)
        return stats
    except Exception as exc:
        log.exception("cost_sync_worker.failed", subscription_id=sub, error=str(exc))
        stats["status"] = "failed"
        stats["error"] = str(exc)[:500]
        stats["message"] = "Cost sync failed; metrics and analysis will use cached cost data."
        return stats

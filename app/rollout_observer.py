"""Scheduled checks for rollout observation windows."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.models import OptimizationRolloutStage
from app.optimizer.rollout_orchestrator import evaluate_rollout_stage

log = structlog.get_logger()


def check_rollout_observations(db: Session, subscription_id: str | None = None) -> dict[str, Any]:
    """Evaluate in-progress rollout stages; flag ready for expand or regression."""
    q = db.query(OptimizationRolloutStage).filter(
        OptimizationRolloutStage.status == "in_progress",
    )
    if subscription_id:
        q = q.filter(OptimizationRolloutStage.subscription_id == subscription_id.strip().lower())

    stages = q.all()
    ready_to_expand: list[str] = []
    needs_rollback: list[str] = []
    waiting: list[str] = []

    for stage in stages:
        evaluation = evaluate_rollout_stage(db, stage)
        if evaluation["metrics_regressed"]:
            needs_rollback.append(stage.id)
        elif evaluation["recommendation"] == "expand":
            ready_to_expand.append(stage.id)
        else:
            waiting.append(stage.id)

    if ready_to_expand or needs_rollback:
        db.commit()

    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "in_progress": len(stages),
        "ready_to_expand": ready_to_expand,
        "needs_rollback": needs_rollback,
        "waiting": waiting,
    }
    log.info("rollout_observation.checked", **{k: result[k] for k in ("in_progress", "ready_to_expand", "needs_rollback")})
    return result


def check_all_subscriptions(db: Session) -> dict[str, Any]:
    from app.scheduler_utils import list_subscription_ids

    subs = list_subscription_ids(db)
    combined = {
        "subscriptions": len(subs),
        "ready_to_expand": [],
        "needs_rollback": [],
        "waiting": [],
    }
    for sub in subs:
        result = check_rollout_observations(db, sub)
        combined["ready_to_expand"].extend(result["ready_to_expand"])
        combined["needs_rollback"].extend(result["needs_rollback"])
        combined["waiting"].extend(result["waiting"])
    return combined

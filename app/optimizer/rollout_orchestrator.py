"""Staged rollout planning, observation windows, expand and rollback."""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.metrics_loader import load_cached_resource_facts
from app.models import OptimizationAction, OptimizationRolloutStage
from app.optimization_actions import update_optimization_action
from app.utils import today_iso, utc_now

log = structlog.get_logger()

_TIER_OBSERVATION_DAYS = {
    "tier1_safe": 0,
    "tier2_balanced": 7,
    "tier3_risky": 14,
}

_TIER_STAGE_NUMBER = {
    "tier1_safe": 1,
    "tier2_balanced": 2,
    "tier3_risky": 3,
}

_METRIC_KEYS = ("avg_cpu_pct", "max_cpu_pct", "avg_memory_pct")


def _parse_json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    try:
        parsed = json.loads(value)
        return [str(v) for v in parsed] if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def _parse_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _actions_for_stage(db: Session, stage: OptimizationRolloutStage) -> list[OptimizationAction]:
    ids = _parse_json_list(stage.action_ids_json)
    if not ids:
        return []
    return (
        db.query(OptimizationAction)
        .filter(OptimizationAction.id.in_(ids))
        .all()
    )


def _capture_metrics_snapshot(
    db: Session,
    subscription_id: str,
    action_ids: list[str],
) -> dict[str, Any]:
    facts_map = load_cached_resource_facts(db, subscription_id)
    actions = db.query(OptimizationAction).filter(OptimizationAction.id.in_(action_ids)).all()
    per_resource: dict[str, dict[str, float]] = {}
    for action in actions:
        rid = (action.resource_id or "").strip().lower()
        facts = facts_map.get(rid) or {}
        per_resource[rid] = {k: float(facts.get(k) or 0) for k in _METRIC_KEYS if facts.get(k) is not None}
    return {"captured_at": utc_now().isoformat(), "resources": per_resource}


def _metrics_regressed(baseline: dict[str, Any], current: dict[str, Any], *, threshold_pct: float = 25.0) -> bool:
    base_resources = baseline.get("resources") or {}
    cur_resources = current.get("resources") or {}
    for rid, base_metrics in base_resources.items():
        cur_metrics = cur_resources.get(rid) or {}
        base_cpu = float(base_metrics.get("avg_cpu_pct") or base_metrics.get("max_cpu_pct") or 0)
        cur_cpu = float(cur_metrics.get("avg_cpu_pct") or cur_metrics.get("max_cpu_pct") or 0)
        if base_cpu > 0 and cur_cpu > base_cpu * (1 + threshold_pct / 100):
            return True
    return False


def serialize_rollout_stage(stage: OptimizationRolloutStage) -> dict[str, Any]:
    action_ids = _parse_json_list(stage.action_ids_json)
    obs_start = stage.observation_start_date
    window = stage.observation_window_days or 0
    observation_complete = False
    days_elapsed = None
    if obs_start and window > 0:
        start = date.fromisoformat(obs_start)
        days_elapsed = (date.today() - start).days
        observation_complete = days_elapsed >= window
    elif window == 0 and stage.status == "in_progress":
        observation_complete = True

    return {
        "id": stage.id,
        "subscription_id": stage.subscription_id,
        "stage_number": stage.stage_number,
        "stage_tier": stage.stage_tier,
        "action_ids": action_ids,
        "resources_in_stage": stage.resources_in_stage,
        "resources_approved": stage.resources_approved,
        "resources_executed": stage.resources_executed,
        "resources_rolled_back": stage.resources_rolled_back,
        "observation_window_days": window,
        "observation_start_date": obs_start,
        "observation_days_elapsed": days_elapsed,
        "observation_complete": observation_complete,
        "observation_metrics": _parse_json_dict(stage.observation_metrics_json),
        "post_change_metrics": _parse_json_dict(stage.post_change_metrics_json),
        "rollback_triggered": bool(stage.rollback_triggered),
        "rollback_reason": stage.rollback_reason,
        "status": stage.status,
        "created_at": stage.created_at.isoformat() if stage.created_at else None,
        "completed_at": stage.completed_at.isoformat() if stage.completed_at else None,
    }


def plan_rollout_stages(
    db: Session,
    subscription_id: str,
    *,
    replace_existing: bool = False,
) -> dict[str, Any]:
    """Group proposed/approved actions into rollout stages by recommendation tier."""
    sub = subscription_id.strip().lower()

    if replace_existing:
        db.query(OptimizationRolloutStage).filter(
            OptimizationRolloutStage.subscription_id == sub,
            OptimizationRolloutStage.status.in_(["proposed"]),
        ).delete(synchronize_session=False)

    actions = (
        db.query(OptimizationAction)
        .filter(
            OptimizationAction.subscription_id == sub,
            OptimizationAction.workflow_status.in_(["proposed", "approved"]),
            OptimizationAction.recommendation_tier.in_(["tier1_safe", "tier2_balanced", "tier3_risky"]),
        )
        .all()
    )

    by_tier: dict[str, list[OptimizationAction]] = defaultdict(list)
    for action in actions:
        tier = action.recommendation_tier or "tier3_risky"
        by_tier[tier].append(action)

    created = 0

    # Tier 1: one batch stage for all safe actions
    tier1 = by_tier.get("tier1_safe", [])
    if tier1:
        db.add(_new_stage(sub, tier1, "tier1_safe"))
        created += 1

    # Tier 2: batch by action_type
    tier2 = by_tier.get("tier2_balanced", [])
    by_action_type: dict[str, list[OptimizationAction]] = defaultdict(list)
    for action in tier2:
        by_action_type[action.action_type or "investigate"].append(action)
    for group in by_action_type.values():
        db.add(_new_stage(sub, group, "tier2_balanced"))
        created += 1

    # Tier 3: one stage per action
    for action in by_tier.get("tier3_risky", []):
        db.add(_new_stage(sub, [action], "tier3_risky"))
        created += 1

    db.commit()
    return {"status": "ok", "subscription_id": sub, "stages_created": created}


def _new_stage(
    subscription_id: str,
    actions: list[OptimizationAction],
    tier: str,
) -> OptimizationRolloutStage:
    action_ids = [a.id for a in actions]
    return OptimizationRolloutStage(
        id=str(uuid.uuid4()),
        subscription_id=subscription_id,
        stage_number=_TIER_STAGE_NUMBER.get(tier, 3),
        stage_tier=tier,
        action_ids_json=action_ids,
        resources_in_stage=len(actions),
        observation_window_days=_TIER_OBSERVATION_DAYS.get(tier, 7),
        status="proposed",
        created_at=utc_now(),
    )


def list_rollout_stages(
    db: Session,
    subscription_id: str,
    *,
    status: str | None = None,
    tier: str | None = None,
) -> dict[str, Any]:
    sub = subscription_id.strip().lower()
    q = db.query(OptimizationRolloutStage).filter(OptimizationRolloutStage.subscription_id == sub)
    if status:
        q = q.filter(OptimizationRolloutStage.status == status.strip().lower())
    if tier:
        q = q.filter(OptimizationRolloutStage.stage_tier == tier.strip().lower())
    rows = q.order_by(
        OptimizationRolloutStage.stage_number.asc(),
        OptimizationRolloutStage.created_at.asc(),
    ).all()
    summary: dict[str, int] = defaultdict(int)
    for row in rows:
        summary[row.status or "proposed"] += 1
    return {
        "subscription_id": sub,
        "count": len(rows),
        "status_summary": dict(summary),
        "items": [serialize_rollout_stage(r) for r in rows],
    }


def start_rollout_stage(
    db: Session,
    stage: OptimizationRolloutStage,
    *,
    user: dict | None = None,
) -> OptimizationRolloutStage:
    """Begin stage: capture baseline metrics and mark in progress."""
    action_ids = _parse_json_list(stage.action_ids_json)
    stage.observation_metrics_json = _capture_metrics_snapshot(
        db, stage.subscription_id, action_ids,
    )
    stage.observation_start_date = today_iso()
    stage.status = "in_progress"

    approved = 0
    for action in _actions_for_stage(db, stage):
        if action.workflow_status == "proposed":
            update_optimization_action(
                db, action,
                workflow_status="approved",
                user=user,
                note="Approved via rollout stage start",
            )
            approved += 1
    stage.resources_approved = approved

    return stage


def evaluate_rollout_stage(db: Session, stage: OptimizationRolloutStage) -> dict[str, Any]:
    """Check observation window and compare metrics."""
    action_ids = _parse_json_list(stage.action_ids_json)
    current = _capture_metrics_snapshot(db, stage.subscription_id, action_ids)
    stage.post_change_metrics_json = current

    baseline = _parse_json_dict(stage.observation_metrics_json)
    regressed = _metrics_regressed(baseline, current)
    window = stage.observation_window_days or 0
    obs_start = stage.observation_start_date
    days_elapsed = 0
    if obs_start:
        days_elapsed = (date.today() - date.fromisoformat(obs_start)).days

    observation_complete = window == 0 or (obs_start and days_elapsed >= window)

    return {
        "observation_complete": observation_complete,
        "days_elapsed": days_elapsed,
        "metrics_regressed": regressed,
        "recommendation": "rollback" if regressed else ("expand" if observation_complete else "wait"),
    }


def expand_rollout_stage(
    db: Session,
    stage: OptimizationRolloutStage,
    *,
    user: dict | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Complete stage after observation window if metrics are healthy."""
    evaluation = evaluate_rollout_stage(db, stage)
    if not force and evaluation["metrics_regressed"]:
        raise ValueError("Metrics regressed — rollback recommended before expand")
    if not force and not evaluation["observation_complete"]:
        raise ValueError(
            f"Observation window not complete ({evaluation['days_elapsed']}/"
            f"{stage.observation_window_days} days)",
        )

    executed = 0
    for action in _actions_for_stage(db, stage):
        if action.workflow_status in {"approved", "proposed"}:
            update_optimization_action(
                db, action,
                workflow_status="executed",
                user=user,
                note="Marked executed after rollout observation",
            )
            executed += 1

    stage.resources_executed = executed
    stage.status = "completed"
    stage.completed_at = utc_now()
    db.commit()
    return {"status": "completed", "resources_executed": executed, "evaluation": evaluation}


def rollback_rollout_stage(
    db: Session,
    stage: OptimizationRolloutStage,
    *,
    reason: str,
    user: dict | None = None,
) -> dict[str, Any]:
    """Rollback stage and reject linked actions."""
    evaluate_rollout_stage(db, stage)
    rolled_back = 0
    for action in _actions_for_stage(db, stage):
        update_optimization_action(
            db, action,
            workflow_status="rejected",
            user=user,
            note=f"Rollout rollback: {reason}",
        )
        rolled_back += 1

    stage.rollback_triggered = True
    stage.rollback_reason = reason
    stage.resources_rolled_back = rolled_back
    stage.status = "rolled_back"
    stage.completed_at = utc_now()
    db.commit()
    return {"status": "rolled_back", "resources_rolled_back": rolled_back}

"""Subscription-level optimization trends and rollout health summary."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models import OptimizationAction, OptimizationRolloutStage, OptimizationScoring


def _today() -> str:
    return date.today().isoformat()


def get_optimization_trends(db: Session, subscription_id: str) -> dict[str, Any]:
    sub = subscription_id.strip().lower()
    eval_date = _today()

    scoring_rows = (
        db.query(OptimizationScoring)
        .filter(
            OptimizationScoring.subscription_id == sub,
            OptimizationScoring.evaluation_date == eval_date,
        )
        .all()
    )
    if not scoring_rows:
        scoring_rows = (
            db.query(OptimizationScoring)
            .filter(OptimizationScoring.subscription_id == sub)
            .order_by(OptimizationScoring.evaluation_date.desc())
            .limit(500)
            .all()
        )

    tier_counts: dict[str, int] = defaultdict(int)
    total_savings = 0.0
    score_values: list[float] = []
    resolved_eval_date = scoring_rows[0].evaluation_date if scoring_rows else None
    for row in scoring_rows:
        tier_counts[row.recommendation_tier or "unknown"] += 1
        total_savings += row.cost_savings_monthly or 0.0
        if row.overall_recommendation_score is not None:
            score_values.append(float(row.overall_recommendation_score))

    average_score = round(sum(score_values) / len(score_values), 1) if score_values else None

    stages = (
        db.query(OptimizationRolloutStage)
        .filter(OptimizationRolloutStage.subscription_id == sub)
        .all()
    )
    stage_status: dict[str, int] = defaultdict(int)
    in_observation = 0
    for stage in stages:
        stage_status[stage.status or "proposed"] += 1
        if stage.status == "in_progress":
            in_observation += 1

    actions = db.query(OptimizationAction).filter(OptimizationAction.subscription_id == sub).all()
    action_status: dict[str, int] = defaultdict(int)
    for action in actions:
        action_status[action.workflow_status or "proposed"] += 1

    completed_stages = stage_status.get("completed", 0)
    rolled_back_stages = stage_status.get("rolled_back", 0)
    finished = completed_stages + rolled_back_stages
    success_rate = round(completed_stages / finished * 100, 1) if finished else None

    executed_actions = sum(1 for a in actions if (a.workflow_status or "") == "executed")

    resources_scored = len(scoring_rows)
    return {
        "subscription_id": sub,
        "evaluation_date": resolved_eval_date,
        "resources_scored": resources_scored,
        "tier_counts": dict(tier_counts),
        "total_estimated_monthly_savings": round(total_savings, 2),
        "scoring": {
            "total": resources_scored,
            "average_score": average_score,
        },
        "rollout": {
            "stages_by_status": dict(stage_status),
            "in_observation": in_observation,
            "completed": completed_stages,
            "rolled_back": rolled_back_stages,
            "success_rate_pct": success_rate,
        },
        "actions_by_status": dict(action_status),
        "executed_actions": executed_actions,
        "mode": "advisory",
    }

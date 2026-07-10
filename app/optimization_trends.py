"""Subscription-level optimization trends and rollout health summary."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models import OptimizationAction, OptimizationRolloutStage, OptimizationScoring
from app.optimization_actions import _distinct_savings_for_query
from app.optimization_savings import distinct_scoreboard_savings
from app.savings_aggregation import aggregate_subscription_savings


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
    score_values: list[float] = []
    resolved_eval_date = scoring_rows[0].evaluation_date if scoring_rows else None
    for row in scoring_rows:
        tier_counts[row.recommendation_tier or "unknown"] += 1
        if row.overall_recommendation_score is not None:
            score_values.append(float(row.overall_recommendation_score))

    average_score = round(sum(score_values) / len(score_values), 1) if score_values else None
    scoreboard_savings = distinct_scoreboard_savings(scoring_rows)

    actions_q = db.query(OptimizationAction).filter(OptimizationAction.subscription_id == sub)
    action_savings = _distinct_savings_for_query(actions_q)
    unified = aggregate_subscription_savings(db, sub)
    unified_savings = float(unified.get("unified_estimated_monthly_savings") or 0.0)
    canonical_savings = (
        unified_savings
        if unified_savings > 0
        else (action_savings if action_savings > 0 else scoreboard_savings)
    )

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
        "total_estimated_monthly_savings": canonical_savings,
        "unified_estimated_monthly_savings": unified_savings,
        "distinct_estimated_monthly_savings": action_savings,
        "action_pipeline_savings": action_savings,
        "distinct_scoreboard_savings": scoreboard_savings,
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

"""Trend analysis from utilization history and cost snapshots."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import CostByResourceSnapshot, ResourceSnapshot
from app.utilization_history import utilization_trend


def _norm_rid(value: str | None) -> str:
    return (value or "").strip().lower()


def analyze_resource_trends(
    db: Session,
    subscription_id: str,
    resource_id: str,
) -> dict[str, Any]:
    """Return cost and utilization trend signals for scoring."""
    sub = subscription_id.strip().lower()
    rid = _norm_rid(resource_id)

    cpu_trend = utilization_trend(db, rid, "avg_cpu_pct", subscription_id=sub, min_points=2)
    mem_trend = utilization_trend(db, rid, "avg_memory_pct", subscription_id=sub, min_points=2)

    snap = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.resource_id == rid,
        )
        .first()
    )
    monthly_cost = float(snap.monthly_cost_usd or 0) if snap else 0.0

    cost_rows = (
        db.query(CostByResourceSnapshot)
        .filter(
            CostByResourceSnapshot.subscription_id == sub,
            CostByResourceSnapshot.resource_id == rid,
        )
        .order_by(CostByResourceSnapshot.month.desc())
        .limit(3)
        .all()
    )
    cost_trajectory = "stable"
    cost_vs_prev_pct = None
    if len(cost_rows) >= 2:
        current = float(cost_rows[0].cost_usd or 0)
        previous = float(cost_rows[1].cost_usd or 0)
        if previous > 0:
            cost_vs_prev_pct = round((current - previous) / previous * 100, 2)
            if cost_vs_prev_pct > 10:
                cost_trajectory = "increasing"
            elif cost_vs_prev_pct < -10:
                cost_trajectory = "decreasing"

    insufficient = bool(cpu_trend.get("insufficient_history"))
    volatility = float(cpu_trend.get("volatility") or 0)

    return {
        "cpu_trend": cpu_trend,
        "memory_trend": mem_trend,
        "monthly_cost_usd": monthly_cost,
        "cost_trajectory": cost_trajectory,
        "cost_vs_prev_month_pct": cost_vs_prev_pct,
        "insufficient_history": insufficient,
        "utilization_volatility": volatility,
        "confidence_penalty": 30.0 if insufficient else 0.0,
    }

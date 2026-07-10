"""Analysis rules — owned by analytics-mlworkspace IT service."""
from __future__ import annotations

from __future__ import annotations
from typing import Any
from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
def _cost_finding(
    engine,
    rule,
    subscription_id: str,
    resource: dict,
    monthly: float,
    detail_suffix: str,
    recommendation: str,
    savings_factor: float,
    waste_score: int,
    priority: str,
) -> ExtendedFinding:
    name = resource.get("name") or ""
    return engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=resource,
        detail=f"'{name}' has MTD spend of ${monthly:,.2f}. {detail_suffix}",
        recommendation=recommendation,
        savings=savings_from_factor(monthly, savings_factor),
        waste_score=waste_score,
        confidence=68,
        priority=priority,
        impact="Analytics compute cost optimization",
        evidence={"monthly_cost_usd": monthly},
    )


def analyze_ml_workspaces(
    engine, subscription_id: str, workspaces: list[dict], cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("ML_WORKSPACE_COMPUTE_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for ws in workspaces:
        monthly = resource_cost(cost_by_resource, ws.get("id", ""))
        if monthly < 100:
            continue
        out.append(_cost_finding(
            engine, rule, subscription_id, ws, monthly,
            "Review idle compute clusters and managed online endpoints.",
            "Delete idle compute clusters, use low-priority VMs for training, and scale managed online endpoints to zero when unused.",
            0.25, 54, "P2",
        ))
    return out

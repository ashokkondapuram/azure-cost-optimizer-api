"""Analysis rules — owned by analytics-adx IT service."""
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


def analyze_adx(
    engine, subscription_id: str, clusters: list[dict], cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("ADX_INGESTION_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for cluster in clusters:
        monthly = resource_cost(cost_by_resource, cluster.get("id", ""))
        if monthly < 100:
            continue
        out.append(_cost_finding(
            engine, rule, subscription_id, cluster, monthly,
            "Review ingestion batching and retention policies.",
            "Review ingestion batching, retention policies, cache policy, and scale down dev/test clusters when idle.",
            0.20, 55, "P2",
        ))
    return out

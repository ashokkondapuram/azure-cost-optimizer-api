"""Analysis rules — owned by integration-datafactory IT service."""
from __future__ import annotations

from __future__ import annotations
from typing import Any
from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import fact_value


def analyze_data_factories(
    engine,
    subscription_id: str,
    factories: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("DATA_FACTORY_IR_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for factory in factories:
        name = factory.get("name") or ""
        monthly = resource_cost(cost_by_resource, factory.get("id", ""))
        if monthly < 75:
            continue
        tags = factory.get("tags") or {}
        env = str(tags.get("environment") or tags.get("env") or "").lower()
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=factory,
            detail=f"Data Factory '{name}' has MTD spend of ${monthly:,.2f}.",
            recommendation="Pause unused pipelines, right-size integration runtimes, and use Azure-hosted IR only when needed.",
            savings=savings_from_factor(monthly, 0.20),
            waste_score=52,
            confidence=65,
            priority="P2",
            impact="Optimize pipeline and IR runtime cost",
            evidence={"monthly_cost_usd": monthly, "environment": env},
        ))
    return out

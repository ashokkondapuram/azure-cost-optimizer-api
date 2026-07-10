"""Analysis rules — owned by integration-logicapp IT service."""
from __future__ import annotations

from __future__ import annotations
from typing import Any
from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import fact_value


def analyze_logic_apps(
    engine,
    subscription_id: str,
    workflows: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("LOGIC_APP_PLAN_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for wf in workflows:
        name = wf.get("name") or ""
        monthly = resource_cost(cost_by_resource, wf.get("id", ""))
        if monthly < 40:
            continue
        props = wf.get("properties") or {}
        state = (props.get("state") or "").lower()
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=wf,
            detail=f"Logic App '{name}' has MTD spend of ${monthly:,.2f} (state: {state or 'unknown'}).",
            recommendation="Trim run history retention, consolidate workflows, and use Consumption plan for intermittent workloads.",
            savings=savings_from_factor(monthly, 0.15),
            waste_score=45,
            confidence=62,
            priority="P3",
            impact="Reduce workflow storage and execution charges",
            evidence={"monthly_cost_usd": monthly, "state": state},
        ))
    return out

"""Azure Functions and serverless optimization rules."""

from __future__ import annotations

from app.cost_utils import resource_cost
from app.optimizer.standard_finding import Finding


def analyze_serverless(
    engine,
    subscription_id: str,
    function_apps: list[dict],
    cost_by_resource: dict[str, float] | None = None,
) -> list[Finding]:
    out: list[Finding] = []
    plan_rule = engine.rules.get("FUNCTIONS_PLAN_OPTIMIZATION")
    if not plan_rule or not plan_rule.enabled:
        return out

    for app in function_apps:
        props = app.get("properties") or {}
        plan = str(props.get("serverFarmId") or props.get("hostingEnvironment") or "")
        monthly = resource_cost(cost_by_resource or {}, app.get("id", ""))
        if monthly < getattr(plan_rule, "min_monthly_savings_usd", 1.0):
            continue
        if "consumption" in plan.lower() or "dynamic" in plan.lower():
            continue
        out.append(Finding(
            plan_rule,
            app,
            detail=f"Function app '{app.get('name')}' runs on a dedicated plan — review Consumption or Flex Consumption.",
            recommendation="Move intermittent workloads to Consumption/Flex to reduce idle plan cost.",
            savings=round(monthly * 0.35, 2),
            score=48,
            evidence={"plan": plan, "monthly_cost_usd": monthly},
            global_config=getattr(engine, "global_config", None),
        ))
    return out

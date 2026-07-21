"""Analysis rules — owned by integration-logicapp IT service."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.integration_logicapp.engine.optimization_rules import (
    evaluate_logicapp_low_runs,
    evaluate_logicapp_plan_cost,
)


def analyze_logic_apps(
    engine,
    subscription_id: str,
    workflows: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    plan_rule = engine.rules.get("LOGIC_APP_PLAN_EXTENDED")
    runs_rule = engine.rules.get("LOGIC_APP_LOW_RUNS_EXTENDED")
    for wf in workflows:
        monthly = resource_cost(cost_by_resource, wf.get("id", ""))
        append_stub_draft(out, engine, subscription_id, wf, plan_rule, evaluate_logicapp_plan_cost(wf, monthly, plan_rule))
        append_stub_draft(out, engine, subscription_id, wf, runs_rule, evaluate_logicapp_low_runs(wf, monthly, runs_rule))
    return out

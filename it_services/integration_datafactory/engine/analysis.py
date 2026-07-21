"""Analysis rules — owned by integration-datafactory IT service."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.integration_datafactory.engine.optimization_rules import (
    evaluate_datafactory_idle_pipelines,
    evaluate_datafactory_ir_cost,
)


def analyze_data_factories(
    engine,
    subscription_id: str,
    factories: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    ir_rule = engine.rules.get("DATA_FACTORY_IR_EXTENDED")
    idle_rule = engine.rules.get("DATA_FACTORY_IDLE_PIPELINES_EXTENDED")
    for factory in factories:
        monthly = resource_cost(cost_by_resource, factory.get("id", ""))
        append_stub_draft(out, engine, subscription_id, factory, ir_rule, evaluate_datafactory_ir_cost(factory, monthly, ir_rule))
        append_stub_draft(out, engine, subscription_id, factory, idle_rule, evaluate_datafactory_idle_pipelines(factory, monthly, idle_rule))
    return out

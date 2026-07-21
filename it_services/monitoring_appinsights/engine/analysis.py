"""Analysis rules — owned by monitoring-appinsights IT service."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.monitoring_appinsights.engine.optimization_rules import (
    evaluate_appinsights_low_traffic,
    evaluate_appinsights_sampling,
)


def analyze_app_insights(
    engine,
    subscription_id: str,
    components: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    sampling_rule = engine.rules.get("APP_INSIGHTS_SAMPLING_EXTENDED")
    traffic_rule = engine.rules.get("APP_INSIGHTS_LOW_TRAFFIC_EXTENDED")
    for comp in components:
        monthly = resource_cost(cost_by_resource, comp.get("id", ""))
        append_stub_draft(out, engine, subscription_id, comp, sampling_rule, evaluate_appinsights_sampling(comp, monthly, sampling_rule))
        append_stub_draft(out, engine, subscription_id, comp, traffic_rule, evaluate_appinsights_low_traffic(comp, monthly, traffic_rule))
    return out

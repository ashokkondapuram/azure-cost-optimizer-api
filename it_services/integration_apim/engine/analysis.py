"""Analysis rules — owned by integration-apim IT service."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.integration_apim.engine.optimization_rules import (
    evaluate_apim_low_capacity,
    evaluate_apim_sku_review,
)


def analyze_apim(
    engine,
    subscription_id: str,
    services: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    sku_rule = engine.rules.get("APIM_SKU_EXTENDED")
    traffic_rule = engine.rules.get("APIM_LOW_TRAFFIC_EXTENDED")
    for svc in services:
        monthly = resource_cost(cost_by_resource, svc.get("id", ""))
        append_stub_draft(out, engine, subscription_id, svc, sku_rule, evaluate_apim_sku_review(svc, monthly, sku_rule))
        append_stub_draft(out, engine, subscription_id, svc, traffic_rule, evaluate_apim_low_capacity(svc, monthly, traffic_rule))
    return out

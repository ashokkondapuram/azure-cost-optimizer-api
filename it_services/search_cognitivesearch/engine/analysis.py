"""Search resource optimization analysis rules."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.search_cognitivesearch.engine.optimization_rules import (
    evaluate_search_over_replicas,
    evaluate_search_sku_review,
)


def analyze_cognitive_search(
    engine,
    subscription_id: str,
    services: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    sku_rule = engine.rules.get("COGNITIVE_SEARCH_SKU_EXTENDED")
    replica_rule = engine.rules.get("COGNITIVE_SEARCH_REPLICA_EXTENDED")
    for svc in services:
        monthly = resource_cost(cost_by_resource, svc.get("id", ""))
        append_stub_draft(out, engine, subscription_id, svc, sku_rule, evaluate_search_sku_review(svc, monthly, sku_rule))
        append_stub_draft(out, engine, subscription_id, svc, replica_rule, evaluate_search_over_replicas(svc, monthly, replica_rule))
    return out

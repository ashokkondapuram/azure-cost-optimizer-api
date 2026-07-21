"""Analysis rules — owned by messaging-servicebus IT service."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.messaging_servicebus.engine.optimization_rules import (
    evaluate_servicebus_idle_namespace,
    evaluate_servicebus_tier_review,
)


def analyze_service_bus(
    engine,
    subscription_id: str,
    namespaces: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    tier_rule = engine.rules.get("SERVICE_BUS_TIER_EXTENDED")
    idle_rule = engine.rules.get("SERVICE_BUS_IDLE_NAMESPACE_EXTENDED")
    for ns in namespaces:
        monthly = resource_cost(cost_by_resource, ns.get("id", ""))
        append_stub_draft(out, engine, subscription_id, ns, tier_rule, evaluate_servicebus_tier_review(ns, monthly, tier_rule))
        append_stub_draft(out, engine, subscription_id, ns, idle_rule, evaluate_servicebus_idle_namespace(ns, monthly, idle_rule))
    return out

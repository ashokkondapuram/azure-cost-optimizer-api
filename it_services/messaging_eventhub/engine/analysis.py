"""Analysis rules — owned by messaging-eventhub IT service."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.messaging_eventhub.engine.optimization_rules import (
    evaluate_eventhub_low_messages,
    evaluate_eventhub_tier_review,
)


def analyze_event_hubs(
    engine,
    subscription_id: str,
    namespaces: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    tier_rule = engine.rules.get("EVENT_HUBS_TIER_EXTENDED")
    low_rule = engine.rules.get("EVENT_HUBS_LOW_THROUGHPUT_EXTENDED")
    for ns in namespaces:
        monthly = resource_cost(cost_by_resource, ns.get("id", ""))
        append_stub_draft(out, engine, subscription_id, ns, tier_rule, evaluate_eventhub_tier_review(ns, monthly, tier_rule))
        append_stub_draft(out, engine, subscription_id, ns, low_rule, evaluate_eventhub_low_messages(ns, monthly, low_rule))
    return out

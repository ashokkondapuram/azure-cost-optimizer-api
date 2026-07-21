"""Analysis rules — owned by network-frontdoor IT service."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.network_frontdoor.engine.optimization_rules import (
    evaluate_frontdoor_cost_review,
    evaluate_frontdoor_low_traffic,
)


def analyze_front_doors(
    engine,
    subscription_id: str,
    profiles: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    review_rule = engine.rules.get("NETWORK_FRONT_DOOR_COST_EXTENDED")
    idle_rule = engine.rules.get("NETWORK_FRONT_DOOR_IDLE_EXTENDED")
    for profile in profiles:
        monthly = resource_cost(cost_by_resource, profile.get("id", ""))
        append_stub_draft(out, engine, subscription_id, profile, review_rule, evaluate_frontdoor_cost_review(profile, monthly, review_rule))
        append_stub_draft(out, engine, subscription_id, profile, idle_rule, evaluate_frontdoor_low_traffic(profile, monthly, idle_rule))
    return out

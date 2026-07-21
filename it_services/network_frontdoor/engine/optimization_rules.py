"""Front Door optimization decision rules — egress cost and request volume."""

from __future__ import annotations

from typing import Any

from app.resource_utilization import fact_value, make_check, utilization_gate
from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_savings, metric_finding_draft

_CANONICAL = "network/frontdoor"


def _thresholds(rule: Any) -> dict[str, float]:
    return threshold_values(
        rule,
        _CANONICAL,
        min_cost="min_monthly_cost_usd",
        requests_low="request_count_low",
        savings_factor="savings_factor",
        min_savings="min_monthly_savings_usd",
    )


def evaluate_frontdoor_cost_review(
    profile: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    name = profile.get("name") or ""
    return metric_finding_draft(
        rule_id="NETWORK_FRONT_DOOR_COST_EXTENDED",
        resource=profile,
        monthly=monthly_cost,
        detail=f"Front Door profile '{name}' has MTD spend of ${monthly_cost:,.2f}.",
        recommendation="Review routing rules, WAF tier, and consolidate entry points across environments.",
        savings=cost_savings(monthly_cost, th["savings_factor"], min_savings=th["min_savings"]),
        waste_score=42,
        priority="P2",
        impact="Validate Front Door profile necessity and tier",
        determination="cost_review",
        summary="Front Door profile has recurring cost above threshold.",
        checks=[make_check("Monthly cost", monthly_cost, f">= ${th['min_cost']:.0f}", passed=True)],
    )


def evaluate_frontdoor_low_traffic(
    profile: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    if not utilization_gate(profile, "request_count", allow_inventory_only=False):
        return None
    requests = fact_value(profile, "request_count")
    if requests is not None and requests >= th["requests_low"]:
        return None
    name = profile.get("name") or ""
    return metric_finding_draft(
        rule_id="NETWORK_FRONT_DOOR_IDLE_EXTENDED",
        resource=profile,
        monthly=monthly_cost,
        detail=(
            f"Front Door profile '{name}' has low request volume "
            f"({requests if requests is not None else 'n/a'} requests)."
        ),
        recommendation="Consolidate profiles or migrate low-traffic endpoints to a shared CDN entry point.",
        savings=cost_savings(monthly_cost, th["savings_factor"], min_savings=th["min_savings"]),
        waste_score=40,
        priority="P3",
        impact="Reduce Front Door fixed and egress cost",
        determination="low_traffic",
        summary="Front Door request volume is below optimization threshold.",
        checks=[make_check("Request count", requests, f"< {th['requests_low']:.0f}", passed=True)],
        extra={"request_count": requests},
        required_keys=("request_count",),
    )

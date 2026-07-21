"""Event Hubs optimization decision rules — tier alignment and throughput."""

from __future__ import annotations

from typing import Any

from app.azure_retail_pricing import estimate_service_tier_savings
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import fact_value, make_check, utilization_gate
from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_savings, metric_finding_draft

_CANONICAL = "messaging/eventhub"


def _thresholds(rule: Any) -> dict[str, float]:
    return threshold_values(
        rule,
        _CANONICAL,
        min_cost="min_monthly_cost_usd",
        incoming_low="incoming_messages_low",
        savings_factor="savings_factor",
        min_savings="min_monthly_savings_usd",
    )


def evaluate_eventhub_tier_review(
    namespace: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    if not utilization_gate(namespace, "incoming_messages", "outgoing_messages", allow_inventory_only=False):
        return None
    incoming = fact_value(namespace, "incoming_messages")
    if incoming is not None and incoming >= th["incoming_low"]:
        return None
    sku = namespace.get("sku") or {}
    tier = (sku.get("tier") or sku.get("name") or "").lower()
    name = namespace.get("name") or ""
    pricing = estimate_service_tier_savings(
        namespace.get("location") or "",
        "Event Hubs",
        tier or "Standard",
        "Basic",
        cache_prefix="eh",
        actual_monthly_cost=monthly_cost if monthly_cost > 0 else None,
    )
    savings = savings_from_retail_or_none(pricing)
    if savings is None:
        savings = cost_savings(monthly_cost, th["savings_factor"], min_savings=th["min_savings"])
    return metric_finding_draft(
        rule_id="EVENT_HUBS_TIER_EXTENDED",
        resource=namespace,
        monthly=monthly_cost,
        detail=(
            f"Event Hubs namespace '{name}' has low throughput for its tier "
            f"(MTD ${monthly_cost:,.2f}, tier: {tier or 'unknown'})."
        ),
        recommendation=(
            "Review TU/partition count, enable auto-inflate only if needed, "
            "and move dev/test traffic to Basic tiers."
        ),
        savings=savings,
        waste_score=50,
        priority="P2",
        impact="Align messaging capacity with actual throughput",
        determination="low_throughput",
        summary="Event Hubs throughput is below tier threshold.",
        checks=[make_check("Incoming messages", incoming, f"< {th['incoming_low']:.0f}", passed=True)],
        extra={"tier": tier, **pricing},
        required_keys=("incoming_messages",),
    )


def evaluate_eventhub_low_messages(
    namespace: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    incoming = fact_value(namespace, "incoming_messages")
    outgoing = fact_value(namespace, "outgoing_messages")
    total = (incoming or 0.0) + (outgoing or 0.0)
    if total >= th["incoming_low"]:
        return None
    name = namespace.get("name") or ""
    return metric_finding_draft(
        rule_id="EVENT_HUBS_LOW_THROUGHPUT_EXTENDED",
        resource=namespace,
        monthly=monthly_cost,
        detail=(
            f"Event Hubs namespace '{name}' processed {total:,.0f} messages "
            f"in the evaluation window."
        ),
        recommendation="Reduce throughput units or consolidate dev/test namespaces.",
        savings=cost_savings(monthly_cost, th["savings_factor"], min_savings=th["min_savings"]),
        waste_score=46,
        priority="P3",
        impact="Reduce fixed Event Hubs capacity cost",
        determination="minimal_message_volume",
        summary="Combined message volume is below optimization threshold.",
        checks=[make_check("Total messages", total, f"< {th['incoming_low']:.0f}", passed=True)],
        extra={"incoming_messages": incoming, "outgoing_messages": outgoing},
    )

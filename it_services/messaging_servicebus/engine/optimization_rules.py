"""Service Bus optimization decision rules — tier alignment and namespace utilization."""

from __future__ import annotations

from typing import Any

from app.azure_retail_pricing import estimate_service_tier_savings
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import fact_value, make_check, utilization_gate
from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_savings, metric_finding_draft

_CANONICAL = "messaging/servicebus"


def _thresholds(rule: Any) -> dict[str, float]:
    return threshold_values(
        rule,
        _CANONICAL,
        min_cost="min_monthly_cost_usd",
        requests_low="incoming_requests_low",
        messages_low="active_messages_low",
        premium_factor="premium_savings_factor",
        standard_factor="standard_savings_factor",
        min_savings="min_monthly_savings_usd",
    )


def evaluate_servicebus_tier_review(
    namespace: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    sku = namespace.get("sku") or {}
    tier = (sku.get("tier") or sku.get("name") or "").lower()
    is_premium = "premium" in tier
    if is_premium and not utilization_gate(namespace, "incoming_requests", allow_inventory_only=False):
        return None
    requests = fact_value(namespace, "incoming_requests")
    if is_premium and requests is not None and requests >= th["requests_low"]:
        return None
    name = namespace.get("name") or ""
    pricing: dict[str, Any] = {}
    savings = cost_savings(monthly_cost, th["premium_factor"] if is_premium else th["standard_factor"], min_savings=th["min_savings"])
    if is_premium:
        pricing = estimate_service_tier_savings(
            namespace.get("location") or "",
            "Service Bus",
            "Premium",
            "Standard",
            cache_prefix="sb",
            actual_monthly_cost=monthly_cost if monthly_cost > 0 else None,
        )
        retail = savings_from_retail_or_none(pricing)
        if retail is not None:
            savings = retail
    return metric_finding_draft(
        rule_id="SERVICE_BUS_TIER_EXTENDED",
        resource=namespace,
        monthly=monthly_cost,
        detail=(
            f"Service Bus namespace '{name}' has MTD spend of ${monthly_cost:,.2f} "
            f"(tier: {tier or 'unknown'})."
        ),
        recommendation=(
            "Use Standard for most workloads, reduce premium namespaces in non-prod, "
            "and delete idle queues or topics."
        ),
        savings=savings,
        waste_score=48 if is_premium else 40,
        priority="P2",
        impact="Reduce messaging fixed capacity cost",
        determination="tier_review",
        summary="Service Bus tier may exceed workload requirements.",
        checks=[make_check("Incoming requests", requests, f"< {th['requests_low']:.0f}", passed=requests is None or requests < th["requests_low"])],
        extra={"tier": tier, **pricing},
        required_keys=("incoming_requests",) if is_premium else (),
    )


def evaluate_servicebus_idle_namespace(
    namespace: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    if not utilization_gate(namespace, "active_messages", allow_inventory_only=False):
        return None
    active = fact_value(namespace, "active_messages")
    if active is not None and active >= th["messages_low"]:
        return None
    name = namespace.get("name") or ""
    return metric_finding_draft(
        rule_id="SERVICE_BUS_IDLE_NAMESPACE_EXTENDED",
        resource=namespace,
        monthly=monthly_cost,
        detail=(
            f"Service Bus namespace '{name}' has low active message volume "
            f"({active if active is not None else 'n/a'} messages)."
        ),
        recommendation="Delete unused queues/topics or downgrade Premium namespaces in non-production.",
        savings=cost_savings(monthly_cost, th["premium_factor"], min_savings=th["min_savings"]),
        waste_score=44,
        priority="P3",
        impact="Reduce idle messaging namespace cost",
        determination="idle_namespace",
        summary="Active message count is below optimization threshold.",
        checks=[make_check("Active messages", active, f"< {th['messages_low']:.0f}", passed=True)],
        extra={"active_messages": active},
        required_keys=("active_messages",),
    )

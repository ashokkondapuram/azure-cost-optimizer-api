"""Messaging resource optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.azure_retail_pricing import estimate_service_tier_savings
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import fact_value
from app.resource_utilization import utilization_gate


def analyze_event_hubs(
    engine,
    subscription_id: str,
    namespaces: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("EVENT_HUBS_TIER_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for ns in namespaces:
        name = ns.get("name") or ""
        sku = ns.get("sku") or {}
        tier = (sku.get("tier") or sku.get("name") or "").lower()
        monthly = resource_cost(cost_by_resource, ns.get("id", ""))
        if monthly < 60:
            continue
        if not utilization_gate(ns, "incoming_messages", "outgoing_messages", allow_inventory_only=False):
            continue
        incoming = fact_value(ns, "incoming_messages")
        if incoming is not None and incoming >= 10000:
            continue
        pricing = estimate_service_tier_savings(
            ns.get("location") or "",
            "Event Hubs",
            tier or "Standard",
            "Basic",
            cache_prefix="eh",
            actual_monthly_cost=monthly if monthly > 0 else None,
        )
        savings = savings_from_retail_or_none(pricing)
        if savings is None:
            savings = savings_from_factor(monthly, 0.25)
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=ns,
            detail=f"Event Hubs namespace '{name}' has low throughput for its tier (MTD ${monthly:,.2f}, tier: {tier or 'unknown'}).",
            recommendation="Review TU/partition count, enable auto-inflate only if needed, and move dev/test traffic to Basic tiers.",
            savings=savings,
            waste_score=50,
            confidence=confidence_with_monitor(66, ns, required_keys=("incoming_messages",)),
            priority="P2",
            impact="Align messaging capacity with actual throughput",
            evidence={"tier": tier, "monthly_cost_usd": monthly, **pricing},
        ))
    return out


def analyze_service_bus(
    engine,
    subscription_id: str,
    namespaces: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("SERVICE_BUS_TIER_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for ns in namespaces:
        name = ns.get("name") or ""
        sku = ns.get("sku") or {}
        tier = (sku.get("tier") or sku.get("name") or "").lower()
        monthly = resource_cost(cost_by_resource, ns.get("id", ""))
        if monthly < 50:
            continue
        is_premium = "premium" in tier
        if is_premium and not utilization_gate(ns, "incoming_messages", allow_inventory_only=False):
            continue
        incoming = fact_value(ns, "incoming_messages")
        if is_premium and incoming is not None and incoming >= 5000:
            continue
        pricing = {}
        savings = savings_from_factor(monthly, 0.25 if is_premium else 0.10)
        if is_premium:
            pricing = estimate_service_tier_savings(
                ns.get("location") or "",
                "Service Bus",
                "Premium",
                "Standard",
                cache_prefix="sb",
                actual_monthly_cost=monthly if monthly > 0 else None,
            )
            retail = savings_from_retail_or_none(pricing)
            if retail is not None:
                savings = retail
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=ns,
            detail=f"Service Bus namespace '{name}' has MTD spend of ${monthly:,.2f} (tier: {tier or 'unknown'}).",
            recommendation="Use Standard for most workloads, reduce premium namespaces in non-prod, and delete idle queues or topics.",
            savings=savings,
            waste_score=48 if is_premium else 40,
            confidence=confidence_with_monitor(64, ns, required_keys=("incoming_messages",) if is_premium else ()),
            priority="P2",
            impact="Reduce messaging fixed capacity cost",
            evidence={"tier": tier, "monthly_cost_usd": monthly, **pricing},
        ))
    return out

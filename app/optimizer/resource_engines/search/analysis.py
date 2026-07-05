"""Search resource optimization analysis rules."""
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


def analyze_cognitive_search(
    engine,
    subscription_id: str,
    services: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("COGNITIVE_SEARCH_SKU_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for svc in services:
        name = svc.get("name") or ""
        sku = svc.get("sku") or {}
        sku_name = sku.get("name") or ""
        monthly = resource_cost(cost_by_resource, svc.get("id", ""))
        if monthly < 80:
            continue
        if not utilization_gate(svc, "search_qps", allow_inventory_only=False):
            continue
        qps = fact_value(svc, "search_qps")
        if qps is not None and qps >= 10:
            continue
        tags = svc.get("tags") or {}
        env = str(tags.get("environment") or tags.get("env") or "").lower()
        pricing = estimate_service_tier_savings(
            svc.get("location") or "",
            "Search",
            sku_name or "standard",
            "basic",
            cache_prefix="search",
            actual_monthly_cost=monthly if monthly > 0 else None,
        )
        savings = savings_from_retail_or_none(pricing)
        if savings is None:
            savings = savings_from_factor(monthly, 0.25)
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=svc,
            detail=f"Search service '{name}' has low query volume for its SKU (MTD ${monthly:,.2f}, SKU: {sku_name}).",
            recommendation="Reduce replicas/partitions in non-prod, use basic tier for dev, and delete unused indexes.",
            savings=savings,
            waste_score=50,
            confidence=confidence_with_monitor(64, svc, required_keys=("search_qps",)),
            priority="P2",
            impact="Right-size search replicas and partitions",
            evidence={"sku": sku_name, "environment": env, "monthly_cost_usd": monthly, **pricing},
        ))
    return out

"""Redis Cache optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.azure_retail_pricing import estimate_redis_tier_savings
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import fact_value
from app.resource_utilization import is_low_memory
from app.resource_utilization import memory_pct
from app.resource_utilization import metrics_block_rightsize
from app.resource_utilization import monitor_evidence
from app.resource_utilization import utilization_gate

def analyze_redis(engine, subscription_id: str, caches: list[dict], cost_by_resource: dict[str, float]) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    health_rule = engine.rules.get("REDIS_HEALTH_EXTENDED")
    size_rule = engine.rules.get("REDIS_RIGHTSIZE_EXTENDED")
    for cache in caches:
        props = cache.get("properties") or {}
        state = (props.get("provisioningState") or "").lower()
        sku = cache.get("sku") or {}
        tier = (sku.get("family") or sku.get("name") or "").lower()
        capacity = int(sku.get("capacity") or 0)
        if health_rule and health_rule.enabled and state == "failed":
            out.append(engine._finding(
                rule=health_rule,
                subscription_id=subscription_id,
                resource=cache,
                detail=f"Redis cache '{cache.get('name')}' is in Failed provisioning state.",
                recommendation="Delete and recreate the cache, or escalate to Azure support.",
                savings=0,
                waste_score=92,
                confidence=97,
                priority="P1",
                impact="Availability incident and wasted spend on broken resource",
                evidence={"provisioningState": state},
            ))
        if size_rule and size_rule.enabled and "premium" in tier and capacity >= size_rule.redis_premium_min_capacity:
            if metrics_block_rightsize(cache):
                continue
            if not utilization_gate(cache, "avg_memory_pct", allow_inventory_only=False):
                continue
            low_mem = is_low_memory(cache, threshold=35.0)
            low_ops = fact_value(cache, "ops_per_sec")
            if low_ops is not None and low_ops >= 100:
                continue
            if low_mem is not True:
                continue
            monthly = resource_cost(cost_by_resource, cache.get("id", ""))
            pricing = estimate_redis_tier_savings(
                cache.get("location") or "",
                capacity,
                max(1, capacity // 2),
                tier="Premium",
                actual_monthly_cost=monthly if monthly > 0 else None,
            )
            savings = savings_from_retail_or_none(pricing)
            if savings is None and monthly > 0:
                from app.cost_utils import savings_from_factor
                savings = savings_from_factor(monthly, 0.35)
            detail = f"Redis '{cache.get('name')}' uses Premium capacity {capacity}."
            if low_mem is True:
                detail += f" Memory utilization is {memory_pct(cache):.1f}% in Azure Monitor."
            out.append(engine._finding(
                rule=size_rule,
                subscription_id=subscription_id,
                resource=cache,
                detail=detail,
                recommendation="Review memory pressure metrics and test Standard tier for non-production workloads.",
                savings=savings,
                waste_score=54,
                confidence=confidence_with_monitor(68, cache, required_keys=("avg_memory_pct",)),
                priority="P3",
                impact="Cache SKU right-sizing opportunity",
                evidence=monitor_evidence(cache, {"tier": tier, "capacity": capacity, **pricing}),
            ))
    return out


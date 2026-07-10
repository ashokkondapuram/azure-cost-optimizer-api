"""Analysis rules — owned by integration-apim IT service."""
from __future__ import annotations

from __future__ import annotations
from typing import Any
from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import fact_value


def analyze_apim(
    engine,
    subscription_id: str,
    services: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("APIM_SKU_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for svc in services:
        name = svc.get("name") or ""
        sku = svc.get("sku") or {}
        sku_name = (sku.get("name") or "").lower()
        capacity = int(sku.get("capacity") or 1)
        monthly = resource_cost(cost_by_resource, svc.get("id", ""))
        if monthly < 100 and sku_name not in {"developer", "consumption"}:
            continue
        tags = svc.get("tags") or {}
        env = str(tags.get("environment") or tags.get("env") or "").lower()
        is_dev_tier = sku_name == "developer"
        low_requests = fact_value(svc, "request_count")
        over_capacity = capacity > 1 and low_requests is not None and low_requests < 10000
        if not is_dev_tier and not over_capacity and monthly < 100:
            continue
        detail = f"API Management instance '{name}' has MTD spend of ${monthly:,.2f} (SKU: {sku_name}, capacity: {capacity})."
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=svc,
            detail=detail,
            recommendation="Validate tier and scale units; downgrade non-production gateways where possible.",
            savings=savings_from_factor(monthly, 0.35) if monthly > 0 else 0,
            waste_score=60,
            confidence=confidence_with_monitor(68, svc),
            priority="P2",
            impact="Right-size API gateway capacity",
            evidence={"sku": sku_name, "capacity": capacity, "environment": env, "monthly_cost_usd": monthly},
        ))
    return out

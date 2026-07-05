"""Cosmos DB optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.azure_retail_pricing import estimate_service_tier_savings
from app.cost_utils import resource_cost
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import fact_value
from app.resource_utilization import is_low_request_volume
from app.resource_utilization import make_check
from app.resource_utilization import monitor_facts_status
from app.resource_utilization import structured_evidence
from app.resource_utilization import utilization_gate


def analyze_cosmos(
    engine,
    subscription_id: str,
    cosmosdb: list[dict],
    cost_by_resource: dict[str, float] | None = None,
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules["COSMOS_AUTOSCALE_EXTENDED"]
    provisioned_rule = engine.rules.get("COSMOS_PROVISIONED_EXTENDED")
    for acct in cosmosdb:
        props = acct.get("properties") or {}
        capabilities = props.get("capabilities") or []
        is_serverless = any(c.get("name") == "EnableServerless" for c in capabilities)
        name = acct.get("name") or ""

        if provisioned_rule and provisioned_rule.enabled and not is_serverless:
            out.append(engine._finding(
                rule=provisioned_rule,
                subscription_id=subscription_id,
                resource=acct,
                detail=f"Cosmos DB account '{name}' does not have serverless capability enabled.",
                recommendation="Evaluate serverless or autoscale for variable or low-throughput workloads.",
                savings=0,
                waste_score=38,
                confidence=68,
                priority="P3",
                impact="Potential RU/s cost optimization for low-volume accounts",
                evidence={"capabilities": capabilities, "serverless_enabled": is_serverless},
            ))

        if not rule.enabled:
            continue
        if is_serverless:
            continue

        facts_status = monitor_facts_status(acct, "request_count", "total_ru")
        if facts_status in {"missing", "partial"}:
            continue
        if not utilization_gate(acct, "request_count", allow_inventory_only=False):
            continue

        low_ru = is_low_request_volume(acct, threshold=50000.0)
        if low_ru is not True:
            continue

        name = acct.get("name") or ""
        requests = fact_value(acct, "request_count")
        total_ru = fact_value(acct, "total_ru")
        monthly = resource_cost(cost_by_resource or {}, acct.get("id", ""))
        pricing = estimate_service_tier_savings(
            acct.get("location") or "",
            "Azure Cosmos DB",
            "provisioned",
            "serverless",
            cache_prefix="cosmos",
            actual_monthly_cost=monthly if monthly > 0 else None,
        )
        savings = savings_from_retail_or_none(pricing) or 0.0
        detail = f"Cosmos DB account '{name}' is not serverless-enabled and may be over-provisioned."
        detail += " Request volume is low in Azure Monitor."

        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=acct,
            detail=detail,
            recommendation="Evaluate autoscale or serverless based on request volume variance and RU utilization.",
            savings=savings,
            waste_score=50,
            confidence=confidence_with_monitor(64, acct, boost=16),
            priority="P3",
            impact="Potential RU/s spend optimization",
            evidence=structured_evidence(
                acct,
                determination="autoscale_candidate",
                summary="Non-serverless Cosmos account shows low request and RU volume in Azure Monitor.",
                checks=[
                    make_check("Request count (7d)", requests, "< 50,000", passed=True),
                    make_check("Total RU (7d)", total_ru, "< 50,000", passed=total_ru is not None and total_ru < 50000),
                ],
                extra={"capabilities": capabilities, **pricing},
            ),
        ))
    return out

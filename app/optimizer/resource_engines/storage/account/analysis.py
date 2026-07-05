"""Storage Accounts optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.azure_retail_pricing import estimate_service_tier_savings
from app.cost_utils import resource_cost
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import fact_value
from app.resource_utilization import is_low_request_volume
from app.resource_utilization import is_low_storage_utilization
from app.resource_utilization import make_check
from app.resource_utilization import monitor_facts_status
from app.resource_utilization import structured_evidence


def analyze_storage(engine, subscription_id: str, storage: list[dict], cost_by_resource: dict[str, float] | None = None) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    lifecycle_rule = engine.rules["STORAGE_LIFECYCLE_EXTENDED"]
    redundancy_rule = engine.rules.get("STORAGE_REDUNDANCY_EXTENDED")
    for acct in storage:
        props = acct.get("properties") or {}
        tier = props.get("accessTier") or "Unknown"
        sku = acct.get("sku") or {}
        sku_name = (sku.get("name") or "").upper()
        name = acct.get("name") or ""
        tags = acct.get("tags") or {}
        env = str(tags.get("environment") or tags.get("env") or "").lower()

        if engine.rules.get("STORAGE_HOT_UNUSED_EXTENDED") and engine.rules["STORAGE_HOT_UNUSED_EXTENDED"].enabled:
            hot_rule = engine.rules["STORAGE_HOT_UNUSED_EXTENDED"]
            if tier == "Hot":
                out.append(engine._finding(
                    rule=hot_rule,
                    subscription_id=subscription_id,
                    resource=acct,
                    detail=f"Storage account '{name}' is on Hot tier — verify data is actively accessed.",
                    recommendation=f"Add lifecycle policy to move blobs to Cool after {lifecycle_rule.storage_cool_after_days} days.",
                    savings=0.0,
                    waste_score=35,
                    confidence=65,
                    priority="P3",
                    impact="Tiering can reduce storage cost for infrequently accessed data",
                    evidence={"access_tier": tier, "sku": sku_name, "environment": env},
                ))

        lrs_rule = engine.rules.get("STORAGE_LRS_CRITICAL_EXTENDED")
        if lrs_rule and lrs_rule.enabled and sku_name in {"STANDARD_LRS", "STANDARD_ZRS"}:
            if env in lrs_rule.prod_tag_values:
                out.append(engine._finding(
                    rule=lrs_rule,
                    subscription_id=subscription_id,
                    resource=acct,
                    detail=f"Storage account '{name}' uses locally redundant SKU {sku_name} in a production environment.",
                    recommendation="Validate resilience requirements — consider GRS or GZRS for geo-disaster recovery.",
                    savings=0,
                    waste_score=15,
                    confidence=60,
                    priority="P3",
                    impact="Resilience review — LRS lacks geo-redundancy",
                    evidence={"sku": sku_name, "environment": env},
                ))

        if lifecycle_rule.enabled:
            facts_status = monitor_facts_status(acct, "transaction_count")
            low_tx = is_low_request_volume(acct, threshold=5000.0)
            low_capacity = is_low_storage_utilization(acct)
            if facts_status in {"missing", "partial", "no_monitor"}:
                continue
            if low_tx is not True and low_capacity is not True:
                continue

            detail = f"Storage account '{name}' should be reviewed for Hot/Cool/Archive lifecycle automation."
            if low_tx is True:
                detail += " Transaction volume is low relative to stored capacity in Azure Monitor."

            out.append(engine._finding(
                rule=lifecycle_rule,
                subscription_id=subscription_id,
                resource=acct,
                detail=detail,
                recommendation=f"Add lifecycle rules to move cold data to Cool after {lifecycle_rule.storage_cool_after_days} days and Archive after {lifecycle_rule.storage_archive_after_days} days.",
                savings=0.0,
                waste_score=42 if low_tx is True else 32,
                confidence=confidence_with_monitor(62, acct, boost=14 if low_tx is True else 0),
                priority="P3",
                impact="Can reduce blob storage cost for cold data",
                evidence=structured_evidence(
                    acct,
                    determination="lifecycle_candidate",
                    summary="Storage account is a candidate for lifecycle tiering based on access patterns.",
                    checks=[
                        make_check(
                            "Transaction count (7d)",
                            fact_value(acct, "transaction_count"),
                            "< 5,000",
                            passed=low_tx is True,
                        ),
                        make_check(
                            "Used capacity",
                            fact_value(acct, "used_capacity_bytes"),
                            "Review cold data",
                            passed=low_capacity is True or facts_status == "no_monitor",
                        ),
                    ],
                    extra={"access_tier": tier, "sku": sku_name},
                ),
            ))

        if redundancy_rule and redundancy_rule.enabled and sku_name in {"STANDARD_GRS", "STANDARD_GZRS", "STANDARD_RAGRS", "STANDARD_RAGZRS"}:
            tags = acct.get("tags") or {}
            env = str(tags.get("environment") or tags.get("env") or "").lower()
            if env in redundancy_rule.nonprod_tag_values or not env:
                monthly = resource_cost(cost_by_resource or {}, acct.get("id", ""))
                pricing = estimate_service_tier_savings(
                    acct.get("location") or "",
                    "Storage",
                    "GRS",
                    "LRS",
                    cache_prefix="storage",
                    actual_monthly_cost=monthly if monthly > 0 else None,
                )
                savings = savings_from_retail_or_none(pricing) or 0.0
                out.append(engine._finding(
                    rule=redundancy_rule,
                    subscription_id=subscription_id,
                    resource=acct,
                    detail=f"Storage account '{name}' uses geo-redundant SKU {sku_name}.",
                    recommendation="Switch non-critical workloads to LRS or ZRS unless geo-failover is required.",
                    savings=savings,
                    waste_score=44,
                    confidence=70,
                    priority="P3",
                    impact="Geo-redundant SKUs roughly double storage cost vs LRS",
                    evidence={"sku": sku_name, "environment": env, **pricing},
                ))
    return out

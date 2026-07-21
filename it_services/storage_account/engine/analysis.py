"""Storage Accounts optimization analysis rules."""
from __future__ import annotations

from typing import Any

from it_services.storage_account.engine.optimization_rules import (
    evaluate_storage_cool_tier_candidate,
    evaluate_storage_egress_high,
)
from app.optimizer.core.finding import ExtendedFinding
from app.azure_retail_pricing import estimate_service_tier_savings
from app.cost_utils import resource_cost
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import fact_value
from app.resource_utilization import is_low_request_volume
from app.resource_utilization import is_low_storage_utilization
from app.resource_utilization import monitor_facts_status
from app.resource_utilization import structured_evidence
from app.storage_account_catalog import optimization_thresholds
from app.service_display import (
    format_access_tier,
    format_replication_sku,
    format_storage_fact,
    format_storage_utilization_threshold,
    format_transaction_threshold,
    make_storage_check,
    storage_hot_tier_recommendation,
    storage_lifecycle_recommendation,
    storage_redundancy_downgrade_recommendation,
    storage_redundancy_upgrade_recommendation,
)


def _append_metrics_draft(out, engine, subscription_id, resource, rule, draft):
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=resource,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def analyze_storage(engine, subscription_id: str, storage: list[dict], cost_by_resource: dict[str, float] | None = None) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    lifecycle_rule = engine.rules["STORAGE_LIFECYCLE_EXTENDED"]
    redundancy_rule = engine.rules.get("STORAGE_REDUNDANCY_EXTENDED")
    defaults = optimization_thresholds()
    tx_low = float(defaults.get("transaction_low_count", 5000.0))
    util_low_pct = float(defaults.get("storage_utilization_low_pct", 25.0))
    cool_days = int(lifecycle_rule.storage_cool_after_days)
    archive_days = int(lifecycle_rule.storage_archive_after_days)

    for acct in storage:
        props = acct.get("properties") or {}
        tier = props.get("accessTier") or "Unknown"
        tier_label = format_access_tier(tier if tier != "Unknown" else None) if tier != "Unknown" else "—"
        sku = acct.get("sku") or {}
        sku_name = (sku.get("name") or "").upper()
        sku_label = format_replication_sku(sku_name) if sku_name else "—"
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
                    detail=f"Storage account '{name}' is on {tier_label} — verify data is actively accessed.",
                    recommendation=storage_hot_tier_recommendation(),
                    savings=0.0,
                    waste_score=35,
                    confidence=65,
                    priority="P3",
                    impact="Tiering can reduce storage cost for infrequently accessed data",
                    evidence={
                        "access_tier": tier,
                        "access_tier_display": tier_label,
                        "sku": sku_name,
                        "sku_display": sku_label,
                        "environment": env,
                    },
                ))

        lrs_rule = engine.rules.get("STORAGE_LRS_CRITICAL_EXTENDED")
        if lrs_rule and lrs_rule.enabled and sku_name in {"STANDARD_LRS", "STANDARD_ZRS"}:
            if env in lrs_rule.prod_tag_values:
                out.append(engine._finding(
                    rule=lrs_rule,
                    subscription_id=subscription_id,
                    resource=acct,
                    detail=(
                        f"Storage account '{name}' uses {sku_label} in a production environment."
                    ),
                    recommendation=storage_redundancy_upgrade_recommendation(),
                    savings=0,
                    waste_score=15,
                    confidence=60,
                    priority="P3",
                    impact="Resilience review — locally redundant storage lacks geo-failover",
                    evidence={
                        "sku": sku_name,
                        "sku_display": sku_label,
                        "environment": env,
                    },
                ))

        if lifecycle_rule.enabled:
            facts_status = monitor_facts_status(acct, "transaction_count")
            low_tx = is_low_request_volume(acct, threshold=tx_low)
            low_capacity = is_low_storage_utilization(acct, threshold_pct=util_low_pct)
            if facts_status in {"missing", "partial", "no_monitor"}:
                continue
            if low_tx is not True and low_capacity is not True:
                continue

            tx_value = fact_value(acct, "transaction_count")
            used_value = fact_value(acct, "used_capacity_bytes")
            detail = (
                f"Storage account '{name}' is a candidate for lifecycle tiering based on Azure Monitor activity."
            )
            if low_tx is True:
                detail += f" Transaction volume is {format_storage_fact('transaction_count', tx_value)}."
            if low_capacity is True:
                detail += f" Used capacity is {format_storage_fact('used_capacity_bytes', used_value)}."

            checks = []
            if low_tx is True or tx_value is not None:
                checks.append(make_storage_check(
                    "Monthly transactions",
                    "transaction_count",
                    tx_value,
                    format_transaction_threshold(tx_low),
                    passed=low_tx is True,
                ))
            if low_capacity is True or used_value is not None:
                checks.append(make_storage_check(
                    "Storage utilization",
                    "storage_pct",
                    fact_value(acct, "storage_pct"),
                    format_storage_utilization_threshold(util_low_pct),
                    passed=low_capacity is True,
                ))

            out.append(engine._finding(
                rule=lifecycle_rule,
                subscription_id=subscription_id,
                resource=acct,
                detail=detail,
                recommendation=storage_lifecycle_recommendation(cool_days=cool_days, archive_days=archive_days),
                savings=0.0,
                waste_score=42 if low_tx is True else 32,
                confidence=confidence_with_monitor(62, acct, boost=14 if low_tx is True else 0),
                priority="P3",
                impact="Can reduce blob storage cost for cold data",
                evidence=structured_evidence(
                    acct,
                    determination="lifecycle_candidate",
                    summary="Storage account is a candidate for lifecycle tiering based on access patterns.",
                    checks=checks,
                    extra={
                        "access_tier": tier,
                        "access_tier_display": tier_label,
                        "sku": sku_name,
                        "sku_display": sku_label,
                    },
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
                    detail=f"Storage account '{name}' uses {sku_label}.",
                    recommendation=storage_redundancy_downgrade_recommendation(),
                    savings=savings,
                    waste_score=44,
                    confidence=70,
                    priority="P3",
                    impact="Geo-redundant SKUs roughly double storage cost vs locally redundant storage",
                    evidence={
                        "sku": sku_name,
                        "sku_display": sku_label,
                        "environment": env,
                        **pricing,
                    },
                ))

        monthly = resource_cost(cost_by_resource or {}, acct.get("id", ""))
        egress_rule = engine.rules.get("STORAGE_EGRESS_HIGH_EXTENDED")
        cool_rule = engine.rules.get("STORAGE_COOL_TIER_CANDIDATE_EXTENDED")
        _append_metrics_draft(out, engine, subscription_id, acct, egress_rule, evaluate_storage_egress_high(acct, monthly, egress_rule))
        _append_metrics_draft(out, engine, subscription_id, acct, cool_rule, evaluate_storage_cool_tier_candidate(acct, monthly, cool_rule))
    return out

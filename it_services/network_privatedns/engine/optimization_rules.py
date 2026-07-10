"""Optimization rules — owned by network-privatedns IT service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.network_pricing import estimate_decommission_savings
from app.private_dns_catalog import optimization_thresholds, zone_monthly_usd
from app.resource_utilization import confidence_with_monitor, fact_value, make_check, monitor_facts_status, structured_evidence


@dataclass(frozen=True)
class NetworkFindingDraft:
    rule_id: str
    detail: str
    recommendation: str
    savings: float
    waste_score: int
    confidence: int
    priority: str
    impact: str
    evidence: dict[str, Any]


def _thresholds(rule: Any) -> dict[str, float]:
    defaults = optimization_thresholds()
    return {
        "max_default_records": float(
            getattr(rule, "private_dns_max_default_record_sets", defaults.get("max_default_record_sets", 2))
        ),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 1.0))),
    }


def _zone_savings(monthly_cost: float, min_savings: float) -> float:
    if monthly_cost and monthly_cost > 0:
        return estimate_decommission_savings(monthly_cost, min_savings=min_savings)
    baseline = zone_monthly_usd()
    return baseline if baseline >= min_savings else 0.0


def evaluate_private_dns_empty(
    zone: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    record_count = ctx.get("record_set_count")
    if record_count is None:
        return None
    try:
        if int(record_count) > th["max_default_records"]:
            return None
    except (TypeError, ValueError):
        return None
    name = zone.get("name") or ""
    savings = _zone_savings(monthly_cost, th["min_savings"])
    return NetworkFindingDraft(
        rule_id="PRIVATE_DNS_EMPTY_EXTENDED",
        detail=f"Private DNS zone '{name}' has no custom record sets.",
        recommendation="Delete empty private DNS zones or attach them to active private endpoints.",
        savings=savings,
        waste_score=40,
        confidence=75,
        priority="P3",
        impact="Clean up unused private DNS zone monthly charges",
        evidence=structured_evidence(
            zone,
            determination="empty_dns_zone",
            summary="Private DNS zone only contains default SOA/NS records.",
            checks=[make_check("Record set count", record_count, f"≤ {int(th['max_default_records'])}", passed=True)],
            extra={
                "record_set_count": record_count,
                "monthly_cost_usd": monthly_cost,
                "estimated_monthly_savings_usd": savings,
            },
        ),
    )


def evaluate_private_dns_unused_zone(
    zone: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    if monitor_facts_status(zone, "query_volume") != "available":
        return None
    queries = fact_value(zone, "query_volume")
    if queries is None or float(queries) > 0:
        return None
    name = zone.get("name") or ""
    savings = _zone_savings(monthly_cost, th["min_savings"])
    return NetworkFindingDraft(
        rule_id="PRIVATE_DNS_UNUSED_ZONE",
        detail=f"Private DNS zone '{name}' shows zero queries in Azure Monitor over the evaluation window.",
        recommendation="Delete unused DNS zones or merge records into a shared zone linked to active private endpoints.",
        savings=savings,
        waste_score=48,
        confidence=confidence_with_monitor(72, zone),
        priority="P2",
        impact="Remove unused private DNS zone and query charges",
        evidence=structured_evidence(
            zone,
            determination="zero_queries",
            summary="Private DNS zone has no query activity.",
            checks=[make_check("Query volume", queries, "0", passed=True)],
            extra={"monthly_cost_usd": monthly_cost, "estimated_monthly_savings_usd": savings},
        ),
    )

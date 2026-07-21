"""Cognitive Search optimization decision rules — SKU and replica alignment."""

from __future__ import annotations

from typing import Any

from app.azure_retail_pricing import estimate_service_tier_savings
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import fact_value, make_check, utilization_gate
from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_savings, metric_finding_draft

_CANONICAL = "search/cognitivesearch"


def _thresholds(rule: Any) -> dict[str, float]:
    return threshold_values(
        rule,
        _CANONICAL,
        min_cost="min_monthly_cost_usd",
        qps_low="search_qps_low",
        replica_high="replica_count_high",
        savings_factor="savings_factor",
        replica_factor="replica_savings_factor",
        min_savings="min_monthly_savings_usd",
    )


def evaluate_search_sku_review(
    service: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    if not utilization_gate(service, "search_qps", allow_inventory_only=False):
        return None
    qps = fact_value(service, "search_qps")
    if qps is not None and qps >= th["qps_low"]:
        return None
    sku = service.get("sku") or {}
    sku_name = sku.get("name") or ""
    name = service.get("name") or ""
    pricing = estimate_service_tier_savings(
        service.get("location") or "",
        "Search",
        sku_name or "standard",
        "basic",
        cache_prefix="search",
        actual_monthly_cost=monthly_cost if monthly_cost > 0 else None,
    )
    savings = savings_from_retail_or_none(pricing)
    if savings is None:
        savings = cost_savings(monthly_cost, th["savings_factor"], min_savings=th["min_savings"])
    return metric_finding_draft(
        rule_id="COGNITIVE_SEARCH_SKU_EXTENDED",
        resource=service,
        monthly=monthly_cost,
        detail=(
            f"Search service '{name}' has low query volume for its SKU "
            f"(MTD ${monthly_cost:,.2f}, SKU: {sku_name})."
        ),
        recommendation="Reduce replicas/partitions in non-prod, use basic tier for dev, and delete unused indexes.",
        savings=savings,
        waste_score=50,
        priority="P2",
        impact="Right-size search replicas and partitions",
        determination="low_query_volume",
        summary="Search query volume is below SKU threshold.",
        checks=[make_check("Search QPS", qps, f"< {th['qps_low']:.0f}", passed=True)],
        extra={"sku": sku_name, **pricing},
        required_keys=("search_qps",),
    )


def evaluate_search_over_replicas(
    service: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    props = service.get("properties") or {}
    replicas = int(props.get("replicaCount") or service.get("replicaCount") or 1)
    if replicas < th["replica_high"]:
        return None
    qps = fact_value(service, "search_qps")
    if qps is not None and qps >= th["qps_low"]:
        return None
    name = service.get("name") or ""
    return metric_finding_draft(
        rule_id="COGNITIVE_SEARCH_REPLICA_EXTENDED",
        resource=service,
        monthly=monthly_cost,
        detail=(
            f"Search service '{name}' has {replicas} replicas with low query volume."
        ),
        recommendation="Reduce replica count in non-production or low-traffic environments.",
        savings=cost_savings(monthly_cost, th["replica_factor"], min_savings=th["min_savings"]),
        waste_score=52,
        priority="P2",
        impact="Reduce search replica fixed cost",
        determination="excess_replicas",
        summary="Replica count exceeds workload requirements.",
        checks=[
            make_check("Replica count", replicas, f">= {th['replica_high']:.0f}", passed=True),
            make_check("Search QPS", qps, f"< {th['qps_low']:.0f}", passed=qps is None or qps < th["qps_low"]),
        ],
        extra={"replica_count": replicas, "search_qps": qps},
    )

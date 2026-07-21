"""API Management optimization decision rules — SKU capacity and request volume."""

from __future__ import annotations

from typing import Any

from app.resource_utilization import fact_value, make_check, utilization_gate
from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_savings, metric_finding_draft

_CANONICAL = "integration/apim"


def _thresholds(rule: Any) -> dict[str, float]:
    return threshold_values(
        rule,
        _CANONICAL,
        min_cost="min_monthly_cost_usd",
        request_low="request_count_low",
        capacity_low="capacity_pct_low",
        savings_factor="savings_factor",
        min_savings="min_monthly_savings_usd",
    )


def evaluate_apim_sku_review(
    service: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    sku = service.get("sku") or {}
    sku_name = (sku.get("name") or "").lower()
    capacity = int(sku.get("capacity") or 1)
    if monthly_cost < th["min_cost"] and sku_name not in {"developer", "consumption"}:
        return None
    requests = fact_value(service, "request_count")
    over_capacity = capacity > 1 and requests is not None and requests < th["request_low"]
    if not (sku_name == "developer" or over_capacity or monthly_cost >= th["min_cost"]):
        return None
    name = service.get("name") or ""
    return metric_finding_draft(
        rule_id="APIM_SKU_EXTENDED",
        resource=service,
        monthly=monthly_cost,
        detail=(
            f"API Management instance '{name}' has MTD spend of ${monthly_cost:,.2f} "
            f"(SKU: {sku_name}, capacity: {capacity})."
        ),
        recommendation="Validate tier and scale units; downgrade non-production gateways where possible.",
        savings=cost_savings(monthly_cost, th["savings_factor"], min_savings=th["min_savings"]),
        waste_score=60,
        priority="P2",
        impact="Right-size API gateway capacity",
        determination="sku_review",
        summary="API Management tier or capacity may exceed workload needs.",
        checks=[
            make_check("Request count", requests, f"< {th['request_low']:.0f}", passed=requests is not None and requests < th["request_low"]),
            make_check("Capacity units", capacity, "Review", passed=True),
        ],
        extra={"sku": sku_name, "capacity": capacity, "request_count": requests},
        required_keys=("request_count",),
    )


def evaluate_apim_low_capacity(
    service: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    if not utilization_gate(service, "capacity_pct", allow_inventory_only=False):
        return None
    capacity_pct = fact_value(service, "capacity_pct")
    if capacity_pct is None or float(capacity_pct) >= th["capacity_low"]:
        return None
    name = service.get("name") or ""
    return metric_finding_draft(
        rule_id="APIM_LOW_TRAFFIC_EXTENDED",
        resource=service,
        monthly=monthly_cost,
        detail=(
            f"API Management '{name}' shows low gateway capacity utilization "
            f"({float(capacity_pct):.1f}%, threshold {th['capacity_low']:.0f}%)."
        ),
        recommendation="Reduce scale units or move intermittent APIs to Consumption tier.",
        savings=cost_savings(monthly_cost, th["savings_factor"], min_savings=th["min_savings"]),
        waste_score=55,
        priority="P2",
        impact="Align API gateway scale with traffic",
        determination="low_capacity_utilization",
        summary="Gateway capacity utilization is below threshold.",
        checks=[make_check("Capacity %", capacity_pct, f"< {th['capacity_low']:.0f}%", passed=True)],
        extra={"capacity_pct": capacity_pct},
        required_keys=("capacity_pct",),
    )

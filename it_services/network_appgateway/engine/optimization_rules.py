"""Application Gateway optimization decision rules — CU saturation and right-sizing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.app_gateway_catalog import optimization_thresholds, parse_app_gateway_arm, tier_spec
from app.network_pricing import estimate_app_gateway_capacity_savings, estimate_decommission_savings
from app.resource_utilization import (
    confidence_with_monitor,
    fact_value,
    make_check,
    monitor_facts_status,
    structured_evidence,
)


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
        "cu_saturation_pct": float(getattr(rule, "app_gateway_cu_saturation_pct", defaults.get("cu_saturation_pct", 80.0))),
        "cu_downsize_pct": float(getattr(rule, "app_gateway_cu_downsize_pct", defaults.get("cu_downsize_pct", 30.0))),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 25.0))),
    }


def _cu_utilization_pct(gateway: dict[str, Any], ctx: dict[str, Any]) -> float | None:
    avg_cu = fact_value(gateway, "billed_capacity_units")
    if avg_cu is None:
        return None
    provisioned = float(ctx.get("provisioned_cu") or 0)
    if provisioned <= 0:
        return None
    return round(float(avg_cu) / provisioned * 100.0, 2)


def evaluate_app_gateway_cu_saturation(
    gateway: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    if monitor_facts_status(gateway, "billed_capacity_units") != "available":
        return None
    cu_pct = _cu_utilization_pct(gateway, ctx)
    if cu_pct is None or cu_pct < th["cu_saturation_pct"]:
        return None
    name = gateway.get("name") or ""
    return NetworkFindingDraft(
        rule_id="APP_GATEWAY_CU_SATURATION",
        detail=(
            f"Application Gateway '{name}' billed capacity utilization is {cu_pct:.0f}% "
            f"(threshold {th['cu_saturation_pct']:.0f}%) — risk of throttling."
        ),
        recommendation="Increase autoscale maximum capacity or add instances before reducing other network resources.",
        savings=0.0,
        waste_score=55,
        confidence=confidence_with_monitor(88, gateway),
        priority="P1",
        impact="Prevent application gateway performance degradation",
        evidence=structured_evidence(
            gateway,
            determination="cu_saturation",
            summary="Billed capacity units exceed safe utilization threshold.",
            checks=[make_check("CU utilization %", cu_pct, f">= {th['cu_saturation_pct']:.0f}%", passed=True)],
            extra={"sku_tier": ctx.get("sku_tier"), "capacity": ctx.get("capacity"), "monthly_cost_usd": monthly_cost},
        ),
    )


def evaluate_app_gateway_cu_rightsize(
    gateway: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    if monitor_facts_status(gateway, "billed_capacity_units") != "available":
        return None
    cu_pct = _cu_utilization_pct(gateway, ctx)
    if cu_pct is None or cu_pct >= th["cu_downsize_pct"]:
        return None
    capacity = int(ctx.get("capacity") or 1)
    if capacity <= 1:
        return None
    suggested = max(1, round(capacity * (cu_pct / 100.0) / 0.6))
    if suggested >= capacity:
        return None
    tier_meta = tier_spec(ctx.get("sku_tier"))
    savings = estimate_app_gateway_capacity_savings(
        current_capacity=capacity,
        suggested_capacity=suggested,
        tier_spec=tier_meta,
        actual_monthly_cost=monthly_cost,
        min_savings=th["min_savings"],
    )
    name = gateway.get("name") or ""
    return NetworkFindingDraft(
        rule_id="APP_GATEWAY_CU_RIGHTSIZE_DOWN",
        detail=(
            f"Application Gateway '{name}' averages {cu_pct:.0f}% billed CU utilization — "
            f"capacity {capacity} may be higher than required."
        ),
        recommendation=f"Lower autoscale maximum or fixed capacity toward {suggested} units after validating peak traffic.",
        savings=savings,
        waste_score=58,
        confidence=confidence_with_monitor(80, gateway),
        priority="P2",
        impact="Reduce application gateway fixed and capacity unit charges",
        evidence=structured_evidence(
            gateway,
            determination="cu_rightsize",
            summary="Sustained low billed CU supports capacity reduction.",
            checks=[
                make_check("CU utilization %", cu_pct, f"< {th['cu_downsize_pct']:.0f}%", passed=True),
                make_check("Current capacity", capacity, f"Suggested {suggested}", passed=True),
            ],
            extra={
                "suggested_capacity": suggested,
                "estimated_monthly_savings_usd": savings,
                "monthly_cost_usd": monthly_cost,
            },
        ),
    )


def evaluate_app_gateway_idle_savings(
    gateway: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> float:
    th = _thresholds(rule)
    tier_meta = tier_spec(ctx.get("sku_tier"))
    hourly = float(tier_meta.get("fixed_cost_hourly_usd") or 0.0)
    capacity = int(ctx.get("capacity") or 1)
    hourly += float(tier_meta.get("capacity_unit_hourly_usd") or 0.0) * capacity
    return estimate_decommission_savings(monthly_cost, hourly_usd=hourly, min_savings=th["min_savings"])

"""Network resource savings — catalog hourly rates with MTD cost overlay."""

from __future__ import annotations

from typing import Any

from app.pricing.savings_calculator import savings_from_retail_or_none


def monthly_from_hourly(hourly_usd: float, hours: float = 730.0) -> float:
    return round(float(hourly_usd) * float(hours), 2)


def estimate_decommission_savings(
    actual_monthly_cost: float | None,
    *,
    hourly_usd: float | None = None,
    savings_factor: float = 1.0,
    min_savings: float = 0.0,
) -> float:
    """Full or partial savings when removing an hourly-billed network resource."""
    if actual_monthly_cost and actual_monthly_cost > 0:
        savings = round(float(actual_monthly_cost) * savings_factor, 2)
    elif hourly_usd and hourly_usd > 0:
        savings = round(monthly_from_hourly(hourly_usd) * savings_factor, 2)
    else:
        savings = 0.0
    return savings if savings >= min_savings else 0.0


def estimate_rightsizing_savings(
    actual_monthly_cost: float | None,
    *,
    savings_factor: float,
    hourly_usd: float | None = None,
    min_savings: float = 0.0,
) -> float:
    return estimate_decommission_savings(
        actual_monthly_cost,
        hourly_usd=hourly_usd,
        savings_factor=savings_factor,
        min_savings=min_savings,
    )


def estimate_app_gateway_capacity_savings(
    *,
    current_capacity: int,
    suggested_capacity: int,
    tier_spec: dict[str, Any],
    actual_monthly_cost: float | None = None,
    min_savings: float = 0.0,
) -> float:
    if current_capacity <= 0 or suggested_capacity >= current_capacity:
        return 0.0
    unit_hourly = float(tier_spec.get("capacity_unit_hourly_usd") or 0.0144)
    fixed_hourly = float(tier_spec.get("fixed_cost_hourly_usd") or 0.0)
    removed_units = current_capacity - suggested_capacity
    retail_monthly = monthly_from_hourly(fixed_hourly + unit_hourly * removed_units)
    if actual_monthly_cost and actual_monthly_cost > 0 and current_capacity > 0:
        savings = round(actual_monthly_cost * (removed_units / current_capacity), 2)
    else:
        savings = retail_monthly
    return savings if savings >= min_savings else 0.0


def estimate_flow_log_savings(
    *,
    gb_per_month: float,
    cost_per_gb: float,
    min_savings: float = 0.0,
) -> float:
    savings = round(float(gb_per_month) * float(cost_per_gb), 2)
    return savings if savings >= min_savings else 0.0


def merge_pricing_evidence(pricing: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    out = dict(pricing or {})
    out.update(extra)
    return out


def savings_from_pricing_dict(pricing: dict[str, Any] | None) -> float:
    if not pricing:
        return 0.0
    return float(savings_from_retail_or_none(pricing) or pricing.get("estimated_monthly_savings_usd") or 0.0)


def estimate_nat_gateway_hourly(public_ip_count: int = 1) -> float:
    from app.nat_gateway_catalog import load_nat_gateway_specifications

    pricing = load_nat_gateway_specifications().get("pricing") or {}
    gateway = float(pricing.get("gateway_hourly_usd") or 0.045)
    ip_rate = float(pricing.get("public_ip_hourly_usd") or 0.004)
    return gateway + ip_rate * max(1, int(public_ip_count or 1))


def estimate_load_balancer_hourly() -> float:
    from app.load_balancer_catalog import load_load_balancer_specifications

    pricing = load_load_balancer_specifications().get("pricing") or {}
    return float(pricing.get("hourly_usd_baseline") or 0.025)


def estimate_peering_savings(
    peering_count: int,
    actual_monthly_cost: float | None,
    *,
    savings_factor: float = 0.15,
    min_savings: float = 0.0,
) -> float:
    if actual_monthly_cost and actual_monthly_cost > 0:
        return estimate_rightsizing_savings(
            actual_monthly_cost,
            savings_factor=savings_factor,
            min_savings=min_savings,
        )
    from app.vnet_catalog import load_vnet_specifications

    thresholds = load_vnet_specifications().get("optimization_thresholds") or {}
    per_peering = float(thresholds.get("peering_baseline_monthly_usd") or 10.0)
    savings = round(per_peering * max(1, int(peering_count or 0)) * savings_factor, 2)
    return savings if savings >= min_savings else 0.0

"""Compute resource savings — catalog baselines with MTD cost overlay."""

from __future__ import annotations

from typing import Any

from app.managed_disk_catalog import disk_type_spec, load_disk_specifications
from app.network_pricing import (
    estimate_decommission_savings,
    estimate_rightsizing_savings,
)
from app.snapshot_retention_catalog import pricing_config as snapshot_pricing_config


def estimate_factor_savings(
    actual_monthly_cost: float | None,
    savings_factor: float,
    *,
    hourly_usd: float | None = None,
    min_savings: float = 0.0,
) -> float:
    """Partial savings using MTD cost when available, else catalog hourly baseline."""
    return estimate_rightsizing_savings(
        actual_monthly_cost,
        savings_factor=savings_factor,
        hourly_usd=hourly_usd,
        min_savings=min_savings,
    )


def estimate_disk_monthly_baseline(size_gb: int | float, sku_name: str | None) -> float:
    pricing = load_disk_specifications().get("pricing") or {}
    base_rate = float(pricing.get("per_gb_month_usd_baseline") or 0.04)
    relative = float(disk_type_spec(sku_name).get("relative_cost") or 1.0)
    return round(float(size_gb) * base_rate * relative, 2)


def estimate_disk_capacity_savings(
    actual_monthly_cost: float | None,
    size_gb: int | float,
    sku_name: str | None,
    *,
    savings_factor: float = 0.25,
    min_savings: float = 0.0,
) -> float:
    baseline = actual_monthly_cost if actual_monthly_cost and actual_monthly_cost > 0 else estimate_disk_monthly_baseline(
        size_gb, sku_name
    )
    return estimate_factor_savings(baseline, savings_factor, min_savings=min_savings)


def estimate_snapshot_monthly_baseline(size_gb: int | float) -> float:
    pricing = snapshot_pricing_config()
    rate = float(pricing.get("per_gb_month_usd_baseline") or 0.06)
    return round(float(size_gb) * rate, 2)


def estimate_snapshot_archive_savings(
    actual_monthly_cost: float | None,
    size_gb: int | float,
    *,
    delete_mode: bool = False,
    min_savings: float = 0.0,
) -> float:
    pricing = snapshot_pricing_config()
    archive_pct = float(pricing.get("archive_savings_pct") or 0.95)
    partial_factor = 0.5
    baseline = actual_monthly_cost if actual_monthly_cost and actual_monthly_cost >= min_savings else estimate_snapshot_monthly_baseline(
        size_gb
    )
    if baseline < min_savings:
        return 0.0
    factor = archive_pct if delete_mode else partial_factor
    savings = round(baseline * factor, 2)
    return savings if savings >= min_savings else 0.0


def estimate_egress_savings(
    egress_bytes: float | None,
    actual_monthly_cost: float | None,
    *,
    egress_factor: float = 0.15,
    cost_per_gb_usd: float = 0.087,
    min_savings: float = 0.0,
) -> float:
    """Bandwidth savings from MTD overlay or egress volume × regional rate."""
    if actual_monthly_cost and actual_monthly_cost >= min_savings:
        return estimate_factor_savings(
            actual_monthly_cost,
            egress_factor,
            min_savings=min_savings,
        )
    if egress_bytes is None or float(egress_bytes) <= 0:
        return 0.0
    egress_gb = float(egress_bytes) / (1024**3)
    savings = round(egress_gb * float(cost_per_gb_usd) * egress_factor, 2)
    return savings if savings >= min_savings else 0.0


def estimate_instance_pool_hourly(
    instance_hourly_usd: float,
    capacity: int = 1,
) -> float:
    return float(instance_hourly_usd) * max(1, int(capacity or 1))


def estimate_instance_pool_savings(
    actual_monthly_cost: float | None,
    *,
    instance_hourly_usd: float,
    capacity: int = 1,
    savings_factor: float = 0.25,
    min_savings: float = 0.0,
) -> float:
    hourly = estimate_instance_pool_hourly(instance_hourly_usd, capacity)
    return estimate_factor_savings(
        actual_monthly_cost,
        savings_factor,
        hourly_usd=hourly,
        min_savings=min_savings,
    )


def estimate_app_service_tier_monthly(tier: str | None) -> float:
    from app.app_service_catalog import load_app_service_specifications

    tiers = load_app_service_specifications().get("tiers") or {}
    spec = tiers.get((tier or "").strip()) or {}
    return float(spec.get("monthly_usd_min") or 0.0)


def estimate_app_service_savings(
    actual_monthly_cost: float | None,
    tier: str | None,
    *,
    savings_factor: float = 0.25,
    min_savings: float = 0.0,
) -> float:
    hourly = None
    if not actual_monthly_cost or actual_monthly_cost <= 0:
        monthly_baseline = estimate_app_service_tier_monthly(tier)
        if monthly_baseline > 0:
            hourly = monthly_baseline / 730.0
    return estimate_factor_savings(
        actual_monthly_cost,
        savings_factor,
        hourly_usd=hourly,
        min_savings=min_savings,
    )


def estimate_storage_tier_savings_fallback(
    *,
    hot_rate_per_gb: float,
    cool_rate_per_gb: float,
    assumed_capacity_gb: float = 100.0,
    min_savings: float = 0.0,
) -> float:
    if hot_rate_per_gb <= 0 or cool_rate_per_gb <= 0:
        return 0.0
    savings = round(float(assumed_capacity_gb) * (hot_rate_per_gb - cool_rate_per_gb), 2)
    return savings if savings >= min_savings else 0.0


def vm_instance_hourly_baseline() -> float:
    from app.vm_metrics_catalog import load_vm_specifications

    pricing = load_vm_specifications().get("pricing") or {}
    return float(pricing.get("instance_hourly_usd_baseline") or 0.096)


def vmss_instance_hourly_baseline() -> float:
    from app.vmss_metrics_catalog import load_vmss_specifications

    pricing = load_vmss_specifications().get("pricing") or {}
    return float(pricing.get("instance_hourly_usd_baseline") or vm_instance_hourly_baseline())


def aks_node_hourly_baseline() -> float:
    from app.aks_metrics_catalog import load_aks_specifications

    pricing = load_aks_specifications().get("pricing") or {}
    return float(pricing.get("node_hourly_usd_baseline") or vm_instance_hourly_baseline())


def merge_pricing_evidence(pricing: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    out = dict(pricing or {})
    out.update(extra)
    return out

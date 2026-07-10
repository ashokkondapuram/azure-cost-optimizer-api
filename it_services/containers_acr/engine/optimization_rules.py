"""ACR optimization decision rules — image retention and untagged cleanup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.acr_tier_catalog import optimization_thresholds, tier_spec
from app.acr_utilization import acr_sku_name, storage_used_gb
from app.resource_utilization import (
    confidence_with_monitor,
    fact_value,
    make_check,
    monitor_facts_status,
    structured_evidence,
)


@dataclass(frozen=True)
class ComputeFindingDraft:
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
        "retention_days": float(getattr(rule, "acr_image_retention_days", defaults.get("image_retention_days", 90.0))),
        "storage_high_gb": float(getattr(rule, "acr_storage_high_gb", defaults.get("storage_high_gb", 50.0))),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 5.0))),
    }


def evaluate_acr_image_retention(
    registry: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> ComputeFindingDraft | None:
    th = _thresholds(rule)
    storage_gb = storage_used_gb(registry) or fact_value(registry, "storage_used_gb")
    if storage_gb is None or float(storage_gb) < th["storage_high_gb"]:
        return None
    if monitor_facts_status(registry, "storage_used_gb") not in {"available", "partial"}:
        return None
    sku = acr_sku_name(registry)
    tier = tier_spec(sku)
    included = float(tier.get("included_storage_gb") or 0)
    overage_gb = max(0.0, float(storage_gb) - included)
    if overage_gb <= 0 and float(storage_gb) < th["storage_high_gb"]:
        return None
    name = registry.get("name") or ""
    from app.acr_tier_catalog import load_acr_specifications
    pricing = load_acr_specifications().get("pricing") or {}
    storage_rate = float(pricing.get("storage_per_gb_month_usd", 0.10))
    savings = round(overage_gb * storage_rate * 0.35, 2) if overage_gb > 0 else round(monthly_cost * 0.25, 2)
    if savings < th["min_savings"]:
        savings = 0.0
    return ComputeFindingDraft(
        rule_id="ACR_IMAGE_RETENTION_EXTENDED",
        detail=(
            f"Container registry '{name}' ({sku}) stores {float(storage_gb):.1f} GB — "
            f"review images older than {int(th['retention_days'])} days and untagged manifests."
        ),
        recommendation=(
            f"Enable retention policy to purge untagged images and artifacts older than {int(th['retention_days'])} days."
        ),
        savings=savings,
        waste_score=50,
        confidence=confidence_with_monitor(70, registry),
        priority="P3",
        impact="Image cleanup reduces ACR storage overage charges",
        evidence=structured_evidence(
            registry,
            determination="image_retention_review",
            summary="Registry storage exceeds threshold — retention policy recommended.",
            checks=[
                make_check("Storage used (GB)", storage_gb, f">= {th['storage_high_gb']:.0f}", passed=True),
                make_check("Retention days", th["retention_days"], "Policy target", passed=True),
            ],
            extra={"sku": sku, "included_storage_gb": included, "monthly_cost_usd": monthly_cost},
        ),
    )

"""Central savings calculation — retail pricing with explicit availability status."""
from __future__ import annotations

from typing import Any

from app.cost_utils import savings_from_factor, savings_from_retail_delta


def pricing_status(pricing: dict[str, Any] | None) -> str:
    """Return 'available' when both current and suggested retail prices were resolved."""
    if not pricing:
        return "unavailable"
    current = pricing.get("current_sku_monthly_usd") or pricing.get("current_tier_monthly_usd")
    suggested = pricing.get("suggested_sku_monthly_usd") or pricing.get("suggested_tier_monthly_usd")
    if current is not None and suggested is not None:
        return "available"
    return "unavailable"


def enrich_pricing_payload(pricing: dict[str, Any]) -> dict[str, Any]:
    out = dict(pricing)
    out["pricing_status"] = pricing_status(out)
    return out


def savings_from_retail_or_none(pricing: dict[str, Any] | None) -> float | None:
    """Return retail savings when pricing is available; None when retail lookup failed."""
    if not pricing or pricing_status(pricing) != "available":
        return None
    return savings_from_retail_delta(pricing)


def savings_from_disk_pricing(
    pricing: dict[str, Any] | None,
    *,
    billed_mtd: float,
    full_baseline_for_delete: bool = False,
) -> float:
    """
    Prefer Azure MTD billed cost (PreTaxCost from Cost Management sync).
    Falls back to retail tier delta when billed cost is unavailable.
    """
    if full_baseline_for_delete and billed_mtd > 0:
        return round(billed_mtd, 2)
    if pricing:
        est = pricing.get("estimated_monthly_savings_usd")
        if billed_mtd > 0 and est is not None:
            try:
                return max(0.0, round(float(est), 2))
            except (TypeError, ValueError):
                pass
        retail = savings_from_retail_or_none(pricing)
        if retail is not None and retail > 0:
            return retail
    if billed_mtd > 0:
        return round(billed_mtd, 2)
    return 0.0


def savings_from_retail_or_factor(
    pricing: dict[str, Any] | None,
    *,
    baseline: float,
    factor: float,
    allow_factor_fallback: bool = False,
) -> tuple[float, dict[str, Any]]:
    """
    Prefer Azure retail delta; optionally fall back to heuristic factor.

    Production path sets allow_factor_fallback=False.
    """
    payload = enrich_pricing_payload(pricing or {})
    retail = savings_from_retail_or_none(payload)
    if retail is not None:
        return retail, payload
    if allow_factor_fallback and baseline > 0:
        payload["pricing_status"] = "heuristic_fallback"
        payload["estimated_monthly_savings_usd"] = savings_from_factor(baseline, factor)
        return payload["estimated_monthly_savings_usd"], payload
    payload["pricing_status"] = "unavailable"
    payload["estimated_monthly_savings_usd"] = 0.0
    return 0.0, payload

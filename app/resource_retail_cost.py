"""Per-resource Azure retail / catalog monthly price estimates."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

DiskTier = Literal["premium", "standard_ssd", "standard_hdd"]

_RETAIL_SUPPORTED_TYPES = frozenset({
    "compute/vm",
    "compute/vmss",
    "compute/disk",
    "compute/snapshot",
    "network/loadbalancer",
    "network/appgateway",
    "network/nat",
    "appservice/plan",
})


def _disk_tier_from_sku(sku_name: str | None) -> DiskTier | None:
    name = (sku_name or "").strip().lower()
    if not name:
        return None
    if "premium" in name and "ultra" not in name:
        return "premium"
    if "standardssd" in name or "standard_ssd" in name:
        return "standard_ssd"
    if "standard" in name:
        return "standard_hdd"
    return None


def _vm_sku_from_row(row: dict[str, Any]) -> str | None:
    props = row.get("properties") or {}
    hw = props.get("hardwareProfile") or {}
    sku = hw.get("vmSize") or row.get("sku") or props.get("sku")
    if isinstance(sku, dict):
        sku = sku.get("name") or sku.get("size")
    text = str(sku or "").strip()
    return text or None


def _disk_size_gb(row: dict[str, Any]) -> int:
    props = row.get("properties") or {}
    for key in ("diskSizeGB", "diskSizeGb", "sizeGb"):
        value = props.get(key)
        if value is not None:
            try:
                return max(4, int(value))
            except (TypeError, ValueError):
                pass
    sku_details = row.get("skuDetails") or {}
    for key in ("size", "diskSizeGB"):
        value = sku_details.get(key)
        if value is not None:
            try:
                return max(4, int(value))
            except (TypeError, ValueError):
                pass
    return 128


def _disk_sku_name(row: dict[str, Any]) -> str | None:
    sku = row.get("sku")
    if isinstance(sku, dict):
        return sku.get("name") or sku.get("tier")
    if sku:
        return str(sku)
    props = row.get("properties") or {}
    sku_obj = props.get("sku") or {}
    if isinstance(sku_obj, dict):
        return sku_obj.get("name") or sku_obj.get("tier")
    return None


def _region_from_row(row: dict[str, Any]) -> str:
    return str(row.get("location") or row.get("region") or "eastus")


def _resolve_db_session(db: Session | None) -> tuple[Session | None, bool]:
    """Return (session, should_close). Opens a short-lived session when db is None."""
    if db is not None:
        return db, False
    try:
        from app.database import SessionLocal

        return SessionLocal(), True
    except Exception:
        return None, False


def estimate_resource_retail_monthly(
    row: dict[str, Any],
    db: Session | None = None,
    *,
    price_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Estimate catalog monthly price for one inventory row.

    Returns retail_monthly, retail_currency, retail_source, retail_pending.
    Uses unified resource_sku_pricing table first, then Azure Retail Prices API,
    then catalog thresholds as fallback.
    """
    canonical = str(row.get("type") or row.get("resource_type") or row.get("canonical_type") or "").strip().lower()
    region = _region_from_row(row)
    billing_currency = str(row.get("billingCurrency") or row.get("billing_currency") or "USD")

    if canonical not in _RETAIL_SUPPORTED_TYPES:
        return {
            "retail_monthly": None,
            "retail_currency": billing_currency,
            "retail_source": None,
            "retail_pending": True,
        }

    session, close_session = _resolve_db_session(db)
    monthly: float | None = None
    source: str | None = None

    try:
        if session is not None and canonical in {"compute/vm", "compute/vmss", "compute/disk"}:
            try:
                from app.azure_retail_price_store import resolve_retail_monthly_for_row

                stored = resolve_retail_monthly_for_row(row, session, cache=price_cache)
                if stored and stored.get("monthly_price_usd"):
                    monthly = float(stored["monthly_price_usd"])
                    source = stored.get("price_source")
            except Exception:
                pass

        if monthly is None:
            if canonical in {"compute/vm", "compute/vmss"}:
                from app.azure_retail_pricing import get_vm_monthly_price, vm_os_type

                sku = _vm_sku_from_row(row)
                if sku:
                    os_type = vm_os_type(row)
                    monthly = get_vm_monthly_price(region, sku, os_type=os_type)
                    source = "azure_retail_prices"

            elif canonical == "compute/disk":
                from app.azure_retail_pricing import get_managed_disk_monthly_price

                sku_name = _disk_sku_name(row)
                tier = _disk_tier_from_sku(sku_name)
                if tier:
                    monthly = get_managed_disk_monthly_price(
                        region,
                        size_gb=_disk_size_gb(row),
                        tier=tier,
                    )
                    source = "azure_retail_prices"
                elif sku_name:
                    from app.compute_pricing import estimate_disk_monthly_baseline

                    monthly = estimate_disk_monthly_baseline(_disk_size_gb(row), sku_name)
                    source = "catalog_thresholds" if monthly else None

            elif canonical == "compute/snapshot":
                from app.compute_pricing import estimate_snapshot_monthly_baseline

                monthly = estimate_snapshot_monthly_baseline(_disk_size_gb(row))
                source = "catalog_thresholds"

            elif canonical == "network/loadbalancer":
                from app.azure_retail_pricing import estimate_load_balancer_monthly_price

                payload = estimate_load_balancer_monthly_price()
                monthly = payload.get("estimated_monthly_usd")
                source = payload.get("pricing_source")

            elif canonical == "network/appgateway":
                from app.azure_retail_pricing import estimate_app_gateway_monthly_price

                props = row.get("properties") or {}
                sku = props.get("sku") or {}
                tier = sku.get("name") or sku.get("tier") or row.get("sku") or "Standard_v2"
                capacity = int((props.get("autoscaleConfiguration") or {}).get("minCapacity") or 1)
                payload = estimate_app_gateway_monthly_price(tier=str(tier), capacity=capacity)
                monthly = payload.get("estimated_monthly_usd")
                source = payload.get("pricing_source")

            elif canonical == "network/nat":
                from app.azure_retail_pricing import estimate_nat_gateway_monthly_price

                payload = estimate_nat_gateway_monthly_price()
                monthly = payload.get("estimated_monthly_usd")
                source = payload.get("pricing_source")

            elif canonical == "appservice/plan":
                from app.compute_pricing import estimate_app_service_tier_monthly

                sku = row.get("sku")
                tier = sku.get("name") if isinstance(sku, dict) else sku
                monthly = estimate_app_service_tier_monthly(str(tier) if tier else None)
                source = "catalog_thresholds" if monthly else None

    except Exception:
        monthly = None
        source = None
    finally:
        if close_session and session is not None:
            session.close()

    if monthly is not None and monthly > 0:
        retail_source = source or "azure_retail_prices"
        return {
            "retail_monthly": round(float(monthly), 2),
            "retail_currency": "USD" if retail_source in {"azure_retail_prices", "catalog_fallback"} else billing_currency,
            "retail_source": retail_source,
            "retail_pending": False,
        }

    return {
        "retail_monthly": None,
        "retail_currency": billing_currency,
        "retail_source": None,
        "retail_pending": True,
    }

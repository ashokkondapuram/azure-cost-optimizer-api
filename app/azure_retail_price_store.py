"""Persistent Azure retail / catalog SKU price cache (resource_sku_pricing table)."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models import ResourceSkuPricing

DiskTier = Literal["premium", "standard_ssd", "standard_hdd"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _float_env(name: str, default: float) -> float:
    try:
        return max(1.0, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def retail_price_db_ttl_hours() -> float:
    return _float_env("RETAIL_PRICE_DB_TTL_HOURS", 168.0)


def normalize_region(region: str | None) -> str:
    return (region or "").strip().replace(" ", "").lower()


def make_lookup_key(
    canonical_type: str,
    region: str,
    arm_sku_name: str,
    *,
    capacity_gb: int | None = None,
    os_type: str | None = None,
) -> str:
    parts = [
        (canonical_type or "").strip().lower(),
        normalize_region(region),
        (arm_sku_name or "").strip().lower(),
    ]
    if capacity_gb is not None:
        parts.append(str(int(capacity_gb)))
    if os_type:
        parts.append((os_type or "").strip().lower())
    return "|".join(parts)


@dataclass(frozen=True)
class SkuPriceRequest:
    canonical_type: str
    region: str
    arm_sku_name: str
    capacity_gb: int | None = None
    os_type: str | None = None
    sku_name: str | None = None

    @property
    def lookup_key(self) -> str:
        return make_lookup_key(
            self.canonical_type,
            self.region,
            self.arm_sku_name,
            capacity_gb=self.capacity_gb,
            os_type=self.os_type,
        )


def _row_is_fresh(row: ResourceSkuPricing, *, now: datetime | None = None) -> bool:
    if row.monthly_price_usd is None or row.monthly_price_usd <= 0:
        return False
    current = now or _now()
    expires_at = row.expires_at
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > current


def lookup_cached_price(
    db: Session,
    request: SkuPriceRequest,
    *,
    allow_stale: bool = True,
) -> dict[str, Any] | None:
    """Return cached monthly price row when present (fresh or stale)."""
    row = (
        db.query(ResourceSkuPricing)
        .filter(ResourceSkuPricing.lookup_key == request.lookup_key)
        .first()
    )
    if not row:
        return None
    if not allow_stale and not _row_is_fresh(row):
        return None
    return {
        "monthly_price_usd": float(row.monthly_price_usd),
        "currency": row.currency or "USD",
        "price_source": row.price_source,
        "fresh": _row_is_fresh(row),
        "lookup_key": row.lookup_key,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
    }


def batch_lookup_cached_prices(
    db: Session,
    requests: list[SkuPriceRequest],
    *,
    allow_stale: bool = True,
) -> dict[str, dict[str, Any]]:
    if not requests:
        return {}
    keys = [req.lookup_key for req in requests]
    rows = (
        db.query(ResourceSkuPricing)
        .filter(ResourceSkuPricing.lookup_key.in_(keys))
        .all()
    )
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not allow_stale and not _row_is_fresh(row):
            continue
        out[row.lookup_key] = {
            "monthly_price_usd": float(row.monthly_price_usd),
            "currency": row.currency or "USD",
            "price_source": row.price_source,
            "fresh": _row_is_fresh(row),
            "lookup_key": row.lookup_key,
            "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        }
    return out


def upsert_sku_price(
    db: Session,
    *,
    canonical_type: str,
    region: str,
    arm_sku_name: str,
    monthly_price_usd: float,
    price_source: str,
    capacity_gb: int | None = None,
    os_type: str | None = None,
    sku_name: str | None = None,
    unit_price: float | None = None,
    unit_of_measure: str | None = None,
    currency: str = "USD",
    sku_details: dict[str, Any] | None = None,
    subscription_id: str | None = None,
    ttl_hours: float | None = None,
) -> ResourceSkuPricing:
    """Insert or update one SKU price row."""
    if monthly_price_usd <= 0:
        raise ValueError("monthly_price_usd must be positive")

    lookup_key = make_lookup_key(
        canonical_type,
        region,
        arm_sku_name,
        capacity_gb=capacity_gb,
        os_type=os_type,
    )
    now = _now()
    ttl = ttl_hours if ttl_hours is not None else retail_price_db_ttl_hours()
    expires_at = now + timedelta(hours=ttl)

    row = (
        db.query(ResourceSkuPricing)
        .filter(ResourceSkuPricing.lookup_key == lookup_key)
        .first()
    )
    if row is None:
        row = ResourceSkuPricing(
            id=str(uuid.uuid4()),
            lookup_key=lookup_key,
        )
        db.add(row)

    row.subscription_id = (subscription_id or "").strip().lower() or None
    row.canonical_type = canonical_type.strip().lower()
    row.arm_sku_name = arm_sku_name
    row.sku_name = sku_name or arm_sku_name
    row.region = normalize_region(region)
    row.capacity_gb = int(capacity_gb) if capacity_gb is not None else None
    row.os_type = (os_type or "").strip().lower() or None
    row.unit_price = unit_price
    row.unit_of_measure = unit_of_measure
    row.monthly_price_usd = round(float(monthly_price_usd), 2)
    row.currency = currency or "USD"
    row.price_source = price_source
    row.sku_details_json = json.dumps(sku_details or {})
    row.fetched_at = now
    row.expires_at = expires_at
    return row


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


def fetch_disk_monthly_price(
    region: str,
    *,
    size_gb: int | float,
    sku_name: str,
    db: Session | None = None,
    persist: bool = True,
) -> dict[str, Any] | None:
    """Fetch managed disk monthly price from cache, retail API, or catalog fallback."""
    tier = _disk_tier_from_sku(sku_name)
    if not tier:
        return None

    billed_size = max(4, int(size_gb or 4))
    request = SkuPriceRequest(
        canonical_type="compute/disk",
        region=region,
        arm_sku_name=sku_name,
        capacity_gb=billed_size,
        sku_name=sku_name,
    )

    if db is not None:
        cached = lookup_cached_price(db, request, allow_stale=True)
        if cached and cached.get("fresh"):
            return cached

    monthly: float | None = None
    source = "azure_retail_prices"
    try:
        from app.azure_retail_pricing import get_managed_disk_monthly_price

        monthly = get_managed_disk_monthly_price(
            region,
            size_gb=billed_size,
            tier=tier,
        )
    except Exception:
        monthly = None

    if monthly is None or monthly <= 0:
        from app.compute_pricing import estimate_disk_monthly_baseline

        monthly = estimate_disk_monthly_baseline(billed_size, sku_name)
        source = "catalog_fallback" if monthly else None

    if monthly is None or monthly <= 0:
        return None

    payload = {
        "monthly_price_usd": round(float(monthly), 2),
        "currency": "USD",
        "price_source": source,
        "fresh": True,
        "lookup_key": request.lookup_key,
    }

    if db is not None and persist:
        upsert_sku_price(
            db,
            canonical_type="compute/disk",
            region=region,
            arm_sku_name=sku_name,
            capacity_gb=billed_size,
            sku_name=sku_name,
            monthly_price_usd=payload["monthly_price_usd"],
            price_source=source or "catalog_fallback",
            sku_details={"tier": tier, "billed_size_gb": billed_size},
        )

    return payload


def fetch_vm_monthly_price(
    region: str,
    sku: str,
    *,
    os_type: str = "linux",
    db: Session | None = None,
    persist: bool = True,
) -> dict[str, Any] | None:
    """Fetch VM monthly price from cache, retail API, or return None."""
    arm_sku = (sku or "").strip()
    if not arm_sku:
        return None

    request = SkuPriceRequest(
        canonical_type="compute/vm",
        region=region,
        arm_sku_name=arm_sku,
        os_type=os_type,
        sku_name=arm_sku,
    )

    if db is not None:
        cached = lookup_cached_price(db, request, allow_stale=True)
        if cached and cached.get("fresh"):
            return cached

    monthly: float | None = None
    try:
        from app.azure_retail_pricing import get_vm_monthly_price

        monthly = get_vm_monthly_price(region, arm_sku, os_type=os_type)
    except Exception:
        monthly = None

    if monthly is None or monthly <= 0:
        return None

    payload = {
        "monthly_price_usd": round(float(monthly), 2),
        "currency": "USD",
        "price_source": "azure_retail_prices",
        "fresh": True,
        "lookup_key": request.lookup_key,
    }

    if db is not None and persist:
        upsert_sku_price(
            db,
            canonical_type="compute/vm",
            region=region,
            arm_sku_name=arm_sku,
            os_type=os_type,
            sku_name=arm_sku,
            monthly_price_usd=payload["monthly_price_usd"],
            price_source="azure_retail_prices",
            sku_details={"os_type": os_type},
        )

    return payload


def resolve_retail_monthly_for_row(
    row: dict[str, Any],
    db: Session | None = None,
    *,
    cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """
    Resolve retail monthly price for one inventory row using the unified table.

    Returns dict with monthly_price_usd, currency, price_source or None.
    """
    canonical = str(row.get("type") or row.get("resource_type") or row.get("canonical_type") or "").strip().lower()
    region = str(row.get("location") or row.get("region") or "eastus")

    if canonical in {"compute/vm", "compute/vmss"}:
        from app.resource_retail_cost import _vm_sku_from_row
        from app.azure_retail_pricing import vm_os_type

        sku = _vm_sku_from_row(row)
        if not sku:
            return None
        os_type = vm_os_type(row)
        request = SkuPriceRequest(
            canonical_type=canonical,
            region=region,
            arm_sku_name=sku,
            os_type=os_type,
        )
        if cache is not None and request.lookup_key in cache:
            return cache[request.lookup_key]
        if db is not None:
            cached = lookup_cached_price(db, request, allow_stale=True)
            if cached:
                if cache is not None:
                    cache[request.lookup_key] = cached
                return cached
        result = fetch_vm_monthly_price(region, sku, os_type=os_type, db=db)
        if result and cache is not None:
            cache[request.lookup_key] = result
        return result

    if canonical == "compute/disk":
        from app.resource_retail_cost import _disk_size_gb, _disk_sku_name

        sku_name = _disk_sku_name(row)
        if not sku_name:
            return None
        size_gb = _disk_size_gb(row)
        request = SkuPriceRequest(
            canonical_type="compute/disk",
            region=region,
            arm_sku_name=sku_name,
            capacity_gb=size_gb,
            sku_name=sku_name,
        )
        if cache is not None and request.lookup_key in cache:
            return cache[request.lookup_key]
        if db is not None:
            cached = lookup_cached_price(db, request, allow_stale=True)
            if cached:
                if cache is not None:
                    cache[request.lookup_key] = cached
                return cached
        result = fetch_disk_monthly_price(region, size_gb=size_gb, sku_name=sku_name, db=db)
        if result and cache is not None:
            cache[request.lookup_key] = result
        return result

    return None

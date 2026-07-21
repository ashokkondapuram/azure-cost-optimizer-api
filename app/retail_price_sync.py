"""Batch sync Azure retail SKU prices into resource_sku_pricing."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.azure_retail_price_store import (
    SkuPriceRequest,
    batch_lookup_cached_prices,
    fetch_disk_monthly_price,
    fetch_vm_monthly_price,
    lookup_cached_price,
    normalize_region,
    upsert_sku_price,
)
from app.models import ResourceSnapshot

log = structlog.get_logger(__name__)

_DEFAULT_REGIONS = ("eastus", "canadacentral", "westeurope", "centralus")

_DISK_SKUS = (
    "Premium_LRS",
    "Premium_ZRS",
    "StandardSSD_LRS",
    "StandardSSD_ZRS",
    "Standard_LRS",
)

_DISK_SIZES_GB = (4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096)


def _disk_size_from_snapshot(row: ResourceSnapshot) -> int | None:
    import json

    try:
        props = json.loads(row.properties_json or "{}")
    except Exception:
        props = {}
    for key in ("diskSizeGB", "diskSizeGb", "sizeGb"):
        value = props.get(key)
        if value is not None:
            try:
                return max(4, int(value))
            except (TypeError, ValueError):
                pass
    try:
        sku_details = json.loads(row.sku_json or "{}")
        if sku_details.get("size") is not None:
            return max(4, int(sku_details["size"]))
    except Exception:
        pass
    return None


def collect_sku_requests_from_inventory(
    db: Session,
    *,
    subscription_id: str | None = None,
) -> list[SkuPriceRequest]:
    """Build unique SKU price requests from active inventory snapshots."""
    q = db.query(ResourceSnapshot).filter(ResourceSnapshot.is_active.is_(True))
    if subscription_id:
        q = q.filter(ResourceSnapshot.subscription_id == subscription_id.strip().lower())

    seen: set[str] = set()
    requests: list[SkuPriceRequest] = []

    for snap in q.all():
        canonical = (snap.resource_type or "").strip().lower()
        region = normalize_region(snap.location or "eastus")
        if not region:
            continue

        if canonical in {"compute/vm", "compute/vmss"}:
            sku = (snap.sku or "").strip()
            if not sku:
                continue
            req = SkuPriceRequest(
                canonical_type=canonical,
                region=region,
                arm_sku_name=sku,
                os_type="linux",
                sku_name=sku,
            )
            if req.lookup_key not in seen:
                seen.add(req.lookup_key)
                requests.append(req)
            req_win = SkuPriceRequest(
                canonical_type=canonical,
                region=region,
                arm_sku_name=sku,
                os_type="windows",
                sku_name=sku,
            )
            if req_win.lookup_key not in seen:
                seen.add(req_win.lookup_key)
                requests.append(req_win)

        elif canonical == "compute/disk":
            sku = (snap.sku or "").strip()
            if not sku:
                continue
            size_gb = _disk_size_from_snapshot(snap) or 128
            req = SkuPriceRequest(
                canonical_type="compute/disk",
                region=region,
                arm_sku_name=sku,
                capacity_gb=size_gb,
                sku_name=sku,
            )
            if req.lookup_key not in seen:
                seen.add(req.lookup_key)
                requests.append(req)

    return requests


def seed_catalog_disk_prices(
    db: Session,
    regions: list[str] | None = None,
) -> int:
    """Seed catalog-fallback disk prices for common SKUs, regions, and sizes."""
    from app.compute_pricing import estimate_disk_monthly_baseline

    region_list = [normalize_region(r) for r in (regions or _DEFAULT_REGIONS) if r]
    written = 0
    for region in region_list:
        for sku_name in _DISK_SKUS:
            for size_gb in _DISK_SIZES_GB:
                monthly = estimate_disk_monthly_baseline(size_gb, sku_name)
                if not monthly or monthly <= 0:
                    continue
                existing = lookup_cached_price(
                    db,
                    SkuPriceRequest(
                        canonical_type="compute/disk",
                        region=region,
                        arm_sku_name=sku_name,
                        capacity_gb=size_gb,
                    ),
                    allow_stale=True,
                )
                if existing and existing.get("price_source") == "azure_retail_prices":
                    continue
                upsert_sku_price(
                    db,
                    canonical_type="compute/disk",
                    region=region,
                    arm_sku_name=sku_name,
                    capacity_gb=size_gb,
                    sku_name=sku_name,
                    monthly_price_usd=monthly,
                    price_source="catalog_fallback",
                    sku_details={"seed": "catalog_disk_grid"},
                )
                written += 1
    return written


def sync_retail_sku_prices(
    db: Session,
    *,
    subscription_id: str | None = None,
    regions: list[str] | None = None,
    force: bool = False,
    fetch_retail_api: bool = True,
    seed_catalog: bool = True,
) -> dict[str, Any]:
    """
    Populate resource_sku_pricing from inventory SKUs + optional catalog seed.

    When fetch_retail_api=True, calls Azure Retail Prices API (throttled).
    Stale or missing rows fall back to catalog estimates for disks.
    """
    stats: dict[str, Any] = {
        "inventory_requests": 0,
        "fetched_api": 0,
        "catalog_fallback": 0,
        "skipped_fresh": 0,
        "seeded_catalog": 0,
        "errors": 0,
    }

    if seed_catalog:
        stats["seeded_catalog"] = seed_catalog_disk_prices(db, regions=regions)

    requests = collect_sku_requests_from_inventory(db, subscription_id=subscription_id)
    stats["inventory_requests"] = len(requests)

    if not force:
        cached = batch_lookup_cached_prices(db, requests, allow_stale=False)
    else:
        cached = {}

    for req in requests:
        if not force and req.lookup_key in cached:
            stats["skipped_fresh"] += 1
            continue

        try:
            if req.canonical_type in {"compute/vm", "compute/vmss"}:
                if not fetch_retail_api:
                    continue
                result = fetch_vm_monthly_price(
                    req.region,
                    req.arm_sku_name,
                    os_type=req.os_type or "linux",
                    db=db,
                )
                if result:
                    stats["fetched_api"] += 1
                continue

            if req.canonical_type == "compute/disk":
                result = fetch_disk_monthly_price(
                    req.region,
                    size_gb=req.capacity_gb or 128,
                    sku_name=req.arm_sku_name,
                    db=db,
                    persist=fetch_retail_api or True,
                )
                if not result:
                    stats["errors"] += 1
                elif result.get("price_source") == "azure_retail_prices":
                    stats["fetched_api"] += 1
                elif result.get("price_source") == "catalog_fallback":
                    stats["catalog_fallback"] += 1
        except Exception as exc:
            stats["errors"] += 1
            log.warning(
                "retail_price_sync.item_failed",
                lookup_key=req.lookup_key,
                error=str(exc)[:200],
            )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    log.info("retail_price_sync.complete", **stats)
    return stats


def distinct_inventory_regions(db: Session, subscription_id: str | None = None) -> list[str]:
    q = db.query(ResourceSnapshot.location).filter(ResourceSnapshot.is_active.is_(True))
    if subscription_id:
        q = q.filter(ResourceSnapshot.subscription_id == subscription_id.strip().lower())
    regions = sorted(
        {
            normalize_region(row[0])
            for row in q.distinct().all()
            if row and row[0]
        }
    )
    return regions or list(_DEFAULT_REGIONS)

"""Quota Page Router

Fetches Azure subscription quota and usage for all connected subscriptions.

Endpoints
---------
GET  /quota/{subscription_id}/compute
     Compute (vCPU, VM family) quotas and usage for a location
GET  /quota/{subscription_id}/network
     Network resource quotas (Public IPs, VNets, LBs, NSGs, etc.)
GET  /quota/{subscription_id}/storage
     Storage account quotas
GET  /quota/{subscription_id}/all
     Combined compute + network + storage for a given location
GET  /quota/summary
     Cross-subscription quota summary (all connected subscriptions)

API references:
  https://learn.microsoft.com/en-us/rest/api/compute/usage/list
  https://learn.microsoft.com/en-us/rest/api/virtualnetwork/usages/list
  https://learn.microsoft.com/en-us/rest/api/storagerp/usages/list-by-location
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import auth_headers
from app.database import get_db
from app.http_client import _get, get_all_pages, BASE, AzureAPIError
from app.user_auth import require_viewer

router = APIRouter(prefix="/quota", tags=["Quota"])

_COMPUTE_USAGE_API = "2024-03-01"
_NETWORK_USAGE_API = "2022-11-01"
_STORAGE_USAGE_API = "2023-01-01"
_QUOTA_WARN_PCT = 80.0  # trigger warning notification above this %
_QUOTA_CRITICAL_PCT = 95.0


def _db(db: Session = Depends(get_db), _=Depends(require_viewer)):
    return db


def _usage_to_dict(item: dict, source: str) -> dict[str, Any]:
    name = (item.get("name") or {})
    limit = item.get("limit", 0) or 0
    current = item.get("currentValue", 0) or 0
    pct = round((current / limit * 100) if limit > 0 else 0.0, 1)
    return {
        "name": name.get("value") or name.get("localizedValue") or "",
        "localized_name": name.get("localizedValue") or name.get("value") or "",
        "current": current,
        "limit": limit,
        "usage_pct": pct,
        "source": source,
        "status": (
            "critical" if pct >= _QUOTA_CRITICAL_PCT
            else "warning" if pct >= _QUOTA_WARN_PCT
            else "ok"
        ),
    }


# ---------------------------------------------------------------------------
# Raw quota fetchers
# ---------------------------------------------------------------------------

def _fetch_compute_quota(subscription_id: str, location: str, headers: dict) -> list[dict]:
    url = (
        f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute"
        f"/locations/{location}/usages"
    )
    try:
        items = get_all_pages(url, headers, {"api-version": _COMPUTE_USAGE_API})
        return [_usage_to_dict(i, "compute") for i in items]
    except AzureAPIError as exc:
        return [{"error": str(exc), "source": "compute"}]


def _fetch_network_quota(subscription_id: str, location: str, headers: dict) -> list[dict]:
    url = (
        f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network"
        f"/locations/{location}/usages"
    )
    try:
        items = get_all_pages(url, headers, {"api-version": _NETWORK_USAGE_API})
        return [_usage_to_dict(i, "network") for i in items]
    except AzureAPIError as exc:
        return [{"error": str(exc), "source": "network"}]


def _fetch_storage_quota(subscription_id: str, location: str, headers: dict) -> list[dict]:
    url = (
        f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Storage"
        f"/locations/{location}/usages"
    )
    try:
        items = get_all_pages(url, headers, {"api-version": _STORAGE_USAGE_API})
        return [_usage_to_dict(i, "storage") for i in items]
    except AzureAPIError as exc:
        return [{"error": str(exc), "source": "storage"}]


def _near_limit(items: list[dict]) -> list[dict]:
    return [i for i in items if isinstance(i.get("usage_pct"), float) and i["usage_pct"] >= _QUOTA_WARN_PCT]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/{subscription_id}/compute")
def compute_quota(
    subscription_id: str,
    location: str = Query(..., description="Azure region, e.g. eastus"),
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """Compute vCPU and VM family quotas for a location."""
    headers = auth_headers(db)
    items = _fetch_compute_quota(subscription_id, location, headers)
    return {
        "subscription_id": subscription_id,
        "location": location,
        "count": len(items),
        "near_limit": _near_limit(items),
        "items": items,
    }


@router.get("/{subscription_id}/network")
def network_quota(
    subscription_id: str,
    location: str = Query(...),
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """Network resource quotas (VNets, Public IPs, NSGs, LBs, etc.)."""
    headers = auth_headers(db)
    items = _fetch_network_quota(subscription_id, location, headers)
    return {
        "subscription_id": subscription_id,
        "location": location,
        "count": len(items),
        "near_limit": _near_limit(items),
        "items": items,
    }


@router.get("/{subscription_id}/storage")
def storage_quota(
    subscription_id: str,
    location: str = Query(...),
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """Storage account quotas."""
    headers = auth_headers(db)
    items = _fetch_storage_quota(subscription_id, location, headers)
    return {
        "subscription_id": subscription_id,
        "location": location,
        "count": len(items),
        "near_limit": _near_limit(items),
        "items": items,
    }


@router.get("/{subscription_id}/all")
def all_quota(
    subscription_id: str,
    location: str = Query(...),
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """Combined compute + network + storage quota for a location."""
    import concurrent.futures
    headers = auth_headers(db)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix="quota") as pool:
        f_compute = pool.submit(_fetch_compute_quota, subscription_id, location, headers)
        f_network = pool.submit(_fetch_network_quota, subscription_id, location, headers)
        f_storage = pool.submit(_fetch_storage_quota, subscription_id, location, headers)
        compute = f_compute.result()
        network = f_network.result()
        storage = f_storage.result()

    all_items = compute + network + storage
    near = _near_limit(all_items)
    critical = [i for i in near if i.get("status") == "critical"]

    return {
        "subscription_id": subscription_id,
        "location": location,
        "totals": {
            "compute": len(compute),
            "network": len(network),
            "storage": len(storage),
        },
        "near_limit_count": len(near),
        "critical_count": len(critical),
        "near_limit": near,
        "compute": compute,
        "network": network,
        "storage": storage,
    }


@router.get("/summary")
def quota_summary(
    location: str = Query(..., description="Azure region to check across all subscriptions"),
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """Cross-subscription quota summary for all connected subscriptions.

    Returns per-subscription near-limit and critical counts so the UI can
    show a global quota health panel.
    """
    import concurrent.futures
    from app.subscription_store import list_active_subscriptions

    subs = list_active_subscriptions(db)
    headers = auth_headers(db)

    def check_sub(sub_id: str) -> dict[str, Any]:
        all_items: list[dict] = []
        for fetcher in (_fetch_compute_quota, _fetch_network_quota, _fetch_storage_quota):
            all_items.extend(fetcher(sub_id, location, headers))
        near = _near_limit(all_items)
        critical = [i for i in near if i.get("status") == "critical"]
        return {
            "subscription_id": sub_id,
            "total_quota_types": len(all_items),
            "near_limit_count": len(near),
            "critical_count": len(critical),
            "near_limit": near[:20],  # truncate for summary
        }

    workers = min(len(subs), 5) if subs else 1
    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="quota_summary"
    ) as pool:
        results = list(pool.map(check_sub, [s.subscription_id for s in subs]))

    total_critical = sum(r["critical_count"] for r in results)
    total_warning = sum(r["near_limit_count"] - r["critical_count"] for r in results)

    return {
        "location": location,
        "subscriptions_checked": len(results),
        "global_critical_count": total_critical,
        "global_warning_count": total_warning,
        "by_subscription": results,
    }

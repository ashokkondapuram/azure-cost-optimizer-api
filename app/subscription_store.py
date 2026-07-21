"""Subscription list — DB cache with fallbacks from synced operational data."""
from __future__ import annotations

import json
import os
import structlog
import threading
import time
from typing import Any

from sqlalchemy.orm import Session

from app.azure_resources import AzureResourcesClient
from app.models import (
    BudgetSnapshot,
    CostByResourceSnapshot,
    CostByServiceSnapshot,
    CostDailyByServiceSnapshot,
    CostSnapshot,
    OptimizationFinding,
    OptimizationRun,
    ResourceSnapshot,
    SubscriptionCache,
)

log = structlog.get_logger(__name__)

_REGISTERED_IDS_CACHE: set[str] | None = None
_REGISTERED_IDS_CACHE_AT: float = 0.0
_REGISTERED_IDS_CACHE_LOCK = threading.Lock()
_REGISTERED_IDS_CACHE_TTL_SEC = max(
    30,
    int(os.getenv("SUBSCRIPTION_IDS_CACHE_TTL_SEC", "45")),
)

_MODELS_WITH_SUBSCRIPTION = (
    ResourceSnapshot,
    OptimizationRun,
    CostByServiceSnapshot,
    CostByResourceSnapshot,
    CostDailyByServiceSnapshot,
    BudgetSnapshot,
    CostSnapshot,
    OptimizationFinding,
)


def normalize_arm_subscription(sub: dict[str, Any]) -> dict[str, Any] | None:
    sid = (sub.get("subscriptionId") or sub.get("subscription_id") or "").strip()
    if not sid and sub.get("id"):
        sid = str(sub["id"]).rstrip("/").split("/")[-1]
    sid = sid.lower()
    if not sid:
        return None
    return {
        "subscriptionId": sid,
        "displayName": sub.get("displayName") or sub.get("display_name") or sid,
        "state": sub.get("state") or "Unknown",
        "tenantId": sub.get("tenantId") or sub.get("tenant_id"),
    }


def _from_cache_row(row: SubscriptionCache) -> dict[str, Any]:
    return {
        "subscriptionId": row.subscription_id,
        "displayName": row.display_name or row.subscription_id,
        "state": row.state or "Unknown",
        "tenantId": row.tenant_id,
    }


def _distinct_subscription_ids(db: Session) -> set[str]:
    sub_ids: set[str] = set()
    for model in _MODELS_WITH_SUBSCRIPTION:
        for (sid,) in db.query(model.subscription_id).distinct():
            if sid:
                sub_ids.add(str(sid).lower())
    return sub_ids


def invalidate_registered_subscription_ids_cache() -> None:
    """Drop the in-process registered-subscription set (call after cache mutations)."""
    global _REGISTERED_IDS_CACHE, _REGISTERED_IDS_CACHE_AT
    with _REGISTERED_IDS_CACHE_LOCK:
        _REGISTERED_IDS_CACHE = None
        _REGISTERED_IDS_CACHE_AT = 0.0


def subscription_cache_has(db: Session, subscription_id: str) -> bool:
    """True when subscription_id exists in subscription_cache (single indexed lookup)."""
    sid = (subscription_id or "").strip().lower()
    if not sid:
        return False
    return (
        db.query(SubscriptionCache.subscription_id)
        .filter(SubscriptionCache.subscription_id == sid)
        .first()
        is not None
    )


def is_subscription_registered(db: Session, subscription_id: str) -> bool:
    """Fast registration check for hot paths — cache row or configured default only."""
    sid = (subscription_id or "").strip().lower()
    if not sid:
        return False
    if subscription_cache_has(db, sid):
        return True
    default_sid = get_default_subscription_id(db)
    return default_sid is not None and sid == default_sid


def get_default_subscription_id(db: Session) -> str | None:
    """Configured default subscription (Settings → Azure or AZURE_DEFAULT_SUBSCRIPTION_ID)."""
    try:
        from app.services.system_settings import get_effective_config

        cfg = get_effective_config(db, "azure")
        sid = (cfg.get("default_subscription_id") or "").strip().lower()
        return sid or None
    except Exception:
        return None


# Backward-compatible alias used by existing modules and tests.
_default_subscription_from_settings = get_default_subscription_id


def registered_subscription_ids(db: Session, *, force_refresh: bool = False) -> set[str]:
    """Subscription IDs registered for this deployment (cache + synced data + default)."""
    global _REGISTERED_IDS_CACHE, _REGISTERED_IDS_CACHE_AT

    now = time.monotonic()
    if not force_refresh:
        with _REGISTERED_IDS_CACHE_LOCK:
            if (
                _REGISTERED_IDS_CACHE is not None
                and (now - _REGISTERED_IDS_CACHE_AT) < _REGISTERED_IDS_CACHE_TTL_SEC
            ):
                return set(_REGISTERED_IDS_CACHE)

    known = _distinct_subscription_ids(db)
    default_sid = get_default_subscription_id(db)
    if default_sid:
        known.add(default_sid)
    for (sid,) in db.query(SubscriptionCache.subscription_id).all():
        if sid:
            known.add(str(sid).lower())

    with _REGISTERED_IDS_CACHE_LOCK:
        _REGISTERED_IDS_CACHE = set(known)
        _REGISTERED_IDS_CACHE_AT = now
    return known


def list_active_subscription_ids(db: Session) -> list[str]:
    """Subscription IDs targeted by sync workers and schedulers.

    When ``default_subscription_id`` is configured, returns only that subscription
    (single-subscription mode). Otherwise returns cache rows, then cached full set.
    """
    default_sid = get_default_subscription_id(db)
    if default_sid:
        return [default_sid]

    rows = db.query(SubscriptionCache.subscription_id).order_by(SubscriptionCache.display_name).all()
    cached = sorted({str(sid).lower() for (sid,) in rows if sid})
    if cached:
        return cached

    known = registered_subscription_ids(db)
    return sorted(known) if known else []


def list_active_subscriptions(db: Session) -> list[dict[str, str]]:
    """Active subscriptions as ``{subscription_id: ...}`` records for worker loops."""
    return [{"subscription_id": sid} for sid in list_active_subscription_ids(db)]


def subscriptions_list_payload(db: Session) -> dict[str, Any]:
    """API payload for GET /resources/subscriptions."""
    default_sid = get_default_subscription_id(db)
    subs = list_subscriptions_db(db)
    if default_sid:
        for sub in subs:
            sub["isDefault"] = sub.get("subscriptionId") == default_sid
    return {
        "subscriptions": subs,
        "default_subscription_id": default_sid,
    }


def list_subscriptions_db(db: Session) -> list[dict[str, Any]]:
    """Return subscriptions for the UI — cache first, then inferred from synced data."""
    rows = db.query(SubscriptionCache).order_by(SubscriptionCache.display_name).all()
    if rows:
        return [_from_cache_row(r) for r in rows]

    sub_ids = registered_subscription_ids(db)
    if not sub_ids:
        return []

    return sorted(
        [
            {
                "subscriptionId": sid,
                "displayName": sid,
                "state": "Synced",
                "tenantId": None,
            }
            for sid in sub_ids
        ],
        key=lambda item: item["displayName"].lower(),
    )


def upsert_subscription_cache(db: Session, sub: dict[str, Any]) -> None:
    normalized = normalize_arm_subscription(sub)
    if not normalized:
        return
    sid = normalized["subscriptionId"]
    row = db.query(SubscriptionCache).filter(SubscriptionCache.subscription_id == sid).first()
    payload = json.dumps(sub)
    if row:
        row.display_name = normalized["displayName"]
        row.state = normalized["state"]
        row.tenant_id = normalized.get("tenantId")
        row.raw_json = payload
    else:
        db.add(
            SubscriptionCache(
                subscription_id=sid,
                display_name=normalized["displayName"],
                state=normalized["state"],
                tenant_id=normalized.get("tenantId"),
                raw_json=payload,
            )
        )
    invalidate_registered_subscription_ids_cache()


def ensure_subscription_cache_row(
    db: Session,
    subscription_id: str,
    *,
    display_name: str | None = None,
    state: str = "Enabled",
) -> None:
    sid = subscription_id.strip().lower()
    if not sid:
        return
    row = db.query(SubscriptionCache).filter(SubscriptionCache.subscription_id == sid).first()
    if row:
        if display_name and (not row.display_name or row.display_name == row.subscription_id):
            row.display_name = display_name
        return
    db.add(
        SubscriptionCache(
            subscription_id=sid,
            display_name=display_name or sid,
            state=state,
            tenant_id=None,
            raw_json="{}",
        )
    )
    invalidate_registered_subscription_ids_cache()


def sync_subscription_catalog(db: Session) -> int:
    """Pull all accessible Azure subscriptions into subscription_cache."""
    from app.auth import arm_auth_context, get_token

    with arm_auth_context(db=db, token=get_token(db)):
        client = AzureResourcesClient(db=db)
        subs = client.list_subscriptions()
    count = 0
    for sub in subs:
        upsert_subscription_cache(db, sub)
        count += 1
    db.commit()
    invalidate_registered_subscription_ids_cache()
    log.info("subscription_catalog_synced", count=count)
    return count

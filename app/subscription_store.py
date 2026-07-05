"""Subscription list — DB cache with fallbacks from synced operational data."""
from __future__ import annotations

import json
import structlog
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


def _default_subscription_from_settings(db: Session) -> str | None:
    try:
        from app.services.system_settings import get_effective_config

        cfg = get_effective_config(db, "azure")
        sid = (cfg.get("default_subscription_id") or "").strip().lower()
        return sid or None
    except Exception:
        return None


def list_subscriptions_db(db: Session) -> list[dict[str, Any]]:
    """Return subscriptions for the UI — cache first, then inferred from synced data."""
    rows = db.query(SubscriptionCache).order_by(SubscriptionCache.display_name).all()
    if rows:
        return [_from_cache_row(r) for r in rows]

    sub_ids = _distinct_subscription_ids(db)
    default_sid = _default_subscription_from_settings(db)
    if default_sid:
        sub_ids.add(default_sid)

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
    log.info("subscription_catalog_synced", count=count)
    return count

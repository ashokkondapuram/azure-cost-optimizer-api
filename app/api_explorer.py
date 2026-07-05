"""Context for the in-app API explorer (Swagger UI)."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.azure_token_cache import get_token_cache_status

log = structlog.get_logger(__name__)


def resolve_explorer_subscription_id(db: Session) -> dict[str, Any] | None:
    """Resolve subscription_id from settings, cache, or managed-identity ARM access."""
    from app.services.system_settings import get_effective_config
    from app.subscription_store import (
        _default_subscription_from_settings,
        list_subscriptions_db,
        normalize_arm_subscription,
    )

    azure_cfg = get_effective_config(db, "azure")
    auth_mode = (azure_cfg.get("auth_mode") or "managed_identity").strip()

    default_sid = _default_subscription_from_settings(db)
    cached = list_subscriptions_db(db)

    if default_sid:
        match = next((s for s in cached if s["subscriptionId"] == default_sid), None)
        return {
            "subscription_id": default_sid,
            "display_name": (match or {}).get("displayName") or default_sid,
            "source": "default_subscription_id",
            "auth_mode": auth_mode,
        }

    if cached:
        first = cached[0]
        return {
            "subscription_id": first["subscriptionId"],
            "display_name": first.get("displayName") or first["subscriptionId"],
            "source": "subscription_cache",
            "auth_mode": auth_mode,
        }

    try:
        from app.azure_resources import AzureResourcesClient
        from app.auth import arm_auth_context, get_token

        with arm_auth_context(db=db, token=get_token(db)):
            live = AzureResourcesClient(db=db).list_subscriptions()
        if live:
            normalized = normalize_arm_subscription(live[0])
            if normalized:
                return {
                    "subscription_id": normalized["subscriptionId"],
                    "display_name": normalized.get("displayName") or normalized["subscriptionId"],
                    "source": "managed_identity",
                    "auth_mode": auth_mode,
                }
    except Exception as exc:
        log.warning("api_explorer.subscription_resolve_failed", error=str(exc))

    return None


def build_api_explorer_context(db: Session) -> dict[str, Any]:
    """Non-secret metadata for manual API testing in the dashboard."""
    try:
        from app.auth import get_token

        get_token(db)
    except Exception as exc:
        log.warning("api_explorer.token_warm_failed", error=str(exc)[:200])

    token_cache = get_token_cache_status(db)
    subscription = resolve_explorer_subscription_id(db)
    from app.subscription_store import list_subscriptions_db

    subscriptions = list_subscriptions_db(db)

    return {
        "openapi_url": "/api/openapi.json",
        "swagger_url": "/api/docs",
        "azure_token_cache": token_cache,
        "subscription_id": subscription["subscription_id"] if subscription else None,
        "subscription": subscription,
        "subscriptions": subscriptions,
        "auth": {
            "app_session": "Session JWT (attached automatically).",
            "azure_arm": "Azure token is cached in PostgreSQL and used server-side.",
        },
        "hints": {
            "subscription_id": (
                "subscriptionId is prefilled from managed identity access "
                "or your default subscription setting."
            ),
            "azure_arm": (
                "Swagger shows management.azure.com URLs; Try it out is proxied "
                "through this app with the cached Azure token."
            ),
            "cost_management": (
                "Cost Management endpoints use /api/costs/* and call this app directly "
                "with your session JWT."
            ),
        },
    }

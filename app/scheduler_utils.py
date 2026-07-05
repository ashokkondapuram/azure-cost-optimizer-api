"""Shared utilities for scheduler and sync workers."""
from __future__ import annotations

import os
from sqlalchemy.orm import Session


def env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def list_subscription_ids(db: Session) -> list[str]:
    """Return sorted unique subscription IDs known to the system."""
    from app.subscription_store import list_subscriptions_db

    subs = list_subscriptions_db(db)
    ids = sorted(
        {
            (s.get("subscriptionId") or "").strip().lower()
            for s in subs
            if s.get("subscriptionId")
        }
    )
    return [sid for sid in ids if sid]

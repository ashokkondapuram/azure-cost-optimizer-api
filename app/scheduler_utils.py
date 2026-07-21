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
    """Return subscription IDs for scheduled sync and analysis workers."""
    from app.subscription_store import list_active_subscription_ids

    return list_active_subscription_ids(db)

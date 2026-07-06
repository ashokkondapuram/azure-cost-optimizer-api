"""Notification Channels — CRUD for alert destinations.

Stores channel definitions in the system_settings table under the
'notifications' category key.  If not yet configured, returns an empty list.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.services.system_settings import get_effective_config, save_category_settings

SETTINGS_KEY = "notifications"


def list_channels(db: Session) -> list[dict]:
    cfg = get_effective_config(db, SETTINGS_KEY)
    return cfg.get("channels") or []


def add_channel(db: Session, channel: dict) -> dict:
    cfg = get_effective_config(db, SETTINGS_KEY)
    channels: list[dict] = cfg.get("channels") or []
    channel["id"] = str(uuid.uuid4())
    channels.append(channel)
    save_category_settings(db, SETTINGS_KEY, {"channels": channels})
    return channel


def update_channel(db: Session, channel_id: str, updates: dict) -> dict | None:
    cfg = get_effective_config(db, SETTINGS_KEY)
    channels: list[dict] = cfg.get("channels") or []
    for ch in channels:
        if ch.get("id") == channel_id:
            ch.update(updates)
            ch["id"] = channel_id  # ensure id is not overwritten
            save_category_settings(db, SETTINGS_KEY, {"channels": channels})
            return ch
    return None


def delete_channel(db: Session, channel_id: str) -> bool:
    cfg = get_effective_config(db, SETTINGS_KEY)
    channels: list[dict] = cfg.get("channels") or []
    new = [ch for ch in channels if ch.get("id") != channel_id]
    if len(new) == len(channels):
        return False
    save_category_settings(db, SETTINGS_KEY, {"channels": new})
    return True


def get_notification_summary(db: Session) -> dict[str, Any]:
    channels = list_channels(db)
    return {
        "total": len(channels),
        "enabled": sum(1 for c in channels if c.get("enabled", True)),
        "types": list({c.get("type", "unknown") for c in channels}),
        "channels": channels,
    }

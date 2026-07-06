"""Notification Channels — lightweight in-process store for alert channel
configuration (webhook, email, Teams, Slack).

Channels are persisted to the ``system_settings`` table under
category='notifications'.  The entire channel list is stored as a JSON
blob in the ``config_json`` column of that single row.

Schema (from models.py SystemSetting):
  id          — UUID primary key
  category    — UNIQUE string key (we use 'notifications')
  config_json — JSON text blob
  updated_at  — auto-updated timestamp

Public API (used by routes_advanced.py)
---------------------------------------
add_channel(db, payload)              → dict
update_channel(db, channel_id, patch) → dict | None
delete_channel(db, channel_id)        → bool
get_notification_summary(db)          → dict

Aliases also exported for direct use:
create_notification_channel, delete_notification_channel, list_notification_channels
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

_CATEGORY = "notifications"


# ── internal helpers ────────────────────────────────────────────────────────────

def _load_channels(db: Session) -> list[dict]:
    """Load the channels list from system_settings."""
    from sqlalchemy import text
    try:
        row = db.execute(
            text("SELECT config_json FROM system_settings WHERE category = :c"),
            {"c": _CATEGORY},
        ).fetchone()
        if row and row[0]:
            data = json.loads(row[0])
            # config_json stores {"channels": [...]}
            return data.get("channels", []) if isinstance(data, dict) else []
    except Exception:
        pass
    return []


def _save_channels(db: Session, channels: list[dict]) -> None:
    """Upsert the channels list in system_settings."""
    from sqlalchemy import text
    raw = json.dumps({"channels": channels})
    existing = db.execute(
        text("SELECT id FROM system_settings WHERE category = :c"),
        {"c": _CATEGORY},
    ).fetchone()
    if existing:
        db.execute(
            text("UPDATE system_settings SET config_json = :v, updated_at = CURRENT_TIMESTAMP WHERE category = :c"),
            {"v": raw, "c": _CATEGORY},
        )
    else:
        db.execute(
            text(
                "INSERT INTO system_settings (id, category, config_json) "
                "VALUES (:id, :c, :v)"
            ),
            {"id": str(uuid.uuid4()), "c": _CATEGORY, "v": raw},
        )
    db.commit()


# ── core CRUD ────────────────────────────────────────────────────────────────────

def list_notification_channels(db: Session) -> dict[str, Any]:
    channels = _load_channels(db)
    return {"channels": channels, "count": len(channels)}


def create_notification_channel(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Append a new channel and return it."""
    channel_type = (payload.get("type") or "").strip().lower()
    if channel_type not in {"webhook", "email", "teams", "slack"}:
        raise ValueError(f"Unsupported channel type: {channel_type!r}")
    channel: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "type": channel_type,
        "name": (payload.get("name") or channel_type).strip(),
        "destination": payload.get("destination", ""),
        "enabled": bool(payload.get("enabled", True)),
        "events": payload.get("events") or ["anomaly", "high_severity_finding"],
        "config": payload.get("config") or {},
    }
    channels = _load_channels(db)
    channels.append(channel)
    _save_channels(db, channels)
    return channel


def update_notification_channel(
    db: Session,
    channel_id: str,
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    """Patch a channel's fields by ID.  Returns the updated channel or None."""
    channels = _load_channels(db)
    for channel in channels:
        if channel.get("id") == channel_id:
            for key, value in patch.items():
                channel[key] = value
            _save_channels(db, channels)
            return channel
    return None


def delete_notification_channel(db: Session, channel_id: str) -> bool:
    """Remove a channel by ID.  Returns True if found and deleted."""
    channels = _load_channels(db)
    new_channels = [c for c in channels if c.get("id") != channel_id]
    if len(new_channels) == len(channels):
        return False
    _save_channels(db, new_channels)
    return True


# ── aliases expected by routes_advanced.py ──────────────────────────────────────

def add_channel(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    return create_notification_channel(db, payload)


def update_channel(
    db: Session,
    channel_id: str,
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    return update_notification_channel(db, channel_id, patch)


def delete_channel(db: Session, channel_id: str) -> bool:
    return delete_notification_channel(db, channel_id)


def get_notification_summary(db: Session) -> dict[str, Any]:
    """Return channels list plus aggregated stats."""
    channels = _load_channels(db)
    enabled = [c for c in channels if c.get("enabled", True)]
    types: dict[str, int] = {}
    for ch in channels:
        t = ch.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
    return {
        "channels": channels,
        "count": len(channels),
        "enabled_count": len(enabled),
        "disabled_count": len(channels) - len(enabled),
        "types": types,
    }

"""Notification Channels — lightweight in-process store for alert channel
configuration (webhook, email, Teams).

Channels are persisted to the ``system_settings`` table under the
``notifications`` category so they survive restarts without requiring a
new DB migration.  Each channel is stored as a JSON blob in the value
field.

Public API (used by routes_advanced.py)
---------------------------------------
add_channel(db, payload)              → dict   (create)
update_channel(db, channel_id, patch) → dict | None  (update)
delete_channel(db, channel_id)        → bool  (delete)
get_notification_summary(db)          → dict  (list + stats)

Also exported for direct use:
create_notification_channel, delete_notification_channel, list_notification_channels
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

_CATEGORY = "notifications"
_KEY = "channels"


# ── internal helpers ───────────────────────────────────────────────────────────────

def _load_channels(db: Session) -> list[dict]:
    """Load the channels list from system_settings."""
    from sqlalchemy import text
    try:
        row = db.execute(
            text("SELECT value FROM system_settings WHERE category = :c AND key = :k"),
            {"c": _CATEGORY, "k": _KEY},
        ).fetchone()
        if row and row[0]:
            return json.loads(row[0])
    except Exception:
        pass
    return []


def _save_channels(db: Session, channels: list[dict]) -> None:
    """Upsert the channels list in system_settings."""
    from sqlalchemy import text
    raw = json.dumps(channels)
    existing = db.execute(
        text("SELECT id FROM system_settings WHERE category = :c AND key = :k"),
        {"c": _CATEGORY, "k": _KEY},
    ).fetchone()
    if existing:
        db.execute(
            text("UPDATE system_settings SET value = :v WHERE category = :c AND key = :k"),
            {"v": raw, "c": _CATEGORY, "k": _KEY},
        )
    else:
        db.execute(
            text(
                "INSERT INTO system_settings (id, category, key, value, is_secret) "
                "VALUES (:id, :c, :k, :v, false)"
            ),
            {"id": str(uuid.uuid4()), "c": _CATEGORY, "k": _KEY, "v": raw},
        )
    db.commit()


# ── core CRUD ──────────────────────────────────────────────────────────────────────

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


# ── aliases expected by routes_advanced.py ─────────────────────────────────────────

def add_channel(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Alias for create_notification_channel (used by routes_advanced)."""
    return create_notification_channel(db, payload)


def update_channel(
    db: Session,
    channel_id: str,
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    """Alias for update_notification_channel (used by routes_advanced)."""
    return update_notification_channel(db, channel_id, patch)


def delete_channel(db: Session, channel_id: str) -> bool:
    """Alias for delete_notification_channel (used by routes_advanced)."""
    return delete_notification_channel(db, channel_id)


def get_notification_summary(db: Session) -> dict[str, Any]:
    """Return channels list plus aggregated stats (used by routes_advanced)."""
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

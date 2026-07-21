"""Shared helpers used across optimization and inventory modules."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def norm_arm_id(value: str | None) -> str:
    return (value or "").strip().lower()


def parse_tags_json(tags_json: Any) -> dict[str, str]:
    if not tags_json:
        return {}
    if isinstance(tags_json, dict):
        return {str(k).lower(): str(v).lower() for k, v in tags_json.items()}
    try:
        raw = json.loads(tags_json)
        return {str(k).lower(): str(v).lower() for k, v in raw.items()} if isinstance(raw, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def today_iso() -> str:
    return date.today().isoformat()


def json_field(value: Any, *, default: str = "{}") -> str:
    """Serialize a value for JSONText columns."""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return json.dumps(value)

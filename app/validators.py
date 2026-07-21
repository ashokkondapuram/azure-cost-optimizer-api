"""Input validators for API query/path parameters."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from fastapi import HTTPException

DEFAULT_METRIC_TIMESPAN = "P7D"
_SUPPORTED_METRIC_TIMESPANS = frozenset({"P1D", "P7D", "P14D", "P30D", "P90D"})

SUBSCRIPTION_ID_RE = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
)
RESOURCE_GROUP_RE = re.compile(r'^[A-Za-z0-9_.()-]{1,90}$')
FINDING_STATUS = {'open', 'acknowledged', 'resolved', 'ignored'}


def validate_subscription_id(subscription_id: str) -> str:
    value = (subscription_id or '').strip()
    if not SUBSCRIPTION_ID_RE.match(value):
        raise HTTPException(status_code=422, detail='Invalid subscription_id format')
    return value.lower()


def validate_optional_subscription_id(subscription_id: str | None) -> str | None:
    if subscription_id is None:
        return None
    return validate_subscription_id(subscription_id)


def require_subscription_id(subscription_id: str | None) -> str:
    if subscription_id is None or not str(subscription_id).strip():
        raise HTTPException(status_code=400, detail="subscription_id is required")
    return validate_subscription_id(subscription_id)


def known_subscription_ids(db) -> set[str]:
    """Subscriptions registered for API access (admin-added cache + synced data)."""
    from app.subscription_store import registered_subscription_ids

    return registered_subscription_ids(db)


def _subscription_has_synced_inventory(db, subscription_id: str) -> bool:
    """Cheap single-table check for legacy synced subscriptions without a cache row."""
    from app.models import ResourceSnapshot

    return (
        db.query(ResourceSnapshot.id)
        .filter(ResourceSnapshot.subscription_id == subscription_id)
        .limit(1)
        .first()
        is not None
    )


def subscription_is_registered(db, subscription_id: str) -> bool:
    """True when subscription is registered for this deployment."""
    try:
        sub = validate_subscription_id(subscription_id)
    except HTTPException:
        return False
    from app.subscription_store import is_subscription_registered

    return is_subscription_registered(db, sub)


def ensure_subscription_known(db, subscription_id: str) -> str:
    """Reject subscription IDs that are not registered in this deployment."""
    sub = validate_subscription_id(subscription_id)
    if subscription_is_registered(db, sub):
        return sub
    if _subscription_has_synced_inventory(db, sub):
        return sub
    raise HTTPException(status_code=404, detail="Subscription not found")


def ensure_job_accessible(db, job, subscription_id: str | None) -> None:
    """Ensure analysis job belongs to the requested subscription."""
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not subscription_id:
        raise HTTPException(status_code=400, detail="subscription_id is required")
    sub = ensure_subscription_known(db, subscription_id)
    if (job.subscription_id or "").lower() != sub:
        raise HTTPException(status_code=404, detail="Job not found")


def ensure_run_accessible(db, run, subscription_id: str | None) -> None:
    """Ensure optimization run belongs to the requested subscription."""
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if not subscription_id:
        raise HTTPException(status_code=400, detail="subscription_id is required")
    sub = ensure_subscription_known(db, subscription_id)
    if (run.subscription_id or "").lower() != sub:
        raise HTTPException(status_code=404, detail="Run not found")


def validate_resource_group(resource_group: str) -> str:
    value = (resource_group or '').strip()
    if not RESOURCE_GROUP_RE.match(value):
        raise HTTPException(status_code=422, detail='Invalid resource_group format')
    return value


def validate_finding_status(status: str) -> str:
    value = (status or '').strip().lower()
    if value not in FINDING_STATUS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Allowed: {', '.join(sorted(FINDING_STATUS))}",
        )
    return value


def coerce_dict(value: Any, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize JSON/object fields before Pydantic dict validation."""
    fallback = dict(default or {})
    if value is None:
        return fallback
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate or candidate == "[object Object]":
            return fallback
        if candidate.startswith("{"):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                return fallback
            return parsed if isinstance(parsed, dict) else fallback
    return fallback


def coerce_str_dict(value: Any) -> dict[str, str]:
    """Coerce tag maps and other string dictionaries."""
    raw = coerce_dict(value)
    out: dict[str, str] = {}
    for key, item in raw.items():
        if item is None:
            continue
        out[str(key)] = str(item)
    return out


def coerce_nested_dict_map(value: Any) -> dict[str, dict[str, Any]]:
    """Coerce rule override maps; drop non-dict inner entries."""
    raw = coerce_dict(value)
    out: dict[str, dict[str, Any]] = {}
    for key, item in raw.items():
        if isinstance(item, dict):
            out[str(key)] = item
            continue
        if isinstance(item, str) and item.strip().startswith("{"):
            try:
                parsed = json.loads(item)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                out[str(key)] = parsed
    return out


def coerce_bool_dict_map(value: Any) -> dict[str, dict[str, bool]]:
    """Coerce nested role/panel visibility maps."""
    raw = coerce_dict(value)
    out: dict[str, dict[str, bool]] = {}
    for role, panels in raw.items():
        panel_map = coerce_dict(panels)
        if not panel_map:
            continue
        out[str(role)] = {str(panel): bool(enabled) for panel, enabled in panel_map.items()}
    return out


def coerce_list(value: Any, *, default: list[Any] | None = None) -> list[Any]:
    """Normalize list fields when clients send null or a single object."""
    fallback = list(default or [])
    if value is None:
        return fallback
    if isinstance(value, list):
        return value
    return fallback


def coerce_metric_timespan(value: Any, *, default: str = DEFAULT_METRIC_TIMESPAN) -> str:
    """Normalize Azure Monitor lookback codes from strings or UI/localStorage objects."""
    fallback = (default or DEFAULT_METRIC_TIMESPAN).strip().upper()
    if fallback not in _SUPPORTED_METRIC_TIMESPANS:
        fallback = DEFAULT_METRIC_TIMESPAN

    if isinstance(value, str):
        candidate = value.strip()
        if not candidate or candidate == "[object Object]":
            return fallback
        upper = candidate.upper()
        if upper in _SUPPORTED_METRIC_TIMESPANS:
            return upper
        if candidate.startswith("{"):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return coerce_metric_timespan(parsed, default=fallback)
        return fallback

    if isinstance(value, dict):
        nested = value.get("value") or value.get("timespan") or value.get("id")
        if isinstance(nested, str):
            candidate = nested.strip().upper()
            if candidate in _SUPPORTED_METRIC_TIMESPANS:
                return candidate
        return fallback

    return fallback


def new_uuid() -> str:
    return str(uuid.uuid4())

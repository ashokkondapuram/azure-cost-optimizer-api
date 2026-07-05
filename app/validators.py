"""Input validators for API query/path parameters."""
from __future__ import annotations

import re
import uuid

from fastapi import HTTPException

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
    """Subscriptions with synced operational data (not catalog-only cache rows)."""
    from app.subscription_store import (
        _default_subscription_from_settings,
        _distinct_subscription_ids,
    )

    known = _distinct_subscription_ids(db)
    default_sid = _default_subscription_from_settings(db)
    if default_sid:
        known.add(default_sid)
    return known


def ensure_subscription_known(db, subscription_id: str) -> str:
    """Reject subscription IDs that are not registered in this deployment."""
    sub = validate_subscription_id(subscription_id)
    if sub not in known_subscription_ids(db):
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


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


def new_uuid() -> str:
    return str(uuid.uuid4())

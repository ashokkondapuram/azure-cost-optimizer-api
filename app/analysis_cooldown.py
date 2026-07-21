"""Limit full optimization analysis to once per rolling day per subscription."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AnalysisJob
from app.optimizer.component_map import (
    ANALYSIS_BATCHES,
    filter_known_components,
    resolve_batches,
)


def full_analysis_cooldown_hours() -> float:
    return max(0.0, float(os.getenv("FULL_ANALYSIS_COOLDOWN_HOURS", "24")))


def cooldown_disabled() -> bool:
    return full_analysis_cooldown_hours() <= 0


def is_scoped_analysis(
    scope_components: list[str] | None,
    scope_resource_types: list[str] | None,
) -> bool:
    if scope_resource_types:
        return True
    known = filter_known_components(scope_components)
    if not known:
        return False
    return len(resolve_batches(known)) < len(ANALYSIS_BATCHES)


def is_full_analysis_request(
    scope_components: list[str] | None,
    scope_resource_types: list[str] | None,
    *,
    skip_monitor_fetch: bool = False,
) -> bool:
    if skip_monitor_fetch:
        return False
    if scope_resource_types:
        return False
    return not is_scoped_analysis(scope_components, None)


def _job_scope(job: AnalysisJob) -> tuple[list[str] | None, list[str], bool]:
    try:
        components_meta = json.loads(job.components_json or "[]")
    except Exception:
        components_meta = []

    scope_resource_types: list[str] = []
    analysis_scope_components: list[str] = []
    skip_monitor_fetch = False
    display_labels = frozenset({"Full analysis", "Rule refresh"})
    valid_component_names = {b["component"] for b in ANALYSIS_BATCHES}

    for entry in components_meta:
        skip_monitor_fetch = skip_monitor_fetch or bool(entry.get("skip_monitor_fetch"))
        for ct in entry.get("scope_resource_types") or []:
            if ct and ct not in scope_resource_types:
                scope_resource_types.append(ct)
        for comp in filter_known_components(entry.get("analysis_scope_components") or []):
            if comp not in analysis_scope_components:
                analysis_scope_components.append(comp)

    if not analysis_scope_components:
        for entry in components_meta:
            label = (entry.get("component") or "").strip()
            if label and label not in display_labels and label in valid_component_names:
                analysis_scope_components.append(label)

    if skip_monitor_fetch:
        return None, [], True

    return (analysis_scope_components or None), scope_resource_types, False


def job_is_full_analysis(job: AnalysisJob) -> bool:
    scope_components, scope_resource_types, skip_monitor_fetch = _job_scope(job)
    return is_full_analysis_request(
        scope_components,
        scope_resource_types,
        skip_monitor_fetch=skip_monitor_fetch,
    )


def _as_utc(when: datetime | None) -> datetime | None:
    if when is None:
        return None
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def last_completed_full_analysis(db: Session, subscription_id: str) -> AnalysisJob | None:
    """Return the most-recent completed full-analysis job for a subscription.

    Candidates are fetched newest-first in a single DB query.  Only the 25
    most-recent completed jobs are inspected (Python-side) to resolve the
    full-analysis flag from components_json, keeping the scan cheap.
    """
    sub = subscription_id.strip().lower()
    rows = (
        db.query(AnalysisJob)
        .filter(
            func.lower(AnalysisJob.subscription_id) == sub,
            AnalysisJob.status == "completed",
        )
        .order_by(AnalysisJob.completed_at.desc())
        .limit(25)
        .all()
    )
    for row in rows:
        if job_is_full_analysis(row):
            return row
    return None


def _last_completed_full_analysis_bulk(
    db: Session,
    subscription_ids: list[str],
) -> dict[str, AnalysisJob]:
    """Fetch the most-recent completed full-analysis job for each subscription
    in a single DB round-trip.

    Returns a mapping of normalised subscription_id → AnalysisJob (only
    subscriptions that have at least one completed full-analysis job are
    represented).
    """
    if not subscription_ids:
        return {}
    normalised = [s.strip().lower() for s in subscription_ids]
    rows = (
        db.query(AnalysisJob)
        .filter(
            func.lower(AnalysisJob.subscription_id).in_(normalised),
            AnalysisJob.status == "completed",
        )
        .order_by(AnalysisJob.completed_at.desc())
        .limit(25 * len(normalised))
        .all()
    )
    best: dict[str, AnalysisJob] = {}
    for row in rows:
        sub = (row.subscription_id or "").strip().lower()
        if sub in best:
            continue
        if job_is_full_analysis(row):
            best[sub] = row
    return best


def full_analysis_cooldown_status(db: Session, subscription_id: str) -> dict[str, Any]:
    hours = full_analysis_cooldown_hours()
    if cooldown_disabled():
        return {
            "enabled": False,
            "cooldown_hours": hours,
            "can_run": True,
            "last_run_at": None,
            "last_job_id": None,
            "next_allowed_at": None,
        }

    last_job = last_completed_full_analysis(db, subscription_id)
    last_at = _as_utc(last_job.completed_at) if last_job else None
    now = datetime.now(timezone.utc)
    cooldown = timedelta(hours=hours)
    next_allowed = (last_at + cooldown) if last_at else None
    can_run = last_at is None or now >= next_allowed

    return {
        "enabled": True,
        "cooldown_hours": hours,
        "can_run": can_run,
        "last_run_at": last_at.isoformat() if last_at else None,
        "last_job_id": last_job.id if last_job else None,
        "next_allowed_at": next_allowed.isoformat() if next_allowed and not can_run else None,
    }


def assert_full_analysis_allowed(
    db: Session,
    subscription_id: str,
    *,
    scope_components: list[str] | None,
    scope_resource_types: list[str] | None,
    skip_monitor_fetch: bool = False,
) -> None:
    """Raise HTTP 429 (with Retry-After) when the cooldown is still active."""
    if not is_full_analysis_request(
        scope_components,
        scope_resource_types,
        skip_monitor_fetch=skip_monitor_fetch,
    ):
        return

    status = full_analysis_cooldown_status(db, subscription_id)
    if status["can_run"]:
        return

    last_run = status.get("last_run_at")
    next_allowed = status.get("next_allowed_at")
    hours = int(status.get("cooldown_hours") or 24)

    # Calculate remaining seconds for Retry-After header.
    retry_after: int | None = None
    if next_allowed:
        try:
            delta = datetime.fromisoformat(next_allowed) - datetime.now(timezone.utc)
            retry_after = max(1, int(delta.total_seconds()))
        except Exception:
            pass

    detail = (
        f"Full analysis already ran within the last {hours} hours. "
        f"Last run: {last_run}. "
        f"Next full analysis available after {next_allowed}. "
        f"Scoped analysis or rule refresh can still run."
    )
    headers: dict[str, str] = {}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    raise HTTPException(status_code=429, detail=detail, headers=headers)


def batch_assert_full_analysis_allowed(
    db: Session,
    subscription_ids: list[str],
    *,
    scope_components: list[str] | None,
    scope_resource_types: list[str] | None,
    skip_monitor_fetch: bool = False,
) -> dict[str, str]:
    """Check cooldown for multiple subscriptions in a single DB query.

    Returns a mapping of subscription_id → error message for every subscription
    that is still in cooldown.  Subscriptions that may proceed are absent from
    the returned dict.
    """
    if not is_full_analysis_request(
        scope_components,
        scope_resource_types,
        skip_monitor_fetch=skip_monitor_fetch,
    ):
        return {}
    if cooldown_disabled():
        return {}

    hours = full_analysis_cooldown_hours()
    cooldown = timedelta(hours=hours)
    now = datetime.now(timezone.utc)

    last_jobs = _last_completed_full_analysis_bulk(db, subscription_ids)
    blocked: dict[str, str] = {}
    for sub in subscription_ids:
        key = sub.strip().lower()
        job = last_jobs.get(key)
        if job is None:
            continue
        last_at = _as_utc(job.completed_at)
        if last_at is None:
            continue
        next_allowed = last_at + cooldown
        if now < next_allowed:
            blocked[sub] = (
                f"Full analysis already ran within the last {int(hours)} hours. "
                f"Next allowed after {next_allowed.isoformat()}."
            )
    return blocked

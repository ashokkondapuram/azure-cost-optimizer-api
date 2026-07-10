"""Scheduler status — expose sync job run history and health."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CostSyncRun, ComponentSyncState

router = APIRouter(prefix="/scheduler", tags=["Scheduler Status"])

_STALE_HOURS = 25  # A job not run in >25h is considered stale


def _age_hours(ts: datetime | None) -> float | None:
    if not ts:
        return None
    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return round((now - ts).total_seconds() / 3600, 1)


def _run_health(last_run_at: datetime | None, last_error: str | None) -> str:
    if last_error:
        return "error"
    age = _age_hours(last_run_at)
    if age is None:
        return "never_run"
    if age > _STALE_HOURS:
        return "stale"
    return "healthy"


@router.get("/cost-sync/{subscription_id}")
def cost_sync_history(
    subscription_id: str,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """Return the most recent cost sync run history for a subscription."""
    sub = (subscription_id or "").strip().lower()
    runs = (
        db.query(CostSyncRun)
        .filter(CostSyncRun.subscription_id == sub)
        .order_by(desc(CostSyncRun.synced_at))
        .limit(limit)
        .all()
    )
    if not runs:
        return {
            "subscription_id": subscription_id,
            "runs": [],
            "health": "never_run",
            "message": "No cost sync runs found.",
        }

    latest = runs[0]
    history = [
        {
            "run_id": r.id,
            "month": r.month,
            "synced_at": r.synced_at.isoformat() if r.synced_at else None,
            "mtd_start": r.mtd_start,
            "mtd_end": r.mtd_end,
            "total_billing": r.total_billing,
            "billing_currency": r.billing_currency,
            "age_hours": _age_hours(r.synced_at),
        }
        for r in runs
    ]

    return {
        "subscription_id": subscription_id,
        "health": _run_health(latest.synced_at, getattr(latest, "error_message", None)),
        "last_synced_at": latest.synced_at.isoformat() if latest.synced_at else None,
        "age_hours": _age_hours(latest.synced_at),
        "runs": history,
    }


@router.get("/db-sync/{subscription_id}")
def db_sync_history(
    subscription_id: str,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """Return the most recent resource DB sync run history."""
    sub = (subscription_id or "").strip().lower()
    try:
        runs = (
            db.query(ComponentSyncState)
            .order_by(desc(ComponentSyncState.synced_at))
            .limit(limit)
            .all()
        )
    except Exception:
        runs = []

    if not runs:
        return {
            "subscription_id": subscription_id,
            "runs": [],
            "health": "never_run",
            "message": "No DB sync runs found.",
        }

    latest = runs[0]
    history = [
        {
            "component": r.component,
            "synced_at": r.synced_at.isoformat() if r.synced_at else None,
            "last_status": r.last_status,
            "age_hours": _age_hours(r.synced_at),
        }
        for r in runs
    ]
    return {
        "subscription_id": subscription_id,
        "health": _run_health(latest.synced_at, getattr(latest, "error_message", None)),
        "last_synced_at": latest.synced_at.isoformat() if latest.synced_at else None,
        "age_hours": _age_hours(latest.synced_at),
        "runs": history,
    }


@router.get("/health-summary/{subscription_id}")
def scheduler_health_summary(
    subscription_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Return an overall scheduler health summary across all job types."""
    sub = (subscription_id or "").strip().lower()

    cost_run = (
        db.query(CostSyncRun)
        .filter(CostSyncRun.subscription_id == sub)
        .order_by(desc(CostSyncRun.synced_at))
        .first()
    )

    jobs: list[dict] = [
        {
            "job": "cost_sync",
            "last_run": cost_run.synced_at.isoformat() if cost_run and cost_run.synced_at else None,
            "age_hours": _age_hours(cost_run.synced_at if cost_run else None),
            "health": _run_health(
                cost_run.synced_at if cost_run else None,
                getattr(cost_run, "error_message", None) if cost_run else None,
            ),
        },
    ]

    all_healthy = all(j["health"] == "healthy" for j in jobs)
    any_error = any(j["health"] == "error" for j in jobs)
    overall = "healthy" if all_healthy else ("error" if any_error else "degraded")

    return {
        "subscription_id": subscription_id,
        "overall_health": overall,
        "jobs": jobs,
    }

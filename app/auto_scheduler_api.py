"""Auto-Scheduler API — expose scheduled sync/analysis job config and history.

Reads from AnalysisJob and OptimizationRun to surface recent scheduled
activity and the current scheduler state.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import AnalysisJob, OptimizationRun


def get_scheduler_status(db: Session, subscription_id: str | None = None) -> dict[str, Any]:
    """Return recent jobs and run stats for the auto-scheduler page."""
    job_q = db.query(AnalysisJob).order_by(AnalysisJob.created_at.desc()).limit(20)
    if subscription_id:
        job_q = job_q.filter(AnalysisJob.subscription_id == subscription_id)
    jobs = job_q.all()

    run_q = db.query(OptimizationRun).order_by(OptimizationRun.created_at.desc()).limit(10)
    if subscription_id:
        run_q = run_q.filter(OptimizationRun.subscription_id == subscription_id)
    runs = run_q.all()

    def _job(j: AnalysisJob) -> dict:
        return {
            "id": str(j.id),
            "status": j.status,
            "subscription_id": j.subscription_id,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "error": j.error_message,
        }

    def _run(r: OptimizationRun) -> dict:
        return {
            "id": str(r.id),
            "subscription_id": r.subscription_id,
            "finding_count": r.finding_count,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    pending = sum(1 for j in jobs if j.status in {"pending", "running"})
    failed = sum(1 for j in jobs if j.status == "failed")

    return {
        "summary": {
            "recent_jobs": len(jobs),
            "pending": pending,
            "failed": failed,
            "last_run": runs[0].created_at.isoformat() if runs else None,
        },
        "jobs": [_job(j) for j in jobs],
        "runs": [_run(r) for r in runs],
    }

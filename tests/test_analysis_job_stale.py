"""Tests for stale analysis job expiry."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.batch_analyzer import (
    cancel_analysis_job,
    create_analysis_job,
    expire_stale_analysis_jobs,
    has_active_analysis_job,
    serialize_job,
)
from app.models import AnalysisJob


def _insert_running_job(db, sub: str, *, hours_ago: float = 5.0) -> AnalysisJob:
    started = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    job = AnalysisJob(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        profile="default",
        engine_version="extended",
        status="running",
        progress_pct=10,
        total_batches=1,
        completed_batches=0,
        components_json='[{"component": "Virtual Machines", "status": "pending"}]',
        started_at=started,
        created_at=started,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_expire_stale_running_job():
    from app.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        sub = f"stale-sub-{uuid.uuid4().hex[:8]}"
        job = _insert_running_job(db, sub, hours_ago=5.0)
        expired = expire_stale_analysis_jobs(db, subscription_id=sub)
        assert job.id in expired
        refreshed = db.query(AnalysisJob).filter(AnalysisJob.id == job.id).first()
        assert refreshed.status == "failed"
        assert "time limit" in (refreshed.error_message or "").lower()
    finally:
        db.close()


def test_has_active_analysis_job_clears_stale_before_check():
    from app.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        sub = f"stale-sub-{uuid.uuid4().hex[:8]}"
        _insert_running_job(db, sub, hours_ago=6.0)
        assert has_active_analysis_job(db, sub) is False
    finally:
        db.close()


def test_cancel_analysis_job_marks_failed():
    from app.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        sub = f"cancel-sub-{uuid.uuid4().hex[:8]}"
        job = create_analysis_job(db, subscription_id=sub)
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        db.commit()
        cancelled = cancel_analysis_job(db, job.id, sub)
        payload = serialize_job(cancelled)
        assert payload["status"] == "failed"
        assert "cancelled" in (payload["error_message"] or "").lower()
    finally:
        db.close()

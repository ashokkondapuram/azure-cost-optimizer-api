"""Regression: batch jobs must not crash when analysis omits run_id."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.batch_analyzer import create_analysis_job, execute_batch_job
from app.database import SessionLocal, init_db
from app.models import AnalysisJob


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_execute_batch_job_tolerates_missing_run_id(db):
    sub = f"sub-run-id-{uuid.uuid4().hex[:8]}"
    job = create_analysis_job(db, subscription_id=sub, engine_version="extended")
    job_id = job.id
    db.close()

    mock_result = {
        "summary": {
            "total_findings": 0,
            "total_estimated_monthly_savings_usd": 0.0,
            "by_severity": {},
        },
        "findings": [],
        "data_source": "db",
        "analysis_trigger": "test",
    }

    with patch("app.batch_analyzer.run_db_analysis", return_value=mock_result):
        with patch("app.batch_analyzer._resolve_analysis_run_id", return_value="run-fallback-123"):
            with patch("app.optimizer.decision_engine.generate_optimization_actions", return_value={"created": 0, "updated": 0}):
                execute_batch_job(job_id)

    verify = SessionLocal()
    try:
        refreshed = verify.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        assert refreshed is not None
        assert refreshed.status == "completed"
        assert refreshed.run_id == "run-fallback-123"
    finally:
        verify.close()


def test_execute_batch_job_persists_fallback_run_id_when_missing(db):
    sub = f"sub-run-id-{uuid.uuid4().hex[:8]}"
    job = create_analysis_job(db, subscription_id=sub, engine_version="extended")
    job_id = job.id
    db.close()

    mock_result = {
        "summary": {
            "total_findings": 1,
            "total_estimated_monthly_savings_usd": 5.0,
            "by_severity": {"HIGH": 1},
        },
        "findings": [],
        "data_source": "db",
    }

    with patch("app.batch_analyzer.run_db_analysis", return_value=mock_result):
        with patch("app.analysis_persist.persist_optimization_run", return_value="run-persisted-456") as mock_persist:
            with patch("app.optimizer.decision_engine.generate_optimization_actions", return_value={"created": 0, "updated": 0}):
                execute_batch_job(job_id)

    mock_persist.assert_called_once()
    verify = SessionLocal()
    try:
        refreshed = verify.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        assert refreshed.status == "completed"
        assert refreshed.run_id == "run-persisted-456"
    finally:
        verify.close()

"""Regression: on-demand analysis must not skip when scheduled ops are disabled."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.analysis.orchestrator import run_db_analysis
from app.operations_scheduler import scheduled_pipeline_enabled
from app.pipeline.orchestrator import pipeline_enabled, run_pipeline
from app.pipeline.unified_recommendations import run_analysis_via_unified_pipeline


@pytest.fixture()
def db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_pipeline_enabled_defaults_true_when_scheduled_ops_false(monkeypatch):
    monkeypatch.delenv("ASSESSMENT_PIPELINE_ENABLED", raising=False)
    monkeypatch.setenv("SCHEDULED_OPERATIONS_ENABLED", "false")
    assert pipeline_enabled() is True


def test_pipeline_enabled_respects_explicit_false(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "false")
    assert pipeline_enabled() is False


def test_scheduled_pipeline_stays_off_when_scheduled_ops_false(monkeypatch):
    monkeypatch.delenv("SCHEDULED_PIPELINE_ENABLED", raising=False)
    monkeypatch.delenv("ASSESSMENT_PIPELINE_ENABLED", raising=False)
    monkeypatch.setenv("SCHEDULED_OPERATIONS_ENABLED", "false")
    assert scheduled_pipeline_enabled() is False


def test_run_pipeline_disabled_includes_actionable_reason(db_session, monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "false")
    sub = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    result = run_pipeline(db_session, sub)

    assert result["status"] == "disabled"
    assert result["reason"] == "assessment_pipeline_disabled"
    assert "ASSESSMENT_PIPELINE_ENABLED" in result.get("hint", "")


def test_run_analysis_via_unified_pipeline_disabled_raises_clear_error(db_session, monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "false")
    sub = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    with pytest.raises(ValueError, match="Unified analysis pipeline is disabled"):
        run_analysis_via_unified_pipeline(db_session, subscription_id=sub)


def test_run_db_analysis_falls_back_when_pipeline_disabled(db_session, monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "false")
    sub = f"sub-fallback-{uuid.uuid4().hex[:8]}"

    with patch("app.pipeline.unified_recommendations.run_analysis_via_unified_pipeline") as mock_unified:
        with patch(
            "app.analysis.orchestrator.load_inventory_from_db",
            side_effect=ValueError("legacy-path-reached"),
        ):
            with pytest.raises(ValueError, match="legacy-path-reached"):
                run_db_analysis(db_session, subscription_id=sub)

    mock_unified.assert_not_called()


def test_run_db_analysis_uses_pipeline_when_enabled(db_session, monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "true")
    sub = f"sub-pipeline-{uuid.uuid4().hex[:8]}"

    mock_pipeline_result = {
        "summary": {"total_findings": 1, "total_estimated_monthly_savings_usd": 5.0, "by_severity": {}},
        "findings": [],
        "data_source": "sub_engines",
        "run_id": "run-pipeline-456",
    }

    with patch(
        "app.pipeline.unified_recommendations.run_analysis_via_unified_pipeline",
        return_value=mock_pipeline_result,
    ) as mock_unified:
        result = run_db_analysis(db_session, subscription_id=sub)

    mock_unified.assert_called_once()
    assert result["run_id"] == "run-pipeline-456"


def test_execute_batch_job_fails_with_clear_message_when_pipeline_disabled():
    import uuid

    from app.batch_analyzer import create_analysis_job, execute_batch_job
    from app.database import SessionLocal, init_db
    from app.models import AnalysisJob

    init_db()
    db = SessionLocal()
    try:
        sub = f"sub-disabled-{uuid.uuid4().hex[:8]}"
        job = create_analysis_job(db, subscription_id=sub, engine_version="extended")
        job_id = job.id
    finally:
        db.close()

    disabled_error = (
        "Unified analysis pipeline is disabled (assessment_pipeline_disabled). "
        "Set ASSESSMENT_PIPELINE_ENABLED=true."
    )

    with patch("app.batch_analyzer.run_db_analysis", side_effect=ValueError(disabled_error)):
        execute_batch_job(job_id)

    verify = SessionLocal()
    try:
        refreshed = verify.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert "assessment_pipeline_disabled" in (refreshed.error_message or "")
    finally:
        verify.close()

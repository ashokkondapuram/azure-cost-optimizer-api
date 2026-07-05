"""Tests for full-analysis daily cooldown."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analysis_cooldown import (
    assert_full_analysis_allowed,
    full_analysis_cooldown_status,
    is_full_analysis_request,
    job_is_full_analysis,
)
from app.batch_analyzer import create_analysis_job
from app.models import AnalysisJob, Base


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _cooldown_24h(monkeypatch):
    monkeypatch.setenv("FULL_ANALYSIS_COOLDOWN_HOURS", "24")


def test_is_full_analysis_request():
    assert is_full_analysis_request(None, None) is True
    assert is_full_analysis_request(["Virtual Machines"], None) is False
    assert is_full_analysis_request(None, ["compute/vm"], skip_monitor_fetch=False) is False
    assert is_full_analysis_request(None, None, skip_monitor_fetch=True) is False


def test_job_is_full_analysis():
    full = AnalysisJob(
        id="j1",
        subscription_id="sub-1",
        components_json=json.dumps([{"component": "Full analysis", "status": "completed"}]),
    )
    scoped = AnalysisJob(
        id="j2",
        subscription_id="sub-1",
        components_json=json.dumps([{
            "component": "Virtual Machines",
            "analysis_scope_components": ["Virtual Machines"],
        }]),
    )
    assert job_is_full_analysis(full) is True
    assert job_is_full_analysis(scoped) is False


def test_full_analysis_cooldown_blocks_repeat(db_session):
    sub = f"cooldown-sub-{uuid.uuid4().hex[:8]}"
    job = create_analysis_job(db_session, subscription_id=sub)
    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.commit()

    status = full_analysis_cooldown_status(db_session, sub)
    assert status["can_run"] is False
    assert status["last_job_id"] == job.id
    assert status["next_allowed_at"] is not None

    with pytest.raises(ValueError, match="Full analysis already ran"):
        assert_full_analysis_allowed(db_session, sub, scope_components=None, scope_resource_types=None)


def test_scoped_analysis_allowed_during_cooldown(db_session):
    sub = f"scoped-sub-{uuid.uuid4().hex[:8]}"
    job = create_analysis_job(db_session, subscription_id=sub)
    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc)
    db_session.commit()

    assert_full_analysis_allowed(
        db_session,
        sub,
        scope_components=["Virtual Machines"],
        scope_resource_types=None,
    )
    scoped_job = create_analysis_job(
        db_session,
        subscription_id=sub,
        scope_components=["Virtual Machines"],
    )
    assert scoped_job.id != job.id


def test_cooldown_expired_allows_full_analysis(db_session, monkeypatch):
    monkeypatch.setenv("FULL_ANALYSIS_COOLDOWN_HOURS", "1")
    sub = f"expired-sub-{uuid.uuid4().hex[:8]}"
    job = create_analysis_job(db_session, subscription_id=sub)
    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.commit()

    status = full_analysis_cooldown_status(db_session, sub)
    assert status["can_run"] is True

    # Active-job guard still applies while first job is "completed", so a new job can start.
    new_job = create_analysis_job(db_session, subscription_id=sub)
    assert new_job.id != job.id

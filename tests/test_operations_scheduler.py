"""Tests for scheduled sync and analysis workers."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, ComponentSyncState, SubscriptionCache
from app import operations_scheduler as sched


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_scheduled_operations_default_disabled_in_development(monkeypatch):
    monkeypatch.delenv("SCHEDULED_OPERATIONS_ENABLED", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    from app.settings import get_settings

    get_settings.cache_clear()
    assert sched.scheduled_operations_enabled() is False
    get_settings.cache_clear()


def test_scheduled_operations_default_enabled_in_production(monkeypatch):
    monkeypatch.delenv("SCHEDULED_OPERATIONS_ENABLED", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    from app.settings import get_settings

    get_settings.cache_clear()
    assert sched.scheduled_operations_enabled() is True
    get_settings.cache_clear()


def test_scheduled_sync_disabled_when_component_sync_active(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SCHEDULED_SYNC_ENABLED", raising=False)
    monkeypatch.delenv("SCHEDULED_FULL_SYNC_ENABLED", raising=False)
    monkeypatch.delenv("SCHEDULED_COMPONENT_SYNC_ENABLED", raising=False)
    from app.settings import get_settings

    get_settings.cache_clear()
    assert sched.scheduled_operations_enabled() is True
    assert sched.scheduled_sync_enabled() is False
    get_settings.cache_clear()


def test_scheduled_sync_explicit_override(monkeypatch):
    monkeypatch.setenv("SCHEDULED_SYNC_ENABLED", "true")
    assert sched.scheduled_sync_enabled() is True


def test_get_scheduler_status_shows_component_mode(monkeypatch):
    from app.component_sync_worker import _last_component_sync_at

    _last_component_sync_at.clear()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SCHEDULED_SYNC_ENABLED", raising=False)
    monkeypatch.delenv("SCHEDULED_FULL_SYNC_ENABLED", raising=False)
    from app.settings import get_settings

    get_settings.cache_clear()
    status = sched.get_scheduler_status()
    assert status["sync"]["mode"] == "per_component_rotation"
    assert status["sync"]["enabled"] is False
    get_settings.cache_clear()


def test_run_scheduled_analysis_skips_active_job(db_session, monkeypatch):
    monkeypatch.setattr(sched, "_list_subscription_ids", lambda _db: ["sub-1"])

    with patch.object(sched, "_has_active_analysis_job", return_value=True):
        result = sched.run_scheduled_analysis()

    assert result["status"] == "skipped"
    assert result["completed"] == []
    assert result["skipped"][0]["subscription_id"] == "sub-1"


@patch("app.db_sync.sync_all")
@patch("app.auth.get_token", return_value="token")
@patch("app.auth.reload_credential")
def test_run_scheduled_sync_uses_cached_subscriptions(
    _reload,
    _token,
    mock_sync_all,
    db_session,
    monkeypatch,
):
    db_session.add(
        SubscriptionCache(
            subscription_id="sub-a",
            display_name="Sub A",
            state="Enabled",
        )
    )
    db_session.commit()

    monkeypatch.setattr("app.database.SessionLocal", lambda: db_session)

    synced = sched.run_scheduled_sync()
    assert synced == ["sub-a"]
    mock_sync_all.assert_called_once_with("sub-a", db_session, "token")


def test_start_is_idempotent(monkeypatch):
    monkeypatch.setenv("SCHEDULED_OPERATIONS_ENABLED", "false")
    sched._started = False
    sched.start()
    sched.start()
    assert sched._started is False


def test_scheduled_engine_scoring_default_interval(monkeypatch):
    monkeypatch.delenv("SCHEDULED_ENGINE_SCORING_HOURS", raising=False)
    assert sched._engine_scoring_interval_seconds() == 3 * 3600.0


def test_scheduled_engine_scoring_enabled_follows_operations(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SCHEDULED_ENGINE_SCORING_ENABLED", raising=False)
    from app.settings import get_settings

    get_settings.cache_clear()
    assert sched.scheduled_engine_scoring_enabled() is True
    get_settings.cache_clear()


def test_run_scheduled_engine_scoring(monkeypatch):
    monkeypatch.setattr(sched, "_list_subscription_ids", lambda _db: ["sub-1"])
    monkeypatch.setattr(sched, "_try_acquire_engine_scoring_lock", lambda _db: True)
    monkeypatch.setattr(sched, "_release_engine_scoring_lock", lambda _db: None)

    with patch("app.database.SessionLocal") as mock_session_local:
        mock_db = mock_session_local.return_value
        with patch("app.advanced_scoring.score_subscription", return_value={"scoring": {"total": 5}}) as score:
            with patch(
                "app.optimizer.decision_engine.generate_optimization_actions",
                return_value={"created": 2, "updated": 1},
            ) as decide:
                result = sched.run_scheduled_engine_scoring()

    assert result["status"] == "ok"
    assert len(result["completed"]) == 1
    assert result["completed"][0]["subscription_id"] == "sub-1"
    assert result["completed"][0]["scoring_total"] == 5
    score.assert_called_once_with(mock_db, "sub-1")
    decide.assert_called_once_with(mock_db, "sub-1")


def test_get_scheduler_status_includes_engine_scoring(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SCHEDULED_ENGINE_SCORING_ENABLED", raising=False)
    from app.settings import get_settings

    get_settings.cache_clear()
    status = sched.get_scheduler_status()
    assert status["engine_scoring"]["enabled"] is True
    assert status["engine_scoring"]["interval_hours"] == 3.0
    assert status["engine_scoring"]["azure_api_calls"] is False
    assert status["engine_scoring"]["after_analysis"] is True
    get_settings.cache_clear()


def test_scheduled_engine_scoring_after_analysis_default(monkeypatch):
    monkeypatch.delenv("SCHEDULED_ENGINE_SCORING_AFTER_ANALYSIS", raising=False)
    assert sched.scheduled_engine_scoring_after_analysis() is True


def test_run_scheduled_analysis_chains_engine_scoring(monkeypatch):
    monkeypatch.setattr(sched, "_list_subscription_ids", lambda _db: ["sub-1"])
    monkeypatch.setattr(sched, "_has_active_analysis_job", lambda _db, _sub: False)
    monkeypatch.setattr(sched, "scheduled_engine_scoring_enabled", lambda: True)
    monkeypatch.setattr(sched, "scheduled_engine_scoring_after_analysis", lambda: True)

    mock_job = type("Job", (), {"id": "job-1"})()

    with patch("app.database.SessionLocal"):
        with patch("app.batch_analyzer.create_analysis_job", return_value=mock_job):
            with patch("app.batch_analyzer.execute_batch_job"):
                with patch.object(sched, "run_scheduled_engine_scoring", return_value={"status": "ok"}) as scoring:
                    result = sched.run_scheduled_analysis()

    assert result["completed"] == ["sub-1"]
    assert result["engine_scoring"]["status"] == "ok"
    scoring.assert_called_once_with(["sub-1"])

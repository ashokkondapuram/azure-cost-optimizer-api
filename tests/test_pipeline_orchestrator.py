"""Tests for assessment pipeline orchestrator stage ordering."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, PipelineRun
from app.pipeline.orchestrator import run_pipeline


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_run_pipeline_executes_stages_in_order(db_session, monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "true")
    sub = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    order: list[str] = []

    def _cost_sync(db, subscription_id, **kwargs):
        order.append("cost_sync")
        return {"status": "fresh", "skipped": True}

    def _metrics(db, subscription_id, **kwargs):
        order.append("inventory_metrics")
        return {"status": "ok"}

    def _quality(db, subscription_id):
        order.append("data_quality")
        return {"status": "ok", "assessed": 1}

    def _recommendations(db, subscription_id):
        order.append("recommendations")
        return {"status": "ok", "findings": 0}

    with (
        patch("app.pipeline.orchestrator.try_acquire_lock", return_value=True),
        patch("app.pipeline.orchestrator.release_lock"),
        patch("app.pipeline.orchestrator.run_cost_sync_worker", side_effect=_cost_sync),
        patch("app.pipeline.orchestrator.run_inventory_metrics_worker", side_effect=_metrics),
        patch("app.pipeline.orchestrator.run_data_quality_worker", side_effect=_quality),
        patch("app.pipeline.orchestrator.run_recommendation_worker", side_effect=_recommendations),
    ):
        result = run_pipeline(db_session, sub)

    assert result["status"] == "ok"
    assert order == ["cost_sync", "inventory_metrics", "data_quality", "recommendations"]
    run = db_session.query(PipelineRun).filter(PipelineRun.subscription_id == sub).one()
    assert run.status == "completed"
    assert run.current_stage == "completed"
    assert result["stages"]["cost_check"]["status"] == "fresh"
    assert result["stages"]["monitor_metrics"]["status"] == "ok"


def test_run_pipeline_skips_metrics_when_requested(db_session, monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "true")
    sub = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    order: list[str] = []

    with (
        patch("app.pipeline.orchestrator.try_acquire_lock", return_value=True),
        patch("app.pipeline.orchestrator.release_lock"),
        patch(
            "app.pipeline.orchestrator.run_cost_sync_worker",
            side_effect=lambda *a, **k: order.append("cost_sync") or {"status": "fresh"},
        ),
        patch(
            "app.pipeline.orchestrator.run_inventory_metrics_worker",
            side_effect=lambda *a, **k: order.append("inventory_metrics") or {"status": "ok"},
        ),
        patch(
            "app.pipeline.orchestrator.run_data_quality_worker",
            side_effect=lambda *a, **k: order.append("data_quality") or {"status": "ok"},
        ),
        patch(
            "app.pipeline.orchestrator.run_recommendation_worker",
            side_effect=lambda *a, **k: order.append("recommendations") or {"status": "ok"},
        ),
    ):
        result = run_pipeline(db_session, sub, skip_metrics=True)

    assert result["status"] == "ok"
    assert order == ["cost_sync", "data_quality", "recommendations"]
    assert "inventory_metrics" not in result["stages"]


def test_run_pipeline_skipped_when_lock_held(db_session, monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "true")
    sub = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    with patch("app.pipeline.orchestrator.try_acquire_lock", return_value=False):
        result = run_pipeline(db_session, sub)

    assert result["status"] == "skipped"
    assert result["reason"] == "lock_held"


def test_run_pipeline_continues_when_cost_sync_fails(db_session, monkeypatch):
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "true")
    sub = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    with (
        patch("app.pipeline.orchestrator.try_acquire_lock", return_value=True),
        patch("app.pipeline.orchestrator.release_lock"),
        patch(
            "app.pipeline.orchestrator.run_cost_sync_worker",
            return_value={"status": "failed", "error": "azure down"},
        ),
        patch("app.pipeline.orchestrator._cost_data_fresh", return_value=False),
        patch("app.pipeline.orchestrator.run_inventory_metrics_worker", return_value={"status": "ok"}),
        patch("app.pipeline.orchestrator.run_data_quality_worker", return_value={"status": "ok"}),
        patch("app.pipeline.orchestrator.run_recommendation_worker", return_value={"status": "ok"}),
    ):
        result = run_pipeline(db_session, sub)

    assert result["status"] == "ok"
    assert result["stages"]["cost_check"]["status"] == "stale"
    assert result["stages"]["inventory_metrics"]["status"] == "ok"

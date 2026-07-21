"""Tests for sync pipeline progress aggregation and Kafka consumer."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.messaging.job_envelope import JobEnvelope, JobType
from app.sync_progress import (
    STAGE_WEIGHT_PCT,
    apply_kafka_completed_event,
    apply_kafka_status_event,
    build_progress_response,
    clear_progress_cache,
    compute_percent_complete,
    serialize_progress_entry,
)


SUBSCRIPTION_ID = str(uuid.uuid4()).lower()
PIPELINE_ID = str(uuid.uuid4())


def _stages(**overrides):
    base = {
        stage: {"status": "pending", "started_at": None, "completed_at": None, "error": None}
        for stage in ("inventory", "cost", "metrics", "analysis")
    }
    for stage, row in overrides.items():
        base[stage] = {**base[stage], **row}
    return base


def _pipeline_state(**overrides):
    state = {
        "pipeline_id": PIPELINE_ID,
        "subscription_id": SUBSCRIPTION_ID,
        "status": "running",
        "current_stage": "inventory",
        "progress_pct": 12,
        "stages": _stages(),
        "analysis_job_id": None,
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
        "created_at": datetime.now(timezone.utc),
        "error": None,
        "run_params": {},
    }
    state.update(overrides)
    return state


@pytest.fixture(autouse=True)
def _reset_progress_cache():
    clear_progress_cache()
    yield
    clear_progress_cache()


def test_compute_percent_complete_all_pending():
    assert compute_percent_complete(_stages()) == 0


def test_compute_percent_complete_inventory_done():
    stages = _stages(inventory={"status": "done"})
    assert compute_percent_complete(stages) == STAGE_WEIGHT_PCT


def test_compute_percent_complete_inventory_running():
    stages = _stages(inventory={"status": "running"})
    assert compute_percent_complete(stages) == STAGE_WEIGHT_PCT // 2


def test_compute_percent_complete_two_stages_done():
    stages = _stages(
        inventory={"status": "done"},
        cost={"status": "done"},
        metrics={"status": "running"},
    )
    assert compute_percent_complete(stages) == 62


def test_compute_percent_complete_completed_pipeline():
    stages = _stages(
        inventory={"status": "done"},
        cost={"status": "done"},
        metrics={"status": "done"},
        analysis={"status": "done"},
    )
    assert compute_percent_complete(stages, pipeline_status="completed") == 100


def test_serialize_progress_entry_maps_stage_statuses():
    state = _pipeline_state(
        stages=_stages(
            inventory={"status": "done"},
            cost={"status": "running"},
        ),
        current_stage="cost",
        progress_pct=37,
    )
    entry = serialize_progress_entry(state)
    assert entry is not None
    assert entry["percent_complete"] == 37
    assert entry["stage_statuses"]["inventory"]["status"] == "done"
    assert entry["stage_statuses"]["cost"]["status"] == "running"
    assert entry["stage_statuses"]["metrics"]["status"] == "pending"
    assert entry["pending"] is True
    assert entry["message"] == "Syncing cost data"


def test_apply_kafka_status_event_uses_db_state():
    state = _pipeline_state(current_stage="metrics", progress_pct=62)
    envelope = JobEnvelope.create(
        job_type=JobType.PIPELINE_STATUS,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={"stage": "metrics", "progress_pct": 62, "status": "running"},
        source_service="platform-metrics",
    )

    with patch("app.sync_orchestrator.load_pipeline_by_id", return_value=state):
        entry = apply_kafka_status_event(envelope)

    assert entry is not None
    assert entry["subscription_id"] == SUBSCRIPTION_ID
    assert entry["current_stage"] == "metrics"
    assert entry["source"] == "kafka"


def test_apply_kafka_completed_event_marks_completed():
    state = _pipeline_state(status="running", current_stage="analysis", progress_pct=87)
    envelope = JobEnvelope.create(
        job_type=JobType.PIPELINE_COMPLETED,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={"status": "completed"},
        source_service="platform-analysis",
    )

    with patch("app.sync_orchestrator.load_pipeline_by_id", return_value=state):
        entry = apply_kafka_completed_event(envelope)

    assert entry is not None
    assert entry["status"] == "completed"
    assert entry["percent_complete"] == 100
    assert entry["pending"] is False


def test_build_progress_response_lists_active_pipelines():
    row = MagicMock()
    row.subscription_id = SUBSCRIPTION_ID
    row.id = PIPELINE_ID
    row.status = "running"
    row.current_stage = "inventory"
    row.progress_pct = 12
    row.stages_json = "{}"
    row.analysis_job_id = None
    row.error_message = None
    row.created_at = datetime.now(timezone.utc)
    row.started_at = datetime.now(timezone.utc)
    row.completed_at = None

    session = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [row]
    session.query.return_value = query

    with patch("app.database.SessionLocal", return_value=session), patch(
        "app.sync_orchestrator.expire_stale_pipeline_runs",
        return_value=[],
    ), patch(
        "app.sync_orchestrator._state_from_pipeline_row",
        return_value=_pipeline_state(),
    ):
        payload = build_progress_response([SUBSCRIPTION_ID], active_only=True, resume=False)

    assert payload["active_count"] == 1
    assert len(payload["subscriptions"]) == 1
    assert payload["subscriptions"][0]["subscription_id"] == SUBSCRIPTION_ID


def test_sync_progress_consumer_handles_status_topic():
    from app.messaging.sync_progress_consumer import _handle_progress_message

    envelope = JobEnvelope.create(
        job_type=JobType.PIPELINE_STATUS,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={"stage": "inventory", "progress_pct": 12, "status": "running"},
        source_service="platform-inventory",
    )

    with patch("app.sync_progress.apply_kafka_status_event") as apply_status:
        _handle_progress_message(envelope, "sync.pipeline.status")
        apply_status.assert_called_once_with(envelope)


def test_sync_router_registers_progress_routes():
    from app.routers.sync import router

    paths = {route.path for route in router.routes}
    assert "/sync/progress" in paths
    assert "/sync/progress/stream" in paths

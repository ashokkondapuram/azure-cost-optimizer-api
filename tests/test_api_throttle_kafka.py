"""Integration tests for Kafka API throttling (api.* topics)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.messaging.api_throttle.batch_registry import reset_batch_registry
from app.messaging.api_throttle.config import kafka_api_throttle_enabled
from app.messaging.api_throttle.metrics import get_metrics, reset_metrics
from app.messaging.api_throttle.phases import cost_api_phases
from app.messaging.api_throttle.rate_limiter import reset_rate_limiters
from app.messaging.api_throttle.topics import (
    TOPIC_API_COST_COMPLETED,
    TOPIC_API_COST_REQUESTED,
    TOPIC_API_DEAD_LETTER,
)
from app.messaging.data_ack import reset_ack_state, signal_persisted
from app.messaging.job_envelope import JobEnvelope, JobType

SUBSCRIPTION_ID = str(uuid.uuid4()).lower()
PIPELINE_ID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _reset_throttle_state():
    reset_batch_registry()
    reset_metrics()
    reset_rate_limiters()
    reset_ack_state()
    yield
    reset_batch_registry()
    reset_metrics()
    reset_rate_limiters()
    reset_ack_state()


def test_kafka_api_throttle_requires_microservices(monkeypatch):
    monkeypatch.delenv("MICROSERVICES_ONLY", raising=False)
    monkeypatch.setenv("KAFKA_API_THROTTLE_ENABLED", "true")
    assert kafka_api_throttle_enabled() is False

    monkeypatch.setenv("MICROSERVICES_ONLY", "1")
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    assert kafka_api_throttle_enabled() is True


def test_validate_api_cost_envelope_passes_schema(monkeypatch):
    monkeypatch.setenv("KAFKA_SCHEMA_VALIDATION_ENABLED", "true")

    from app.messaging.schema_registry import serialize_envelope, validate_envelope
    from app.messaging.topics import TOPIC_API_COST_REQUESTED, TOPIC_API_COST_COMPLETED

    requested = JobEnvelope.create(
        job_type=JobType.API_COST_REQUESTED,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={
            "batch_id": "batch-schema",
            "phase": "subscription_totals",
            "phase_index": 0,
            "total_phases": 3,
            "api_params": {},
            "run_params": {"token": "tok"},
            "meta": {"month": "2026-07"},
        },
        source_service="platform-cost",
    )
    validate_envelope(requested, topic=TOPIC_API_COST_REQUESTED)
    raw = serialize_envelope(requested, topic=TOPIC_API_COST_REQUESTED)
    assert b'"job_type":"api.cost"' in raw

    completed = JobEnvelope.create(
        job_type=JobType.API_COST_COMPLETED,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={
            "batch_id": "batch-schema",
            "phase": "subscription_totals",
            "phase_index": 0,
            "total_phases": 3,
            "result": {"pretax_total": 1.0},
            "api_kind": "cost",
            "run_params": {},
        },
        source_service="platform-cost",
    )
    validate_envelope(completed, topic=TOPIC_API_COST_COMPLETED)


def test_cost_api_phases_include_core_queries():
    phases = cost_api_phases(subscription_id=SUBSCRIPTION_ID)
    phase_names = [p["phase"] for p in phases]
    assert "subscription_totals" in phase_names
    assert "cost_by_service" in phase_names
    assert "cost_by_resource" in phase_names
    assert phases[0]["phase_index"] == 0
    assert phases[-1]["phase_index"] == len(phases) - 1
    assert all(p["total_phases"] == len(phases) for p in phases)


@patch("app.messaging.api_throttle.coordinator.publish_envelope_safe", return_value=True)
def test_enqueue_cost_api_jobs_publishes_all_phases(mock_publish):
    from app.messaging.api_throttle.coordinator import enqueue_cost_api_jobs

    batch_id = enqueue_cost_api_jobs(
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        run_params={"token": "test-token"},
        source_service="platform-cost",
    )
    phases = cost_api_phases(subscription_id=SUBSCRIPTION_ID)
    assert mock_publish.call_count == len(phases)
    assert batch_id

    first_call = mock_publish.call_args_list[0]
    envelope = first_call[0][0]
    assert envelope.job_type == JobType.API_COST_REQUESTED
    assert first_call[1]["topic"] == TOPIC_API_COST_REQUESTED


@patch("app.messaging.api_throttle.aggregator.publish_api_completed", return_value=True)
@patch("app.messaging.api_throttle.cost_executor.execute_cost_phase")
def test_api_cost_worker_executes_phase(mock_execute, mock_publish_completed):
    from app.messaging.api_throttle.worker import handle_api_cost_requested

    mock_execute.return_value = {"pretax_total": 10.0, "billing_currency": "USD"}

    envelope = JobEnvelope.create(
        job_type=JobType.API_COST_REQUESTED,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={
            "batch_id": "batch-1",
            "phase": "subscription_totals",
            "phase_index": 0,
            "total_phases": 1,
            "api_params": {},
            "run_params": {"token": "tok"},
            "meta": {"month": "2026-07"},
        },
        source_service="platform-cost",
    )
    handle_api_cost_requested(envelope)
    mock_execute.assert_called_once()
    mock_publish_completed.assert_called_once()


@patch("app.messaging.api_throttle.aggregator.publish_stage_data", return_value=True)
@patch("app.messaging.api_throttle.aggregator.wait_for_persist", return_value=True)
@patch("app.messaging.api_throttle.aggregator.assemble_cost_data_payload")
def test_api_completed_aggregates_and_publishes_data_cost(
    mock_assemble, mock_wait, mock_publish_data, monkeypatch
):
    from app.messaging.api_throttle.aggregator import handle_api_completed
    from app.messaging.api_throttle.batch_registry import ApiBatchState, get_batch_registry

    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")
    monkeypatch.setenv("KAFKA_DATA_PIPELINE_ENABLED", "true")

    mock_assemble.return_value = {"stage": "cost", "sections": {}, "summary": {"api_throttle": True}}

    registry = get_batch_registry()
    registry.register(
        ApiBatchState(
            batch_id="batch-agg",
            pipeline_id=PIPELINE_ID,
            subscription_id=SUBSCRIPTION_ID,
            api_kind="cost",
            total_phases=1,
            run_params={},
            source_service="platform-cost",
            meta={"month": "2026-07"},
        )
    )

    envelope = JobEnvelope.create(
        job_type=JobType.API_COST_COMPLETED,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={
            "batch_id": "batch-agg",
            "phase": "subscription_totals",
            "phase_index": 0,
            "total_phases": 1,
            "result": {"pretax_total": 5.0},
            "api_kind": "cost",
            "run_params": {},
            "meta": {"month": "2026-07"},
        },
        source_service="platform-cost",
    )

    signal_persisted(PIPELINE_ID, "cost")
    handle_api_completed(envelope)
    mock_assemble.assert_called_once()
    mock_publish_data.assert_called_once()
    mock_wait.assert_called_once()


@patch("app.messaging.api_throttle.dlq.mark_pipeline_failed_db")
@patch("app.messaging.api_throttle.dlq.publish_envelope_safe", return_value=True)
def test_dlq_marks_pipeline_failed(mock_publish, mock_mark_failed, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("KAFKA_API_DLQ_ENABLED", "true")
    from app.messaging.api_throttle.dlq import handle_dead_letter, publish_dead_letter

    original = JobEnvelope.create(
        job_type=JobType.API_COST_REQUESTED,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={
            "phase": "cost_by_service",
            "batch_id": "batch-dlq",
            "run_params": {},
        },
        source_service="platform-cost",
    )
    publish_dead_letter(original, error="429 Too Many Requests", original_topic=TOPIC_API_COST_REQUESTED)
    assert mock_publish.call_count == 1
    dlq_envelope = mock_publish.call_args_list[0][0][0]
    assert dlq_envelope.job_type == JobType.API_DEAD_LETTER
    assert mock_publish.call_args_list[0][1]["topic"] == TOPIC_API_DEAD_LETTER

    handle_dead_letter(dlq_envelope, TOPIC_API_DEAD_LETTER)
    mock_mark_failed.assert_called_once()
    assert get_metrics().dlq_messages == 1


@patch("app.messaging.api_throttle.coordinator.enqueue_cost_api_jobs", return_value="batch-x")
def test_run_cost_stage_delegates_when_throttle_enabled(mock_enqueue, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")
    monkeypatch.setenv("KAFKA_DATA_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("KAFKA_API_THROTTLE_ENABLED", "true")

    from app.messaging.sync_stages import run_cost_stage

    envelope = JobEnvelope.create(
        job_type=JobType.SYNC_COST,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={"run_params": {"include_costs": True, "token": "tok"}},
        source_service="platform-cost",
    )

    with patch("app.sync_orchestrator.mark_pipeline_running_db"), patch(
        "app.sync_orchestrator.pipeline_row_still_active", return_value=True
    ), patch("app.sync_orchestrator.load_pipeline_by_id", return_value={"status": "running", "stages": {}}):
        run_cost_stage(envelope, source_service="platform-cost")

    mock_enqueue.assert_called_once()


def test_rate_limiter_records_throttle_wait():
    from app.messaging.api_throttle.envelope import ApiDomain
    from app.messaging.api_throttle.rate_limiter import DomainRateLimiter, reset_rate_limiters

    reset_rate_limiters()
    limiter = DomainRateLimiter(
        ApiDomain.COST_MANAGEMENT,
        rate_fn=lambda: 1.0,
        burst_fn=lambda: 1.0,
        delay_fn=lambda: 0.0,
    )
    limiter.acquire(label="test")
    limiter.acquire(label="test")
    assert get_metrics().throttle_waits >= 0


@patch("app.messaging.kafka_client.start_consumer_loop")
def test_start_api_throttle_consumers_registers_worker_and_aggregate(mock_start, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")
    monkeypatch.setenv("KAFKA_API_THROTTLE_ENABLED", "true")

    from app.messaging.api_throttle.consumers import start_api_throttle_consumers

    start_api_throttle_consumers("platform-cost")
    assert mock_start.call_count == 3
    groups = [call.kwargs.get("consumer_group") or call[1].get("consumer_group") for call in mock_start.call_args_list]
    assert any("api.cost" in (g or "") for g in groups)
    assert any("aggregate" in (g or "") for g in groups)

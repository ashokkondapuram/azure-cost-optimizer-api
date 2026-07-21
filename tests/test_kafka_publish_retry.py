"""Tests for Kafka publish retry and retriable pipeline recovery."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.messaging.job_envelope import JobEnvelope, JobType
from app.messaging.kafka_errors import KafkaPublishExhaustedError
from app.messaging.topics import TOPIC_SYNC_INVENTORY_REQUESTED

SUBSCRIPTION_ID = str(uuid.uuid4()).lower()
PIPELINE_ID = str(uuid.uuid4())


def _delivery_success(on_delivery, topic: str) -> None:
    if on_delivery is not None:
        on_delivery(None, MagicMock(topic=topic))


def _delivery_failure(on_delivery, topic: str, error: str = "MSG_SIZE_TOO_LARGE") -> None:
    if on_delivery is not None:
        on_delivery(MagicMock(__str__=lambda self: error), MagicMock(topic=topic))


@patch("app.messaging.kafka_client.get_producer")
def test_publish_envelope_safe_waits_for_delivery(mock_get_producer, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("KAFKA_SCHEMA_VALIDATION_ENABLED", "false")
    monkeypatch.setenv("KAFKA_PUBLISH_MAX_RETRIES", "0")

    producer = MagicMock()

    def produce_side_effect(**kwargs):
        _delivery_success(kwargs.get("on_delivery"), kwargs["topic"])

    producer.produce.side_effect = produce_side_effect
    mock_get_producer.return_value = producer

    from app.messaging.kafka_client import publish_envelope_safe

    envelope = JobEnvelope.create(
        job_type=JobType.SYNC_INVENTORY,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
    )
    ok = publish_envelope_safe(envelope, topic=TOPIC_SYNC_INVENTORY_REQUESTED)
    assert ok is True
    producer.produce.assert_called_once()


@patch("app.messaging.kafka_client.time.sleep")
@patch("app.messaging.kafka_client.get_producer")
def test_publish_envelope_safe_retries_then_succeeds(mock_get_producer, mock_sleep, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("KAFKA_SCHEMA_VALIDATION_ENABLED", "false")
    monkeypatch.setenv("KAFKA_PUBLISH_MAX_RETRIES", "2")
    monkeypatch.setenv("KAFKA_PUBLISH_RETRY_BACKOFF_SEC", "0.01")

    producer = MagicMock()
    attempts = {"count": 0}

    def produce_side_effect(**kwargs):
        attempts["count"] += 1
        on_delivery = kwargs.get("on_delivery")
        if attempts["count"] == 1:
            _delivery_failure(on_delivery, kwargs["topic"])
        else:
            _delivery_success(on_delivery, kwargs["topic"])

    producer.produce.side_effect = produce_side_effect
    mock_get_producer.return_value = producer

    from app.messaging.kafka_client import publish_envelope_safe

    envelope = JobEnvelope.create(
        job_type=JobType.SYNC_INVENTORY,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
    )
    ok = publish_envelope_safe(envelope, topic=TOPIC_SYNC_INVENTORY_REQUESTED)
    assert ok is True
    assert attempts["count"] == 2
    mock_sleep.assert_called_once()


@patch("app.messaging.kafka_client.time.sleep")
@patch("app.messaging.kafka_client.get_producer")
def test_publish_envelope_safe_exhausts_retries(mock_get_producer, mock_sleep, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("KAFKA_SCHEMA_VALIDATION_ENABLED", "false")
    monkeypatch.setenv("KAFKA_PUBLISH_MAX_RETRIES", "2")
    monkeypatch.setenv("KAFKA_PUBLISH_RETRY_BACKOFF_SEC", "0.01")

    producer = MagicMock()

    def produce_side_effect(**kwargs):
        _delivery_failure(kwargs.get("on_delivery"), kwargs["topic"])

    producer.produce.side_effect = produce_side_effect
    mock_get_producer.return_value = producer

    from app.messaging.kafka_client import publish_envelope_safe

    envelope = JobEnvelope.create(
        job_type=JobType.SYNC_INVENTORY,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
    )
    ok = publish_envelope_safe(envelope, topic=TOPIC_SYNC_INVENTORY_REQUESTED)
    assert ok is False
    assert producer.produce.call_count == 3
    assert mock_sleep.call_count == 2


@patch("app.messaging.data_producer.publish_envelope_safe", return_value=False)
def test_data_stage_publish_failure_marks_retriable(mock_publish, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")
    monkeypatch.setenv("KAFKA_DATA_PIPELINE_ENABLED", "true")

    from app.messaging.data_stage import run_stage_via_data_pipeline
    from app.messaging.job_envelope import JobEnvelope

    envelope = JobEnvelope.create(
        job_type=JobType.SYNC_COST,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={"run_params": {}},
        source_service="platform-cost",
    )

    with patch("app.sync_orchestrator.mark_pipeline_publish_failed_db") as mark_retriable:
        with pytest.raises(KafkaPublishExhaustedError):
            run_stage_via_data_pipeline(
                envelope,
                stage="cost",
                source_service="platform-cost",
                run_params={},
                fetch_fn=lambda: {"cost_by_service": 1},
            )
    mark_retriable.assert_called_once()


@patch("app.messaging.sync_producer.publish_sync_job", return_value=True)
def test_resume_incomplete_pipelines_republish_after_publish_failure(publish, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")

    import app.sync_orchestrator as orch
    from app.messaging.job_envelope import JobType
    from app.sync_orchestrator import resume_incomplete_pipelines

    state = orch._new_pipeline_state(SUBSCRIPTION_ID)
    state["pipeline_id"] = PIPELINE_ID
    state["status"] = "running"
    state["current_stage"] = "cost"
    state["publish_retriable"] = True
    state["last_publish_error"] = "MSG_SIZE_TOO_LARGE"
    state["stages"]["inventory"]["status"] = "done"
    state["stages"]["cost"]["status"] = "running"
    state["run_params"] = {"reason": "resume-test"}

    with patch.object(orch, "expire_stale_pipeline_runs"):
        with patch.object(orch, "list_incomplete_pipeline_states", return_value=[state]):
            with patch.object(orch, "_pipeline_row_still_active", return_value=True):
                resumed = resume_incomplete_pipelines(service_id="platform-inventory")

    assert resumed == [PIPELINE_ID]
    publish.assert_called_once()
    assert publish.call_args.args[0] == JobType.SYNC_COST


def test_consumer_does_not_commit_on_handler_failure():
    from app.messaging.kafka_client import start_consumer_loop

    consumer = MagicMock()
    msg = MagicMock()
    msg.error.return_value = None
    msg.topic.return_value = TOPIC_SYNC_INVENTORY_REQUESTED
    msg.value.return_value = json.dumps(
        {
            "job_id": str(uuid.uuid4()),
            "job_type": JobType.SYNC_INVENTORY.value,
            "subscription_id": SUBSCRIPTION_ID,
            "pipeline_id": PIPELINE_ID,
            "payload": {},
            "created_at": "2026-07-17T00:00:00+00:00",
            "source_service": "platform-inventory",
        }
    ).encode("utf-8")

    poll_results = [msg, None]

    def poll_side_effect(_timeout):
        return poll_results.pop(0) if poll_results else None

    consumer.poll.side_effect = poll_side_effect
    stop_event = __import__("threading").Event()

    def handler(_envelope, _topic):
        raise RuntimeError("handler failed")

    with patch("app.messaging.kafka_client.kafka_enabled", return_value=True):
        with patch("app.messaging.kafka_client._connect_consumer", return_value=(consumer, "test-group")):
            with patch("app.messaging.kafka_client.deserialize_envelope") as deserialize:
                deserialize.return_value = JobEnvelope.create(
                    job_type=JobType.SYNC_INVENTORY,
                    subscription_id=SUBSCRIPTION_ID,
                    pipeline_id=PIPELINE_ID,
                )
                thread = start_consumer_loop(
                    service_id="test-service",
                    topics=[TOPIC_SYNC_INVENTORY_REQUESTED],
                    handler=handler,
                    stop_event=stop_event,
                )
                stop_event.wait(timeout=2.0)
                stop_event.set()
                thread.join(timeout=2.0)

    consumer.commit.assert_not_called()

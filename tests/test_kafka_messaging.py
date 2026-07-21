"""Unit tests for Kafka messaging layer (mocked producer/consumer)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.messaging.config import kafka_enabled, kafka_pipeline_dispatch_enabled
from app.messaging.job_envelope import JobEnvelope, JobType
from app.messaging.topics import (
    TOPIC_SYNC_COST_REQUESTED,
    TOPIC_SYNC_INVENTORY_REQUESTED,
    TOPIC_SYNC_PIPELINE_STATUS,
    topic_for_job_type,
)


SUBSCRIPTION_ID = str(uuid.uuid4()).lower()
PIPELINE_ID = str(uuid.uuid4())


def test_job_envelope_serializes_datetime_payload():
    from datetime import datetime, timezone

    ts = datetime(2026, 7, 17, 12, 30, tzinfo=timezone.utc)
    envelope = JobEnvelope.create(
        job_type=JobType.DATA_COST_SYNCED,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={
            "data": {
                "stage": "cost",
                "sections": {
                    "cost_sync_run": {"previous_synced_at": ts},
                },
                "summary": {},
            },
            "run_params": {},
        },
        source_service="platform-cost",
    )
    raw = envelope.to_json()
    payload = json.loads(raw)
    assert payload["payload"]["data"]["sections"]["cost_sync_run"]["previous_synced_at"] == ts.isoformat()


def test_topic_provision_imports_without_scripts_package(monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")

    import sys

    scripts_modules = [name for name in sys.modules if name == "scripts" or name.startswith("scripts.")]
    for name in scripts_modules:
        sys.modules.pop(name, None)

    from app.messaging import topic_provision as mod

    mod._provisioned = False
    with patch("app.messaging.topic_admin.provision_topics", return_value=10):
        assert mod.ensure_topics_provisioned() is True


@patch("app.messaging.sync_producer.publish_pipeline_completed")
@patch("app.messaging.sync_producer.publish_next_stage")
@patch("app.messaging.data_stage.publish_stage_data", return_value=False)
@patch("app.sync_orchestrator.mark_pipeline_publish_failed_db")
def test_failed_data_publish_does_not_emit_pipeline_completed(
    mock_mark_publish_failed,
    mock_publish_stage,
    mock_publish_next,
    mock_publish_completed,
    monkeypatch,
):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")
    monkeypatch.setenv("KAFKA_DATA_PIPELINE_ENABLED", "true")

    from app.messaging.data_stage import run_stage_via_data_pipeline
    from app.messaging.kafka_errors import KafkaPublishExhaustedError
    from app.messaging.sync_consumers import _handle_stage

    envelope = JobEnvelope.create(
        job_type=JobType.SYNC_COST,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={"run_params": {"include_costs": True}},
        source_service="platform-cost",
    )

    def _runner(env, *, source_service):
        run_stage_via_data_pipeline(
            env,
            stage="cost",
            source_service=source_service,
            run_params={"include_costs": True},
            fetch_fn=lambda: {"cost_by_service": 1},
        )

    with pytest.raises(KafkaPublishExhaustedError, match="Failed to publish data.cost.synced"):
        _handle_stage(envelope, stage="cost", runner=_runner, source_service="platform-cost")

    mock_mark_publish_failed.assert_called()
    mock_publish_completed.assert_not_called()
    mock_publish_next.assert_not_called()


def test_job_envelope_roundtrip():
    envelope = JobEnvelope.create(
        job_type=JobType.SYNC_INVENTORY,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={"run_params": {"reason": "test"}},
        source_service="platform-inventory",
    )
    restored = JobEnvelope.from_json(envelope.to_json())
    assert restored.job_id == envelope.job_id
    assert restored.job_type == JobType.SYNC_INVENTORY
    assert restored.subscription_id == SUBSCRIPTION_ID
    assert restored.pipeline_id == PIPELINE_ID
    assert restored.payload["run_params"]["reason"] == "test"
    assert restored.idempotency_key == f"{PIPELINE_ID}:sync.inventory"


def test_topic_for_job_type():
    assert topic_for_job_type(JobType.SYNC_INVENTORY) == TOPIC_SYNC_INVENTORY_REQUESTED
    assert topic_for_job_type(JobType.SYNC_COST) == TOPIC_SYNC_COST_REQUESTED


def test_kafka_disabled_by_default(monkeypatch):
    monkeypatch.delenv("KAFKA_ENABLED", raising=False)
    assert kafka_enabled() is False
    assert kafka_pipeline_dispatch_enabled() is False


def test_kafka_pipeline_requires_microservices(monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.delenv("MICROSERVICES_ONLY", raising=False)
    monkeypatch.delenv("MICROSERVICES_ENABLED", raising=False)
    assert kafka_enabled() is True
    assert kafka_pipeline_dispatch_enabled() is False


def test_kafka_pipeline_enabled_in_microservices(monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")
    assert kafka_pipeline_dispatch_enabled() is True


@patch("app.messaging.kafka_client.get_producer")
def test_publish_envelope_safe(mock_get_producer, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("KAFKA_SCHEMA_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("KAFKA_PUBLISH_MAX_RETRIES", "0")
    producer = MagicMock()

    def produce_side_effect(**kwargs):
        on_delivery = kwargs.get("on_delivery")
        if on_delivery is not None:
            on_delivery(None, MagicMock(topic=TOPIC_SYNC_INVENTORY_REQUESTED))

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
    call_kwargs = producer.produce.call_args.kwargs
    assert call_kwargs["topic"] == TOPIC_SYNC_INVENTORY_REQUESTED
    payload = json.loads(call_kwargs["value"].decode("utf-8"))
    assert payload["pipeline_id"] == PIPELINE_ID


@patch("app.messaging.sync_producer.publish_envelope_safe", return_value=True)
def test_publish_inventory_requested(mock_publish, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")

    from app.messaging.sync_producer import publish_inventory_requested

    ok = publish_inventory_requested(
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        run_params={"reason": "test"},
    )
    assert ok is True
    mock_publish.assert_called_once()


def test_request_full_sync_uses_kafka_when_enabled(monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")

    import app.sync_orchestrator as module
    from app.sync_orchestrator import request_full_sync

    with module._lock:
        module._pending.clear()
        module._pipeline_by_sub.clear()

    with patch("app.sync_orchestrator._persist_pipeline_state"):
        with patch("app.messaging.sync_producer.publish_inventory_requested", return_value=True) as publish:
            with patch("app.sync_orchestrator.threading.Thread") as thread_cls:
                enqueued, payload = request_full_sync(SUBSCRIPTION_ID, reason="kafka-test")

    assert enqueued is True
    assert payload.get("kafka") is True
    publish.assert_called_once()
    thread_cls.assert_not_called()

    with module._lock:
        module._pending.clear()
        module._pipeline_by_sub.clear()


def test_request_full_sync_falls_back_to_thread_when_kafka_disabled(monkeypatch):
    monkeypatch.delenv("KAFKA_ENABLED", raising=False)
    monkeypatch.delenv("MICROSERVICES_ONLY", raising=False)

    import app.sync_orchestrator as module
    from app.sync_orchestrator import request_full_sync

    with module._lock:
        module._pending.clear()
        module._pipeline_by_sub.clear()

    with patch("app.sync_orchestrator._persist_pipeline_state"):
        with patch("app.sync_orchestrator.threading.Thread") as thread_cls:
            enqueued, payload = request_full_sync(SUBSCRIPTION_ID, reason="thread-test")

    assert enqueued is True
    assert payload.get("kafka") is False
    thread_cls.assert_called_once()

    with module._lock:
        module._pending.clear()
        module._pipeline_by_sub.clear()


def test_topic_schema_bindings_cover_all_sync_topics():
    from app.messaging.schema_registry import topic_schema_bindings
    from app.messaging.topic_config import topic_specs

    bindings = topic_schema_bindings()
    assert set(bindings) == {spec.name for spec in topic_specs()}


def test_validate_envelope_for_inventory_topic():
    from app.messaging.schema_registry import validate_envelope
    from app.messaging.topics import TOPIC_SYNC_INVENTORY_REQUESTED

    envelope = JobEnvelope.create(
        job_type=JobType.SYNC_INVENTORY,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={"run_params": {"reason": "schema-test"}},
        source_service="platform-inventory",
    )
    validate_envelope(envelope, topic=TOPIC_SYNC_INVENTORY_REQUESTED)


def test_validate_envelope_with_null_run_params_fields(monkeypatch):
    """run_params fields omitted at request time are serialized as null."""
    monkeypatch.setenv("KAFKA_SCHEMA_VALIDATION_ENABLED", "true")

    from app.messaging.schema_registry import serialize_envelope, validate_envelope
    from app.messaging.topics import TOPIC_SYNC_INVENTORY_REQUESTED

    run_params = {
        "token": None,
        "type_list": None,
        "scope_components": None,
        "scope_resource_types": None,
        "include_costs": True,
        "profile": "default",
        "engine_version": "extended",
        "reason": "manual_api",
        "force": False,
    }
    envelope = JobEnvelope.create(
        job_type=JobType.SYNC_INVENTORY,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={"run_params": run_params},
        source_service="platform-gateway",
    )
    validate_envelope(envelope, topic=TOPIC_SYNC_INVENTORY_REQUESTED)
    raw = serialize_envelope(envelope, topic=TOPIC_SYNC_INVENTORY_REQUESTED)
    payload = json.loads(raw.decode("utf-8"))
    assert payload["payload"]["run_params"]["token"] is None


@patch("app.messaging.kafka_client.get_producer")
def test_publish_envelope_with_null_token(mock_get_producer, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("KAFKA_SCHEMA_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("KAFKA_PUBLISH_MAX_RETRIES", "0")
    producer = MagicMock()

    def produce_side_effect(**kwargs):
        on_delivery = kwargs.get("on_delivery")
        if on_delivery is not None:
            on_delivery(None, MagicMock(topic=TOPIC_SYNC_INVENTORY_REQUESTED))

    producer.produce.side_effect = produce_side_effect
    mock_get_producer.return_value = producer

    from app.messaging.kafka_client import publish_envelope_safe

    envelope = JobEnvelope.create(
        job_type=JobType.SYNC_INVENTORY,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={
            "run_params": {
                "token": None,
                "reason": "manual_api",
                "include_costs": True,
                "force": False,
            }
        },
        source_service="platform-gateway",
    )
    ok = publish_envelope_safe(envelope, topic=TOPIC_SYNC_INVENTORY_REQUESTED)
    assert ok is True
    producer.produce.assert_called_once()
    payload = json.loads(producer.produce.call_args.kwargs["value"].decode("utf-8"))
    assert payload["payload"]["run_params"]["token"] is None


def test_validate_pipeline_status_payload():
    from app.messaging.schema_registry import validate_envelope
    from app.messaging.topics import TOPIC_SYNC_PIPELINE_STATUS

    envelope = JobEnvelope.create(
        job_type=JobType.PIPELINE_STATUS,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={
            "stage": "inventory",
            "progress_pct": 50,
            "status": "running",
        },
        source_service="platform-inventory",
    )
    validate_envelope(envelope, topic=TOPIC_SYNC_PIPELINE_STATUS)


def test_serialize_deserialize_roundtrip(monkeypatch):
    monkeypatch.setenv("KAFKA_SCHEMA_VALIDATION_ENABLED", "true")

    from app.messaging.schema_registry import deserialize_envelope, serialize_envelope
    from app.messaging.topics import TOPIC_SYNC_COST_REQUESTED

    envelope = JobEnvelope.create(
        job_type=JobType.SYNC_COST,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={"run_params": {"reason": "roundtrip"}},
        source_service="platform-inventory",
    )
    raw = serialize_envelope(envelope, topic=TOPIC_SYNC_COST_REQUESTED)
    restored = deserialize_envelope(raw, topic=TOPIC_SYNC_COST_REQUESTED)
    assert restored.job_type == JobType.SYNC_COST
    assert restored.pipeline_id == PIPELINE_ID


def test_deserialize_legacy_json_without_strict(monkeypatch):
    monkeypatch.setenv("KAFKA_SCHEMA_VALIDATION_ENABLED", "true")
    monkeypatch.delenv("KAFKA_SCHEMA_VALIDATION_STRICT", raising=False)

    from app.messaging.schema_registry import deserialize_envelope
    from app.messaging.topics import TOPIC_SYNC_PIPELINE_STATUS

    envelope = JobEnvelope.create(
        job_type=JobType.PIPELINE_STATUS,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={"stage": "cost", "progress_pct": 10, "status": "running"},
    )
    raw = envelope.to_json()
    restored = deserialize_envelope(raw, topic=TOPIC_SYNC_PIPELINE_STATUS)
    assert restored.job_type == JobType.PIPELINE_STATUS


def test_manifest_paths_resolve_from_repo_root(monkeypatch, tmp_path):
    """Relative manifest env vars must resolve from repo root, not process cwd."""
    monkeypatch.setenv("KAFKA_TOPICS_MANIFEST", "data/kafka-topics.yaml")
    monkeypatch.setenv("KAFKA_SCHEMAS_MANIFEST", "data/kafka/schemas/schemas-manifest.yaml")
    monkeypatch.chdir(tmp_path)

    from app.messaging import schema_registry, topic_config

    topic_config.load_manifest.cache_clear()
    schema_registry.load_schema_manifest.cache_clear()

    assert topic_config.manifest_path().is_file()
    assert schema_registry.manifest_path().is_file()
    assert schema_registry.schemas_root().is_dir()
    topic_config.load_manifest()
    schema_registry.load_schema_manifest()


def test_topic_config_matches_manifest():
    from app.messaging.topic_config import topic_specs, topic_spec_map

    specs = topic_specs()
    assert len(specs) == 17
    inventory = topic_spec_map()["sync.inventory.requested"]
    assert inventory.partitions == 6
    assert inventory.replication_factor == 1
    assert "data.inventory.synced" in topic_spec_map()


def test_data_envelope_roundtrip():
    from app.messaging.job_envelope import JobEnvelope, JobType

    envelope = JobEnvelope.create(
        job_type=JobType.DATA_COST_SYNCED,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={
            "data": {"stage": "cost", "sections": {"cost_by_service": {}}, "summary": {}},
            "run_params": {},
        },
        source_service="platform-cost",
    )
    restored = JobEnvelope.from_json(envelope.to_json())
    assert restored.job_type == JobType.DATA_COST_SYNCED
    assert restored.payload["data"]["stage"] == "cost"


def test_orchestration_topics_filtered():
    from app.messaging.topic_config import data_topics_for_service, orchestration_topics_for_service

    orch = orchestration_topics_for_service("platform-inventory")
    data = data_topics_for_service("platform-inventory")
    assert orch == [
        "sync.inventory.requested",
        "sync.pipeline.status",
        "sync.pipeline.completed",
    ]
    assert data == ["data.inventory.synced"]


@patch("app.messaging.topic_admin.provision_topics", return_value=10)
def test_ensure_topics_provisioned(mock_provision, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")

    from app.messaging import topic_provision as mod

    mod._provisioned = False
    assert mod.ensure_topics_provisioned() is True
    mock_provision.assert_called_once()


@patch("app.messaging.data_producer.publish_envelope_safe", return_value=True)
def test_publish_stage_data_from_messaging_tests(mock_publish, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")
    monkeypatch.setenv("KAFKA_DATA_PIPELINE_ENABLED", "true")

    from app.messaging.data_producer import publish_stage_data
    from app.messaging.data_topics import TOPIC_DATA_INVENTORY_SYNCED

    ok = publish_stage_data(
        "inventory",
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        data_payload={"stage": "inventory", "sections": {}, "summary": {}},
        source_service="platform-inventory",
        run_params={"reason": "test"},
    )
    assert ok is True
    mock_publish.assert_called_once()
    assert mock_publish.call_args.kwargs["topic"] == TOPIC_DATA_INVENTORY_SYNCED


def _pipeline_state_at_stage(stage: str, *, sub: str = SUBSCRIPTION_ID, pipeline_id: str = PIPELINE_ID):
    """Build a pipeline state dict interrupted at *stage*."""
    import app.sync_orchestrator as orch

    state = orch._new_pipeline_state(sub)
    state["pipeline_id"] = pipeline_id
    state["status"] = "running"
    state["current_stage"] = stage
    state["started_at"] = orch._now()
    state["run_params"] = {"reason": "resume-test", "include_costs": True}
    stage_index = orch.STAGE_ORDER.index(stage)
    for idx, name in enumerate(orch.STAGE_ORDER):
        if idx < stage_index:
            state["stages"][name]["status"] = "done"
        elif name == stage:
            state["stages"][name]["status"] = "running"
    return state


def test_resolve_resume_job_type_at_cost_stage():
    from app.messaging.job_envelope import JobType
    from app.sync_orchestrator import resolve_resume_job_type

    state = _pipeline_state_at_stage("cost")
    assert resolve_resume_job_type(state) == JobType.SYNC_COST


def test_resolve_resume_job_type_at_inventory():
    from app.messaging.job_envelope import JobType
    from app.sync_orchestrator import resolve_resume_job_type

    state = _pipeline_state_at_stage("inventory")
    assert resolve_resume_job_type(state) == JobType.SYNC_INVENTORY


def test_resolve_resume_job_type_after_inventory_done():
    from app.messaging.job_envelope import JobType
    from app.sync_orchestrator import resolve_resume_job_type

    state = _pipeline_state_at_stage("cost")
    state["stages"]["inventory"]["status"] = "done"
    state["stages"]["cost"]["status"] = "pending"
    state["current_stage"] = "inventory"
    assert resolve_resume_job_type(state) == JobType.SYNC_COST


def test_resolve_resume_job_type_all_stages_done_returns_none():
    import app.sync_orchestrator as orch
    from app.sync_orchestrator import resolve_resume_job_type

    state = orch._new_pipeline_state(SUBSCRIPTION_ID)
    state["pipeline_id"] = PIPELINE_ID
    state["status"] = "running"
    for stage in orch.STAGE_ORDER:
        state["stages"][stage]["status"] = "done"
    assert resolve_resume_job_type(state) is None


@patch("app.messaging.sync_producer.publish_sync_job", return_value=True)
def test_resume_incomplete_pipelines_publishes_cost_not_inventory(publish, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")

    import app.sync_orchestrator as orch
    from app.messaging.job_envelope import JobType
    from app.sync_orchestrator import resume_incomplete_pipelines

    state = _pipeline_state_at_stage("cost")

    with patch.object(orch, "expire_stale_pipeline_runs"):
        with patch.object(orch, "list_incomplete_pipeline_states", return_value=[state]):
            with patch.object(orch, "_pipeline_row_still_active", return_value=True):
                resumed = resume_incomplete_pipelines(service_id="platform-inventory")

    assert resumed == [PIPELINE_ID]
    publish.assert_called_once()
    assert publish.call_args.args[0] == JobType.SYNC_COST


def test_resume_incomplete_pipelines_skipped_on_non_inventory_service(monkeypatch):
    import app.sync_orchestrator as orch
    from app.sync_orchestrator import resume_incomplete_pipelines

    state = _pipeline_state_at_stage("metrics")
    with patch.object(orch, "expire_stale_pipeline_runs"):
        with patch.object(orch, "list_incomplete_pipeline_states", return_value=[state]) as list_fn:
            with patch("app.messaging.sync_producer.publish_sync_job") as publish:
                resumed = resume_incomplete_pipelines(service_id="platform-cost")

    assert resumed == []
    publish.assert_not_called()


@patch("app.messaging.sync_producer.publish_pipeline_completed", return_value=True)
@patch("app.messaging.sync_producer.publish_sync_job", return_value=True)
def test_resume_pipeline_state_finalizes_when_all_stages_done(mock_publish, mock_completed, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")

    import app.sync_orchestrator as orch
    from app.sync_orchestrator import resume_pipeline_state

    state = orch._new_pipeline_state(SUBSCRIPTION_ID)
    state["pipeline_id"] = PIPELINE_ID
    state["status"] = "running"
    for stage in orch.STAGE_ORDER:
        state["stages"][stage]["status"] = "done"

    with patch.object(orch, "_pipeline_row_still_active", return_value=True):
        with patch.object(orch, "mark_pipeline_complete_db") as mark_complete:
            ok = resume_pipeline_state(state, source_service="platform-inventory")

    assert ok is True
    mock_publish.assert_not_called()
    mark_complete.assert_called_once_with(
        PIPELINE_ID, SUBSCRIPTION_ID, source_service="platform-inventory"
    )
    mock_completed.assert_called_once()


def test_service_hooks_resume_on_inventory_startup(monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")

    with patch("app.sync_orchestrator.resume_incomplete_pipelines", return_value=["pipe-1"]) as resume:
        with patch("app.messaging.data_consumers.start_data_persistence_consumer"):
            with patch("app.messaging.sync_consumers.start_inventory_consumer"):
                from app.messaging.service_hooks import start_kafka_consumers_for_service

                start_kafka_consumers_for_service("platform-inventory")

    resume.assert_called_once_with(service_id="platform-inventory")

"""Unit tests for Kafka data pipeline (fetch → Redpanda → PostgreSQL)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.messaging.data_ack import reset_ack_state, signal_persisted, wait_for_persist
from app.messaging.data_collector import SyncDataCollector, collect_sync_data
from app.messaging.data_topics import (
    TOPIC_DATA_COST_SYNCED,
    TOPIC_DATA_INVENTORY_SYNCED,
    data_job_type_for_stage,
    data_topic_for_job_type,
)
from app.messaging.job_envelope import JobEnvelope, JobType

SUBSCRIPTION_ID = str(uuid.uuid4()).lower()
PIPELINE_ID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _clear_ack_state():
    reset_ack_state()
    yield
    reset_ack_state()


def test_data_job_type_for_stage():
    assert data_job_type_for_stage("inventory") == JobType.DATA_INVENTORY_SYNCED
    assert data_job_type_for_stage("analysis") == JobType.DATA_ANALYSIS_COMPLETED
    assert data_job_type_for_stage("unknown") is None


def test_data_topic_for_job_type():
    assert data_topic_for_job_type(JobType.DATA_INVENTORY_SYNCED) == TOPIC_DATA_INVENTORY_SYNCED
    assert data_topic_for_job_type(JobType.DATA_COST_SYNCED) == TOPIC_DATA_COST_SYNCED


def test_sync_data_collector_sanitizes_datetime_payload():
    ts = datetime(2026, 7, 17, 8, 0, tzinfo=timezone.utc)
    with collect_sync_data("cost") as collector:
        collector.add_section("cost_sync_run", {"previous_synced_at": ts, "amount": Decimal("12.50")})
        collector.summary = {"cost_by_service": 1}

    payload = collector.to_payload()
    assert payload["sections"]["cost_sync_run"]["previous_synced_at"] == ts.isoformat()
    assert payload["sections"]["cost_sync_run"]["amount"] == 12.5

    envelope = JobEnvelope.create(
        job_type=JobType.DATA_COST_SYNCED,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={"data": payload, "run_params": {}},
        source_service="platform-cost",
    )
    serialized = json.loads(envelope.to_json())
    assert serialized["payload"]["data"]["sections"]["cost_sync_run"]["previous_synced_at"] == ts.isoformat()


def test_sync_data_collector_payload():
    with collect_sync_data("inventory") as collector:
        collector.add_section("inventory_batches", [{"canonical_type": "compute/vm", "mappings": []}])
        collector.summary = {"db_total": 1}

    payload = collector.to_payload()
    assert payload["stage"] == "inventory"
    assert "inventory_batches" in payload["sections"]
    assert payload["summary"]["db_total"] == 1


def test_wait_for_persist_signal():
    assert wait_for_persist(PIPELINE_ID, "inventory", timeout=0.1) is False
    signal_persisted(PIPELINE_ID, "inventory")
    assert wait_for_persist(PIPELINE_ID, "inventory", timeout=0.1) is True


@patch("app.database.SessionLocal")
def test_persist_inventory_data_idempotent(mock_session_local):
    from app.messaging.data_persist import persist_data_envelope

    mock_db = MagicMock()
    mock_session_local.return_value = mock_db

    envelope = JobEnvelope.create(
        job_type=JobType.DATA_INVENTORY_SYNCED,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={
            "data": {
                "stage": "inventory",
                "sections": {
                    "inventory_batches": [
                        {
                            "canonical_type": "compute/vm",
                            "mappings": [
                                {
                                    "resource_id": "/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
                                    "resource_name": "vm1",
                                    "resource_type": "compute/vm",
                                    "sku": "Standard_D2s_v3",
                                    "sku_json": {},
                                }
                            ],
                        }
                    ],
                    "post_sync": {"dedupe_snapshots": False, "dedupe_pricing": False},
                },
                "summary": {},
            },
            "run_params": {},
        },
        source_service="platform-inventory",
    )

    with patch("app.bulk_resource_upsert.bulk_upsert_snapshots", return_value=1) as upsert:
        with patch("app.db_sync.sync_subscription_catalog"):
            with patch("app.db_sync.ensure_subscription_cache_row"):
                with patch("app.resource_pricing.upsert_resource_pricing_profile"):
                    persist_data_envelope(envelope)

    upsert.assert_called_once()
    assert wait_for_persist(PIPELINE_ID, "inventory", timeout=0.1) is True

    persist_data_envelope(envelope)
    upsert.assert_called_once()


def test_validate_data_inventory_envelope_schema():
    from app.messaging.schema_registry import validate_envelope

    envelope = JobEnvelope.create(
        job_type=JobType.DATA_INVENTORY_SYNCED,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={
            "data": {"stage": "inventory", "sections": {}, "summary": {}},
            "run_params": {"reason": "test"},
        },
        source_service="platform-inventory",
    )
    validate_envelope(envelope, topic=TOPIC_DATA_INVENTORY_SYNCED)


def test_validate_data_envelope_with_null_token(monkeypatch):
    monkeypatch.setenv("KAFKA_SCHEMA_VALIDATION_ENABLED", "true")

    from app.messaging.schema_registry import validate_envelope

    envelope = JobEnvelope.create(
        job_type=JobType.DATA_INVENTORY_SYNCED,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={
            "data": {"stage": "inventory", "sections": {}, "summary": {}},
            "run_params": {
                "token": None,
                "type_list": None,
                "scope_components": None,
                "scope_resource_types": None,
                "reason": "manual_api",
            },
        },
        source_service="platform-inventory",
    )
    validate_envelope(envelope, topic=TOPIC_DATA_INVENTORY_SYNCED)


@patch("app.messaging.data_producer.publish_envelope_safe", return_value=True)
def test_publish_stage_data(mock_publish, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")
    monkeypatch.setenv("KAFKA_DATA_PIPELINE_ENABLED", "true")

    from app.messaging.data_producer import publish_stage_data

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
    call_args = mock_publish.call_args
    assert call_args.kwargs["topic"] == TOPIC_DATA_INVENTORY_SYNCED


def test_topic_manifest_includes_data_topics():
    from app.messaging.topic_config import topic_specs
    from app.messaging.topics import TOPIC_API_COST_REQUESTED, TOPIC_API_DEAD_LETTER

    names = {spec.name for spec in topic_specs()}
    assert TOPIC_DATA_INVENTORY_SYNCED in names
    assert "data.analysis.completed" in names
    assert TOPIC_API_COST_REQUESTED in names
    assert TOPIC_API_DEAD_LETTER in names
    assert len(names) == 17


def test_schema_bindings_cover_data_topics():
    from app.messaging.schema_registry import topic_schema_bindings
    from app.messaging.topic_config import topic_specs

    bindings = topic_schema_bindings()
    for spec in topic_specs():
        assert spec.name in bindings

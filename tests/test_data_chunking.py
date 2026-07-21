"""Tests for Kafka data payload chunking and reassembly."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.messaging.data_chunking import (
    ChunkAssembler,
    merge_chunked_data,
    plan_data_chunks,
)
from app.messaging.job_envelope import JobEnvelope, JobType

SUBSCRIPTION_ID = str(uuid.uuid4()).lower()
PIPELINE_ID = str(uuid.uuid4())


def _large_cost_by_resource(count: int) -> dict[str, dict]:
    return {
        f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-{i}": {
            "pretax_cost": float(i),
            "service_name": "Virtual Machines",
            "currency": "USD",
            "resource_name": f"vm-{i}",
        }
        for i in range(count)
    }


def test_plan_data_chunks_small_payload_unchanged():
    payload = {
        "stage": "cost",
        "sections": {"cost_meta": {"month": "2026-07"}},
        "summary": {"cost_by_service": 1},
    }
    plans = plan_data_chunks(payload, {}, target_bytes=1_000_000)
    assert len(plans) == 1
    assert "chunk" not in plans[0]
    assert plans[0]["data"] == payload


def test_plan_data_chunks_splits_large_cost_by_resource():
    payload = {
        "stage": "cost",
        "sections": {
            "cost_meta": {"month": "2026-07"},
            "cost_by_resource": _large_cost_by_resource(1200),
        },
        "summary": {"cost_by_resource": 1200},
    }
    plans = plan_data_chunks(payload, {}, target_bytes=80_000)
    assert len(plans) > 1
    assert all("chunk" in plan for plan in plans)
    batch_ids = {plan["chunk"]["batch_id"] for plan in plans}
    assert len(batch_ids) == 1
    assert plans[0]["chunk"]["chunk_index"] == 0
    assert plans[-1]["chunk"]["total_chunks"] == len(plans)
    assert plans[-1]["data"]["summary"] == payload["summary"]


def test_merge_chunked_data_round_trip():
    original = {
        "stage": "cost",
        "sections": {
            "cost_meta": {"month": "2026-07"},
            "cost_by_resource": _large_cost_by_resource(500),
            "cost_by_service": {"Virtual Machines": 100.0},
        },
        "summary": {"cost_by_resource": 500},
    }
    plans = plan_data_chunks(original, {}, target_bytes=60_000)
    merged = merge_chunked_data([plan["data"] for plan in plans])
    assert merged["stage"] == original["stage"]
    assert merged["summary"] == original["summary"]
    assert merged["sections"]["cost_meta"] == original["sections"]["cost_meta"]
    assert merged["sections"]["cost_by_service"] == original["sections"]["cost_by_service"]
    assert merged["sections"]["cost_by_resource"] == original["sections"]["cost_by_resource"]


def test_validate_chunked_data_envelope_schema():
    from app.messaging.schema_registry import validate_envelope

    envelope = JobEnvelope.create(
        job_type=JobType.DATA_COST_SYNCED,
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        payload={
            "data": {"stage": "cost", "sections": {"cost_meta": {"month": "2026-07"}}, "summary": {}},
            "run_params": {"reason": "test"},
            "chunk": {"batch_id": str(uuid.uuid4()), "chunk_index": 0, "total_chunks": 2},
        },
        source_service="platform-cost",
    )
    validate_envelope(envelope, topic="data.cost.synced")


def test_chunk_assembler_waits_until_complete():
    assembler = ChunkAssembler()
    batch_id = str(uuid.uuid4())
    chunks = [
        {
            "stage": "cost",
            "sections": {"cost_by_resource": {"a": {"pretax_cost": 1.0}}},
            "summary": {},
        },
        {
            "stage": "cost",
            "sections": {"cost_by_resource": {"b": {"pretax_cost": 2.0}}},
            "summary": {"cost_by_resource": 2},
        },
    ]

    for index, data in enumerate(chunks):
        envelope = JobEnvelope.create(
            job_type=JobType.DATA_COST_SYNCED,
            subscription_id=SUBSCRIPTION_ID,
            pipeline_id=PIPELINE_ID,
            payload={
                "data": data,
                "run_params": {},
                "chunk": {
                    "batch_id": batch_id,
                    "chunk_index": index,
                    "total_chunks": len(chunks),
                },
            },
            source_service="platform-cost",
        )
        merged = assembler.ingest(envelope)
        if index < len(chunks) - 1:
            assert merged is None
        else:
            assert merged is not None
            assert merged["sections"]["cost_by_resource"]["a"]["pretax_cost"] == 1.0
            assert merged["sections"]["cost_by_resource"]["b"]["pretax_cost"] == 2.0
            assert merged["summary"]["cost_by_resource"] == 2


@patch("app.messaging.data_producer.publish_envelope_safe", return_value=True)
def test_publish_stage_data_chunks_large_payload(mock_publish, monkeypatch):
    monkeypatch.setenv("KAFKA_ENABLED", "true")
    monkeypatch.setenv("MICROSERVICES_ONLY", "1")
    monkeypatch.setenv("KAFKA_DATA_PIPELINE_ENABLED", "true")

    from app.messaging.data_producer import publish_stage_data

    payload = {
        "stage": "cost",
        "sections": {"cost_by_resource": _large_cost_by_resource(5000)},
        "summary": {"cost_by_resource": 5000},
    }
    ok = publish_stage_data(
        "cost",
        subscription_id=SUBSCRIPTION_ID,
        pipeline_id=PIPELINE_ID,
        data_payload=payload,
        source_service="platform-cost",
        run_params={"reason": "test"},
    )
    assert ok is True
    assert mock_publish.call_count > 1
    first_envelope = mock_publish.call_args_list[0].args[0]
    assert "chunk" in first_envelope.payload

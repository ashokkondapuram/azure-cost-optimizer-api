"""Kafka consumers that persist data.* topic payloads to PostgreSQL."""

from __future__ import annotations

import structlog

from app.messaging.config import kafka_data_pipeline_enabled, kafka_pipeline_dispatch_enabled
from app.messaging.data_chunking import get_chunk_assembler
from app.messaging.data_persist import persist_data_envelope
from app.messaging.data_topics import all_data_topic_names
from app.messaging.job_envelope import JobEnvelope, JobType
from app.messaging.kafka_client import start_consumer_loop
from app.messaging.sync_producer import publish_next_stage, publish_pipeline_completed
from app.messaging.topic_config import data_topics_for_service

log = structlog.get_logger(__name__)

_DATA_JOB_STAGE = {
    JobType.DATA_INVENTORY_SYNCED: "inventory",
    JobType.DATA_COST_SYNCED: "cost",
    JobType.DATA_METRICS_SYNCED: "metrics",
    JobType.DATA_ANALYSIS_COMPLETED: "analysis",
}


def _run_params(envelope: JobEnvelope) -> dict:
    payload = envelope.payload or {}
    run_params = payload.get("run_params")
    return dict(run_params) if isinstance(run_params, dict) else {}


def _envelope_with_merged_data(envelope: JobEnvelope, merged_data: dict) -> JobEnvelope:
    payload = dict(envelope.payload or {})
    payload["data"] = merged_data
    payload.pop("chunk", None)
    return JobEnvelope(
        job_id=envelope.job_id,
        job_type=envelope.job_type,
        subscription_id=envelope.subscription_id,
        pipeline_id=envelope.pipeline_id,
        payload=payload,
        created_at=envelope.created_at,
        source_service=envelope.source_service,
        idempotency_key=envelope.idempotency_key,
    )


def _handle_data_message(envelope: JobEnvelope, topic: str) -> None:
    from app.sync_orchestrator import (
        mark_pipeline_complete_db,
        mark_stage_done_db,
        pipeline_row_still_active,
    )

    stage = _DATA_JOB_STAGE.get(envelope.job_type)
    if stage is None:
        log.warning("data_consumer.unknown_job_type", topic=topic, job_type=envelope.job_type.value)
        return

    merged_data = get_chunk_assembler().ingest(envelope)
    if merged_data is None:
        return

    envelope = _envelope_with_merged_data(envelope, merged_data)

    sub = envelope.subscription_id
    pipeline_id = envelope.pipeline_id
    source_service = envelope.source_service

    persist_data_envelope(envelope)

    if not pipeline_row_still_active(sub, pipeline_id):
        return

    data_payload = (envelope.payload or {}).get("data") or {}
    summary = data_payload.get("summary") if isinstance(data_payload, dict) else {}
    mark_stage_done_db(pipeline_id, sub, stage, result=summary or {}, source_service=source_service)

    if stage == "analysis":
        mark_pipeline_complete_db(pipeline_id, sub, source_service=source_service)
        publish_pipeline_completed(
            subscription_id=sub,
            pipeline_id=pipeline_id,
            status="completed",
            source_service=source_service,
        )
        return

    publish_next_stage(
        stage,
        subscription_id=sub,
        pipeline_id=pipeline_id,
        run_params=_run_params(envelope),
        source_service=source_service,
    )
    log.info("data_consumer.advanced_pipeline", stage=stage, pipeline_id=pipeline_id, topic=topic)


def start_data_persistence_consumer(service_id: str) -> None:
    if not kafka_pipeline_dispatch_enabled() or not kafka_data_pipeline_enabled():
        return

    topics = data_topics_for_service(service_id)
    if not topics:
        return

    def _handler(envelope: JobEnvelope, topic: str) -> None:
        if topic not in all_data_topic_names():
            return
        _handle_data_message(envelope, topic)

    start_consumer_loop(
        service_id=f"{service_id}.persist",
        topics=topics,
        handler=_handler,
    )

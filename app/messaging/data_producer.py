"""Publish sync data payloads to Kafka data topics."""

from __future__ import annotations

import structlog

from app.messaging.config import kafka_data_pipeline_enabled
from app.messaging.data_chunking import plan_data_chunks
from app.messaging.data_topics import data_job_type_for_stage, data_topic_for_job_type
from app.messaging.job_envelope import JobEnvelope, JobType
from app.messaging.kafka_client import publish_envelope_safe

log = structlog.get_logger(__name__)


def publish_stage_data(
    stage: str,
    *,
    subscription_id: str,
    pipeline_id: str,
    data_payload: dict,
    source_service: str,
    run_params: dict | None = None,
) -> bool:
    """Publish fetched stage data to the matching data.* topic."""
    if not kafka_data_pipeline_enabled():
        return False

    job_type = data_job_type_for_stage(stage)
    if job_type is None:
        raise ValueError(f"No data topic for stage: {stage}")

    topic = data_topic_for_job_type(job_type)
    params = dict(run_params or {})
    chunk_plans = plan_data_chunks(data_payload, params)
    published = 0

    for plan in chunk_plans:
        envelope_payload: dict = {
            "data": plan["data"],
            "run_params": params,
        }
        chunk_meta = plan.get("chunk")
        if chunk_meta:
            envelope_payload["chunk"] = chunk_meta

        envelope = JobEnvelope.create(
            job_type=job_type,
            subscription_id=subscription_id,
            pipeline_id=pipeline_id,
            payload=envelope_payload,
            source_service=source_service,
        )
        if chunk_meta:
            batch_id = chunk_meta.get("batch_id", "")
            chunk_index = chunk_meta.get("chunk_index", 0)
            envelope.idempotency_key = (
                f"{pipeline_id}:{job_type.value}:{batch_id}:{chunk_index}"
            )

        if not publish_envelope_safe(envelope, topic=topic):
            log.error(
                "data_pipeline.publish_chunk_failed",
                stage=stage,
                topic=topic,
                pipeline_id=pipeline_id,
                chunk_index=chunk_meta.get("chunk_index") if chunk_meta else 0,
                total_chunks=chunk_meta.get("total_chunks") if chunk_meta else 1,
            )
            return False
        published += 1

    if published:
        log.info(
            "data_pipeline.published",
            stage=stage,
            topic=topic,
            pipeline_id=pipeline_id,
            subscription_id=subscription_id,
            chunks=published,
        )
    return published > 0


def publish_data_job(
    job_type: JobType,
    *,
    subscription_id: str,
    pipeline_id: str,
    payload: dict,
    source_service: str,
) -> bool:
    if not kafka_data_pipeline_enabled():
        return False
    envelope = JobEnvelope.create(
        job_type=job_type,
        subscription_id=subscription_id,
        pipeline_id=pipeline_id,
        payload=dict(payload or {}),
        source_service=source_service,
    )
    topic = data_topic_for_job_type(job_type)
    return publish_envelope_safe(envelope, topic=topic)

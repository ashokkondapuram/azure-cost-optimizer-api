"""Publish sync pipeline jobs to Kafka."""

from __future__ import annotations

import structlog

from app.messaging.config import kafka_pipeline_dispatch_enabled
from app.messaging.job_envelope import JobEnvelope, JobType
from app.messaging.kafka_client import publish_envelope_safe
from app.messaging.topics import topic_for_job_type

log = structlog.get_logger(__name__)


def publish_sync_job(
    job_type: JobType,
    *,
    subscription_id: str,
    pipeline_id: str,
    payload: dict | None = None,
    source_service: str = "platform-gateway",
) -> bool:
    """Publish a sync stage job. Returns False when Kafka is disabled or publish fails."""
    if not kafka_pipeline_dispatch_enabled():
        return False

    envelope = JobEnvelope.create(
        job_type=job_type,
        subscription_id=subscription_id,
        pipeline_id=pipeline_id,
        payload=dict(payload or {}),
        source_service=source_service,
    )
    topic = topic_for_job_type(job_type)
    ok = publish_envelope_safe(envelope, topic=topic)
    if ok:
        log.info(
            "sync_pipeline.job_published",
            job_type=job_type.value,
            pipeline_id=pipeline_id,
            subscription_id=subscription_id,
            topic=topic,
        )
    return ok


def publish_inventory_requested(
    *,
    subscription_id: str,
    pipeline_id: str,
    run_params: dict,
    source_service: str = "platform-gateway",
) -> bool:
    return publish_sync_job(
        JobType.SYNC_INVENTORY,
        subscription_id=subscription_id,
        pipeline_id=pipeline_id,
        payload={"run_params": run_params},
        source_service=source_service,
    )


def publish_next_stage(
    completed_stage: str,
    *,
    subscription_id: str,
    pipeline_id: str,
    run_params: dict,
    source_service: str,
) -> bool:
    """Publish the next pipeline stage after *completed_stage* completes."""
    from app.messaging.topics import next_job_type_after_stage

    next_type = next_job_type_after_stage(completed_stage)
    if next_type is None:
        return publish_pipeline_completed(
            subscription_id=subscription_id,
            pipeline_id=pipeline_id,
            status="completed",
            source_service=source_service,
        )
    return publish_sync_job(
        next_type,
        subscription_id=subscription_id,
        pipeline_id=pipeline_id,
        payload={"run_params": run_params},
        source_service=source_service,
    )


def publish_pipeline_completed(
    *,
    subscription_id: str,
    pipeline_id: str,
    status: str,
    source_service: str,
    error: str | None = None,
) -> bool:
    return publish_sync_job(
        JobType.PIPELINE_COMPLETED,
        subscription_id=subscription_id,
        pipeline_id=pipeline_id,
        payload={"status": status, "error": error},
        source_service=source_service,
    )


def publish_pipeline_status(
    *,
    subscription_id: str,
    pipeline_id: str,
    stage: str,
    progress_pct: int,
    status: str,
    source_service: str,
    error: str | None = None,
) -> bool:
    return publish_sync_job(
        JobType.PIPELINE_STATUS,
        subscription_id=subscription_id,
        pipeline_id=pipeline_id,
        payload={
            "stage": stage,
            "progress_pct": progress_pct,
            "status": status,
            "error": error,
        },
        source_service=source_service,
    )

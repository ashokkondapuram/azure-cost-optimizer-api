"""Kafka consumer for sync.pipeline.status and sync.pipeline.completed."""

from __future__ import annotations

import structlog

from app.messaging.config import kafka_pipeline_dispatch_enabled
from app.messaging.job_envelope import JobEnvelope, JobType
from app.messaging.kafka_client import start_consumer_loop
from app.messaging.topics import TOPIC_SYNC_PIPELINE_COMPLETED, TOPIC_SYNC_PIPELINE_STATUS

log = structlog.get_logger(__name__)

_PROGRESS_TOPICS = (
    TOPIC_SYNC_PIPELINE_STATUS,
    TOPIC_SYNC_PIPELINE_COMPLETED,
)


def _handle_progress_message(envelope: JobEnvelope, topic: str) -> None:
    from app.sync_progress import apply_kafka_completed_event, apply_kafka_status_event

    if topic == TOPIC_SYNC_PIPELINE_STATUS:
        if envelope.job_type != JobType.PIPELINE_STATUS:
            log.warning(
                "sync_progress.unexpected_job_type",
                topic=topic,
                expected=JobType.PIPELINE_STATUS.value,
                got=envelope.job_type.value,
                pipeline_id=envelope.pipeline_id,
            )
            return
        apply_kafka_status_event(envelope)
        return

    if topic == TOPIC_SYNC_PIPELINE_COMPLETED:
        if envelope.job_type != JobType.PIPELINE_COMPLETED:
            log.warning(
                "sync_progress.unexpected_job_type",
                topic=topic,
                expected=JobType.PIPELINE_COMPLETED.value,
                got=envelope.job_type.value,
                pipeline_id=envelope.pipeline_id,
            )
            return
        apply_kafka_completed_event(envelope)
        return

    log.warning("sync_progress.unknown_topic", topic=topic, pipeline_id=envelope.pipeline_id)


def start_pipeline_progress_consumer(service_id: str = "platform-inventory") -> None:
    """Start the pipeline progress aggregation consumer (platform-inventory only)."""
    if not kafka_pipeline_dispatch_enabled():
        return
    if service_id != "platform-inventory":
        return

    start_consumer_loop(
        service_id=f"{service_id}.progress",
        topics=list(_PROGRESS_TOPICS),
        handler=_handle_progress_message,
    )
    log.info(
        "sync_progress.consumer_started",
        service_id=service_id,
        topics=list(_PROGRESS_TOPICS),
    )

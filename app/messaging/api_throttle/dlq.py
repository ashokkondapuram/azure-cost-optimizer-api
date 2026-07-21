"""Dead-letter handling for failed api.* jobs."""

from __future__ import annotations

import structlog

from app.messaging.api_throttle import metrics as throttle_metrics
from app.messaging.api_throttle.batch_registry import get_batch_registry
from app.messaging.api_throttle.config import kafka_api_dlq_enabled
from app.messaging.api_throttle.topics import TOPIC_API_DEAD_LETTER
from app.messaging.job_envelope import JobEnvelope, JobType
from app.messaging.kafka_client import publish_envelope_safe
from app.sync_orchestrator import mark_pipeline_failed_db

log = structlog.get_logger(__name__)


def publish_dead_letter(
    envelope: JobEnvelope,
    *,
    error: str,
    original_topic: str,
) -> bool:
    if not kafka_api_dlq_enabled():
        return False

    payload = envelope.payload or {}
    phase = str(payload.get("phase") or "unknown")
    api_kind = envelope.job_type.value.split(".")[1] if "." in envelope.job_type.value else "unknown"
    batch_id = str(payload.get("batch_id") or "")

    if batch_id:
        get_batch_registry().mark_failed(batch_id, error)

    dlq = JobEnvelope.create(
        job_type=JobType.API_DEAD_LETTER,
        subscription_id=envelope.subscription_id,
        pipeline_id=envelope.pipeline_id,
        payload={
            "original_topic": original_topic,
            "original_job_type": envelope.job_type.value,
            "original_job_id": envelope.job_id,
            "phase": phase,
            "batch_id": batch_id,
            "error": error[:2000],
            "run_params": dict(payload.get("run_params") or {}),
        },
        source_service=envelope.source_service,
    )
    dlq.idempotency_key = f"{envelope.pipeline_id}:dlq:{envelope.job_id}"

    published = publish_envelope_safe(dlq, topic=TOPIC_API_DEAD_LETTER)
    if published:
        throttle_metrics.get_metrics().record_dlq(
            api_kind=api_kind,
            phase=phase,
            pipeline_id=envelope.pipeline_id,
        )
    return published


def handle_dead_letter(envelope: JobEnvelope, topic: str) -> None:
    payload = envelope.payload or {}
    error = str(payload.get("error") or "api job failed")
    original_job_type = str(payload.get("original_job_type") or "")
    phase = str(payload.get("phase") or "unknown")

    stage = "cost"
    if "metrics" in original_job_type:
        stage = "metrics"
    elif "inventory" in original_job_type:
        stage = "inventory"

    log.error(
        "api_throttle.dlq_received",
        topic=topic,
        pipeline_id=envelope.pipeline_id,
        subscription_id=envelope.subscription_id,
        stage=stage,
        phase=phase,
        error=error[:300],
    )

    mark_pipeline_failed_db(
        envelope.pipeline_id,
        envelope.subscription_id,
        stage,
        f"API throttle DLQ ({phase}): {error[:500]}",
        source_service=envelope.source_service,
    )

"""Run sync stages via Azure fetch → Redpanda data topics → PostgreSQL persist."""

from __future__ import annotations

from typing import Any, Callable

import structlog

from app.messaging.config import kafka_data_pipeline_enabled
from app.messaging.data_ack import wait_for_persist
from app.messaging.data_collector import collect_sync_data
from app.messaging.data_producer import publish_stage_data
from app.messaging.job_envelope import JobEnvelope

log = structlog.get_logger(__name__)


def run_stage_via_data_pipeline(
    envelope: JobEnvelope,
    *,
    stage: str,
    source_service: str,
    run_params: dict[str, Any],
    fetch_fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Fetch from Azure, publish to data topic, wait for DB persist consumer."""
    with collect_sync_data(stage) as collector:
        result = fetch_fn()
        collector.summary = dict(result) if isinstance(result, dict) else {"result": result}

    data_payload = collector.to_payload()
    published = publish_stage_data(
        stage,
        subscription_id=envelope.subscription_id,
        pipeline_id=envelope.pipeline_id,
        data_payload=data_payload,
        source_service=source_service,
        run_params=run_params,
    )
    if not published:
        from app.messaging.kafka_errors import KafkaPublishExhaustedError
        from app.sync_orchestrator import mark_pipeline_publish_failed_db

        error = f"Failed to publish data.{stage}.synced for pipeline {envelope.pipeline_id}"
        mark_pipeline_publish_failed_db(
            envelope.pipeline_id,
            envelope.subscription_id,
            stage,
            error,
            source_service=source_service,
        )
        raise KafkaPublishExhaustedError(error)

    if not wait_for_persist(envelope.pipeline_id, stage, timeout=900.0):
        raise TimeoutError(
            f"Timed out waiting for {stage} data persist (pipeline_id={envelope.pipeline_id})"
        )

    log.info(
        "sync_stage.data_pipeline_complete",
        stage=stage,
        pipeline_id=envelope.pipeline_id,
        subscription_id=envelope.subscription_id,
    )
    return collector.summary


def maybe_use_data_pipeline(
    envelope: JobEnvelope,
    *,
    stage: str,
    source_service: str,
    run_params: dict[str, Any],
    fetch_fn: Callable[[], dict[str, Any]],
    direct_fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    if kafka_data_pipeline_enabled():
        return run_stage_via_data_pipeline(
            envelope,
            stage=stage,
            source_service=source_service,
            run_params=run_params,
            fetch_fn=fetch_fn,
        )
    return direct_fn()

"""Kafka consumer handlers for sync pipeline orchestration (sync.* topics)."""

from __future__ import annotations

import structlog

from app.messaging.config import kafka_data_pipeline_enabled, kafka_pipeline_dispatch_enabled
from app.messaging.job_envelope import JobEnvelope, JobType
from app.messaging.kafka_client import start_consumer_loop
from app.messaging.sync_producer import publish_next_stage, publish_pipeline_completed
from app.messaging.sync_stages import (
    run_analysis_stage,
    run_cost_stage,
    run_inventory_stage,
    run_metrics_stage,
)
from app.messaging.topic_config import orchestration_topics_for_service

log = structlog.get_logger(__name__)

_STAGE_BY_JOB: dict[JobType, str] = {
    JobType.SYNC_INVENTORY: "inventory",
    JobType.SYNC_COST: "cost",
    JobType.SYNC_METRICS: "metrics",
    JobType.SYNC_ANALYSIS: "analysis",
}


def _run_params(envelope: JobEnvelope) -> dict:
    payload = envelope.payload or {}
    run_params = payload.get("run_params")
    return dict(run_params) if isinstance(run_params, dict) else {}


def _handle_stage(
    envelope: JobEnvelope,
    *,
    stage: str,
    runner,
    source_service: str,
) -> None:
    run_params = _run_params(envelope)
    try:
        runner(envelope, source_service=source_service)
    except Exception:
        # Stage runners call mark_pipeline_failed_db; do not emit pipeline.completed.
        raise

    if kafka_data_pipeline_enabled():
        return

    if stage == "analysis":
        publish_pipeline_completed(
            subscription_id=envelope.subscription_id,
            pipeline_id=envelope.pipeline_id,
            status="completed",
            source_service=source_service,
        )
        return

    publish_next_stage(
        stage,
        subscription_id=envelope.subscription_id,
        pipeline_id=envelope.pipeline_id,
        run_params=run_params,
        source_service=source_service,
    )


def _make_handler(stage: str, runner, source_service: str):
    def _handler(envelope: JobEnvelope, topic: str) -> None:
        expected = _STAGE_BY_JOB.get(envelope.job_type)
        if expected != stage:
            log.warning(
                "sync_consumer.unexpected_job_type",
                expected=stage,
                got=envelope.job_type.value,
                pipeline_id=envelope.pipeline_id,
                topic=topic,
            )
            return
        _handle_stage(envelope, stage=stage, runner=runner, source_service=source_service)

    return _handler


def _start_service_consumer(service_id: str, stage: str, runner) -> None:
    if not kafka_pipeline_dispatch_enabled():
        return
    topics = orchestration_topics_for_service(service_id)
    if not topics:
        return
    start_consumer_loop(
        service_id=service_id,
        topics=topics,
        handler=_make_handler(stage, runner, service_id),
    )


def start_inventory_consumer() -> None:
    _start_service_consumer("platform-inventory", "inventory", run_inventory_stage)


def start_cost_consumer() -> None:
    _start_service_consumer("platform-cost", "cost", run_cost_stage)


def start_metrics_consumer() -> None:
    _start_service_consumer("platform-metrics", "metrics", run_metrics_stage)


def start_analysis_consumer() -> None:
    _start_service_consumer("platform-analysis", "analysis", run_analysis_stage)

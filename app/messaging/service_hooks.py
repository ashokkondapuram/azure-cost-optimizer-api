"""Service startup hooks for Kafka sync pipeline consumers."""

from __future__ import annotations

import structlog

from app.messaging.config import (
    kafka_ensure_topics_on_startup,
    kafka_pipeline_dispatch_enabled,
)
from app.messaging.topic_config import consumer_group_for_service, consumer_topics_for_service

log = structlog.get_logger(__name__)


def start_kafka_consumers_for_service(service_id: str) -> None:
    """Start the Kafka consumer loop appropriate for *service_id*.

    Never raises — Kafka unavailability must not block uvicorn health checks.
    """
    if service_id == "platform-inventory":
        try:
            from app.sync_orchestrator import resume_incomplete_pipelines

            resumed = resume_incomplete_pipelines(service_id=service_id)
            if resumed:
                log.info(
                    "kafka.pipelines_resumed_on_startup",
                    service_id=service_id,
                    count=len(resumed),
                    pipeline_ids=resumed,
                )
        except Exception:
            log.exception(
                "kafka.pipeline_resume_failed",
                service_id=service_id,
                hint="Incomplete pipelines remain in DB; poll GET /sync/pipeline to retry.",
            )

    if not kafka_pipeline_dispatch_enabled():
        log.debug("kafka.hooks_skipped", service_id=service_id)
        return

    if kafka_ensure_topics_on_startup():
        try:
            from app.messaging.topic_provision import ensure_schemas_registered, ensure_topics_provisioned

            ensure_topics_provisioned()
            ensure_schemas_registered()
        except Exception:
            log.exception("kafka.startup_provision_failed", service_id=service_id)

    try:
        from app.messaging import data_consumers, sync_consumers

        data_consumers.start_data_persistence_consumer(service_id)

        starters = {
            "platform-inventory": sync_consumers.start_inventory_consumer,
            "platform-cost": sync_consumers.start_cost_consumer,
            "platform-metrics": sync_consumers.start_metrics_consumer,
            "platform-analysis": sync_consumers.start_analysis_consumer,
        }
        starter = starters.get(service_id)
        if starter is not None:
            starter()
        else:
            log.debug("kafka.no_orchestration_consumer", service_id=service_id)

        try:
            from app.messaging.sync_progress_consumer import start_pipeline_progress_consumer

            start_pipeline_progress_consumer(service_id)
        except Exception:
            log.exception("kafka.progress_consumer_start_failed", service_id=service_id)

        try:
            from app.messaging.api_throttle.consumers import start_api_throttle_consumers

            start_api_throttle_consumers(service_id)
        except Exception:
            log.exception(
                "kafka.api_throttle_start_failed",
                service_id=service_id,
            )

        topics = consumer_topics_for_service(service_id)
        log.info(
            "kafka.consumers_registered",
            service_id=service_id,
            topics=topics,
            consumer_group=consumer_group_for_service(service_id),
        )
    except Exception:
        log.exception(
            "kafka.consumer_start_failed",
            service_id=service_id,
            hint="Service will continue without Kafka consumer; retry on restart.",
        )

"""Kafka consumer loops for api.* throttling."""

from __future__ import annotations

import structlog

from app.messaging.api_throttle.aggregator import handle_api_completed
from app.messaging.api_throttle.config import (
    api_aggregate_consumer_group_suffix,
    api_consumer_group_suffix,
    kafka_api_dlq_enabled,
    kafka_api_throttle_enabled,
)
from app.messaging.api_throttle.dlq import handle_dead_letter
from app.messaging.api_throttle.topics import (
    TOPIC_API_DEAD_LETTER,
    completed_topics_for_service,
    requested_topics_for_service,
)
from app.messaging.api_throttle.worker import handle_api_requested
from app.messaging.config import kafka_consumer_group, kafka_pipeline_dispatch_enabled
from app.messaging.job_envelope import JobEnvelope, JobType
from app.messaging.kafka_client import start_consumer_loop

log = structlog.get_logger(__name__)

_COMPLETED_JOB_TYPES = {
    JobType.API_COST_COMPLETED,
    JobType.API_METRICS_COMPLETED,
    JobType.API_INVENTORY_COMPLETED,
}


def _api_worker_group(service_id: str, api_kind: str) -> str:
    return f"{kafka_consumer_group(service_id)}.{api_consumer_group_suffix(api_kind)}"


def _api_aggregate_group(service_id: str, api_kind: str) -> str:
    return f"{kafka_consumer_group(service_id)}.{api_aggregate_consumer_group_suffix(api_kind)}"


def start_api_worker_consumer(service_id: str) -> None:
    if not kafka_pipeline_dispatch_enabled() or not kafka_api_throttle_enabled():
        return

    topics = requested_topics_for_service(service_id)
    if not topics:
        return

    api_kind = {
        "platform-cost": "cost",
        "platform-metrics": "metrics",
        "platform-inventory": "inventory",
    }.get(service_id, "unknown")

    def _handler(envelope: JobEnvelope, topic: str) -> None:
        handle_api_requested(envelope, topic)

    start_consumer_loop(
        service_id=f"{service_id}.api-worker",
        topics=topics,
        handler=_handler,
        consumer_group=_api_worker_group(service_id, api_kind),
    )
    log.info(
        "api_throttle.worker_started",
        service_id=service_id,
        topics=topics,
        consumer_group=_api_worker_group(service_id, api_kind),
    )


def start_api_aggregate_consumer(service_id: str) -> None:
    if not kafka_pipeline_dispatch_enabled() or not kafka_api_throttle_enabled():
        return

    topics = completed_topics_for_service(service_id)
    if not topics:
        return

    api_kind = {
        "platform-cost": "cost",
        "platform-metrics": "metrics",
        "platform-inventory": "inventory",
    }.get(service_id, "unknown")

    def _handler(envelope: JobEnvelope, topic: str) -> None:
        if envelope.job_type not in _COMPLETED_JOB_TYPES:
            log.warning(
                "api_throttle.unexpected_completed_type",
                topic=topic,
                job_type=envelope.job_type.value,
            )
            return
        handle_api_completed(envelope)

    start_consumer_loop(
        service_id=f"{service_id}.api-aggregate",
        topics=topics,
        handler=_handler,
        consumer_group=_api_aggregate_group(service_id, api_kind),
    )
    log.info(
        "api_throttle.aggregate_started",
        service_id=service_id,
        topics=topics,
        consumer_group=_api_aggregate_group(service_id, api_kind),
    )


def start_api_dlq_consumer(service_id: str) -> None:
    if not kafka_pipeline_dispatch_enabled() or not kafka_api_throttle_enabled():
        return
    if not kafka_api_dlq_enabled():
        return

    def _handler(envelope: JobEnvelope, topic: str) -> None:
        if envelope.job_type != JobType.API_DEAD_LETTER:
            return
        handle_dead_letter(envelope, topic)

    start_consumer_loop(
        service_id=f"{service_id}.api-dlq",
        topics=[TOPIC_API_DEAD_LETTER],
        handler=_handler,
        consumer_group=f"{kafka_consumer_group(service_id)}.api.dlq",
    )
    log.info(
        "api_throttle.dlq_consumer_started",
        service_id=service_id,
        topic=TOPIC_API_DEAD_LETTER,
    )


def start_api_throttle_consumers(service_id: str) -> None:
    start_api_worker_consumer(service_id)
    start_api_aggregate_consumer(service_id)
    start_api_dlq_consumer(service_id)

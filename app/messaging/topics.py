"""Kafka topic names for sync pipeline coordination."""

from __future__ import annotations

from app.messaging.job_envelope import JobType
from app.messaging.topic_config import all_sync_topic_names

# Stage request topics — one consumer group per platform service.
TOPIC_SYNC_INVENTORY_REQUESTED = "sync.inventory.requested"
TOPIC_SYNC_COST_REQUESTED = "sync.cost.requested"
TOPIC_SYNC_METRICS_REQUESTED = "sync.metrics.requested"
TOPIC_SYNC_ANALYSIS_REQUESTED = "sync.analysis.requested"

# Status / completion events (optional subscribers: gateway SSE, monitoring).
TOPIC_SYNC_PIPELINE_STATUS = "sync.pipeline.status"
TOPIC_SYNC_PIPELINE_COMPLETED = "sync.pipeline.completed"

# API throttle queue — rate-limited Azure API work (partition key: subscription_id).
TOPIC_API_COST_REQUESTED = "api.cost.requested"
TOPIC_API_COST_COMPLETED = "api.cost.completed"
TOPIC_API_METRICS_REQUESTED = "api.metrics.requested"
TOPIC_API_METRICS_COMPLETED = "api.metrics.completed"
TOPIC_API_INVENTORY_REQUESTED = "api.inventory.requested"
TOPIC_API_INVENTORY_COMPLETED = "api.inventory.completed"
TOPIC_API_DEAD_LETTER = "api.dead-letter"

API_TOPICS: tuple[str, ...] = (
    TOPIC_API_COST_REQUESTED,
    TOPIC_API_COST_COMPLETED,
    TOPIC_API_METRICS_REQUESTED,
    TOPIC_API_METRICS_COMPLETED,
    TOPIC_API_INVENTORY_REQUESTED,
    TOPIC_API_INVENTORY_COMPLETED,
    TOPIC_API_DEAD_LETTER,
)

SYNC_TOPICS: tuple[str, ...] = tuple(
    name
    for name in all_sync_topic_names()
    if name
) or (
    TOPIC_SYNC_INVENTORY_REQUESTED,
    TOPIC_SYNC_COST_REQUESTED,
    TOPIC_SYNC_METRICS_REQUESTED,
    TOPIC_SYNC_ANALYSIS_REQUESTED,
    TOPIC_SYNC_PIPELINE_STATUS,
    TOPIC_SYNC_PIPELINE_COMPLETED,
)

_JOB_TYPE_TO_TOPIC: dict[JobType, str] = {
    JobType.SYNC_INVENTORY: TOPIC_SYNC_INVENTORY_REQUESTED,
    JobType.SYNC_COST: TOPIC_SYNC_COST_REQUESTED,
    JobType.SYNC_METRICS: TOPIC_SYNC_METRICS_REQUESTED,
    JobType.SYNC_ANALYSIS: TOPIC_SYNC_ANALYSIS_REQUESTED,
    JobType.PIPELINE_STATUS: TOPIC_SYNC_PIPELINE_STATUS,
    JobType.PIPELINE_COMPLETED: TOPIC_SYNC_PIPELINE_COMPLETED,
}

_STAGE_TO_NEXT_JOB: dict[str, JobType] = {
    "inventory": JobType.SYNC_COST,
    "cost": JobType.SYNC_METRICS,
    "metrics": JobType.SYNC_ANALYSIS,
}


def topic_for_job_type(job_type: JobType) -> str:
    try:
        return _JOB_TYPE_TO_TOPIC[job_type]
    except KeyError as exc:
        raise ValueError(f"No topic mapped for job type: {job_type}") from exc


def next_job_type_after_stage(stage: str) -> JobType | None:
    return _STAGE_TO_NEXT_JOB.get(stage)

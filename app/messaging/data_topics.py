"""Kafka topic names for sync data plane (Azure fetch → Redpanda → PostgreSQL)."""

from __future__ import annotations

from app.messaging.job_envelope import JobType
from app.messaging.topic_config import all_sync_topic_names

TOPIC_DATA_INVENTORY_SYNCED = "data.inventory.synced"
TOPIC_DATA_COST_SYNCED = "data.cost.synced"
TOPIC_DATA_METRICS_SYNCED = "data.metrics.synced"
TOPIC_DATA_ANALYSIS_COMPLETED = "data.analysis.completed"

_DATA_JOB_TYPE_TO_TOPIC: dict[JobType, str] = {
    JobType.DATA_INVENTORY_SYNCED: TOPIC_DATA_INVENTORY_SYNCED,
    JobType.DATA_COST_SYNCED: TOPIC_DATA_COST_SYNCED,
    JobType.DATA_METRICS_SYNCED: TOPIC_DATA_METRICS_SYNCED,
    JobType.DATA_ANALYSIS_COMPLETED: TOPIC_DATA_ANALYSIS_COMPLETED,
}

_STAGE_TO_DATA_JOB: dict[str, JobType] = {
    "inventory": JobType.DATA_INVENTORY_SYNCED,
    "cost": JobType.DATA_COST_SYNCED,
    "metrics": JobType.DATA_METRICS_SYNCED,
    "analysis": JobType.DATA_ANALYSIS_COMPLETED,
}


def data_topic_for_job_type(job_type: JobType) -> str:
    try:
        return _DATA_JOB_TYPE_TO_TOPIC[job_type]
    except KeyError as exc:
        raise ValueError(f"No data topic mapped for job type: {job_type}") from exc


def data_job_type_for_stage(stage: str) -> JobType | None:
    return _STAGE_TO_DATA_JOB.get(stage)


def all_data_topic_names() -> tuple[str, ...]:
    return tuple(sorted(_DATA_JOB_TYPE_TO_TOPIC.values()))


def all_topic_names() -> tuple[str, ...]:
    return tuple(sorted(set(all_sync_topic_names()) | set(all_data_topic_names())))

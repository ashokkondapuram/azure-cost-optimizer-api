"""Kafka topic names and service bindings for API throttling."""

from __future__ import annotations

from app.messaging.job_envelope import JobType

TOPIC_API_COST_REQUESTED = "api.cost.requested"
TOPIC_API_COST_COMPLETED = "api.cost.completed"
TOPIC_API_METRICS_REQUESTED = "api.metrics.requested"
TOPIC_API_METRICS_COMPLETED = "api.metrics.completed"
TOPIC_API_INVENTORY_REQUESTED = "api.inventory.requested"
TOPIC_API_INVENTORY_COMPLETED = "api.inventory.completed"
TOPIC_API_DEAD_LETTER = "api.dead-letter"

# Aliases used by domain-centric modules.
TOPIC_API_MONITOR_REQUESTED = TOPIC_API_METRICS_REQUESTED
TOPIC_API_MONITOR_COMPLETED = TOPIC_API_METRICS_COMPLETED
TOPIC_API_RESOURCE_GRAPH_REQUESTED = TOPIC_API_INVENTORY_REQUESTED
TOPIC_API_RESOURCE_GRAPH_COMPLETED = TOPIC_API_INVENTORY_COMPLETED

API_THROTTLE_TOPICS: tuple[str, ...] = (
    TOPIC_API_COST_REQUESTED,
    TOPIC_API_COST_COMPLETED,
    TOPIC_API_METRICS_REQUESTED,
    TOPIC_API_METRICS_COMPLETED,
    TOPIC_API_INVENTORY_REQUESTED,
    TOPIC_API_INVENTORY_COMPLETED,
    TOPIC_API_DEAD_LETTER,
)

_JOB_TYPE_TO_TOPIC: dict[JobType, str] = {
    JobType.API_COST_REQUESTED: TOPIC_API_COST_REQUESTED,
    JobType.API_COST_COMPLETED: TOPIC_API_COST_COMPLETED,
    JobType.API_METRICS_REQUESTED: TOPIC_API_METRICS_REQUESTED,
    JobType.API_METRICS_COMPLETED: TOPIC_API_METRICS_COMPLETED,
    JobType.API_INVENTORY_REQUESTED: TOPIC_API_INVENTORY_REQUESTED,
    JobType.API_INVENTORY_COMPLETED: TOPIC_API_INVENTORY_COMPLETED,
    JobType.API_DEAD_LETTER: TOPIC_API_DEAD_LETTER,
}

_SERVICE_REQUESTED: dict[str, tuple[str, ...]] = {
    "platform-cost": (TOPIC_API_COST_REQUESTED,),
    "platform-metrics": (TOPIC_API_METRICS_REQUESTED,),
    "platform-inventory": (TOPIC_API_INVENTORY_REQUESTED,),
}

_SERVICE_COMPLETED: dict[str, tuple[str, ...]] = {
    "platform-cost": (TOPIC_API_COST_COMPLETED,),
    "platform-metrics": (TOPIC_API_METRICS_COMPLETED,),
    "platform-inventory": (TOPIC_API_INVENTORY_COMPLETED,),
}


def api_topic_for_job_type(job_type: JobType) -> str:
    try:
        return _JOB_TYPE_TO_TOPIC[job_type]
    except KeyError as exc:
        raise ValueError(f"No API topic mapped for job type: {job_type}") from exc


def requested_topics_for_service(service_id: str) -> list[str]:
    return list(_SERVICE_REQUESTED.get(service_id, ()))


def completed_topics_for_service(service_id: str) -> list[str]:
    return list(_SERVICE_COMPLETED.get(service_id, ()))


# Domain-centric helpers (cost_management → api.cost, etc.)
try:
    from app.messaging.api_throttle.envelope import ApiDomain

    _DOMAIN_REQUESTED = {
        ApiDomain.COST_MANAGEMENT: TOPIC_API_COST_REQUESTED,
        ApiDomain.MONITOR: TOPIC_API_MONITOR_REQUESTED,
        ApiDomain.RESOURCE_GRAPH: TOPIC_API_RESOURCE_GRAPH_REQUESTED,
    }
    _DOMAIN_COMPLETED = {
        ApiDomain.COST_MANAGEMENT: TOPIC_API_COST_COMPLETED,
        ApiDomain.MONITOR: TOPIC_API_MONITOR_COMPLETED,
        ApiDomain.RESOURCE_GRAPH: TOPIC_API_RESOURCE_GRAPH_COMPLETED,
    }

    def requested_topic_for_domain(domain: ApiDomain) -> str:
        return _DOMAIN_REQUESTED[domain]

    def completed_topic_for_domain(domain: ApiDomain) -> str:
        return _DOMAIN_COMPLETED[domain]
except Exception:
    pass

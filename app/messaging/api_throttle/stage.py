"""Stage integration for Kafka API throttling."""

from __future__ import annotations

import structlog

from app.messaging.api_throttle.config import kafka_api_throttle_enabled
from app.messaging.api_throttle.coordinator import enqueue_cost_api_jobs
from app.messaging.config import kafka_data_pipeline_enabled
from app.messaging.job_envelope import JobEnvelope

log = structlog.get_logger(__name__)


def maybe_run_cost_via_api_throttle(
    envelope: JobEnvelope,
    *,
    source_service: str,
    run_params: dict,
) -> bool:
    """Enqueue throttled cost API jobs instead of a monolithic Azure fetch.

    Returns True when the throttle path was taken (caller should not direct-fetch).
    """
    if not kafka_api_throttle_enabled() or not kafka_data_pipeline_enabled():
        return False

    enqueue_cost_api_jobs(
        subscription_id=envelope.subscription_id,
        pipeline_id=envelope.pipeline_id,
        run_params=run_params,
        source_service=source_service,
    )
    log.info(
        "api_throttle.cost_stage_delegated",
        pipeline_id=envelope.pipeline_id,
        subscription_id=envelope.subscription_id,
    )
    return True

"""Enqueue api.*.requested jobs from sync stage orchestration."""

from __future__ import annotations

import time

import structlog

from app.messaging.api_throttle.batch_registry import ApiBatchState, get_batch_registry
from app.messaging.api_throttle.phases import build_cost_batch_id, cost_api_phases
from app.messaging.api_throttle.topics import TOPIC_API_COST_REQUESTED
from app.messaging.job_envelope import JobEnvelope, JobType
from app.messaging.kafka_client import publish_envelope_safe

log = structlog.get_logger(__name__)


def enqueue_cost_api_jobs(
    *,
    subscription_id: str,
    pipeline_id: str,
    run_params: dict,
    source_service: str,
) -> str:
    """Fan out cost sync into rate-limited api.cost.requested jobs. Returns batch_id."""
    batch_id = build_cost_batch_id()
    phases = cost_api_phases(subscription_id=subscription_id)
    if not phases:
        raise RuntimeError("No cost API phases defined")

    meta = {
        "month": phases[0].get("month"),
        "mtd_start": phases[0].get("mtd_start"),
        "mtd_end": phases[0].get("mtd_end"),
        "daily_history_start": phases[0].get("daily_history_start"),
    }
    get_batch_registry().register(
        ApiBatchState(
            batch_id=batch_id,
            pipeline_id=pipeline_id,
            subscription_id=subscription_id,
            api_kind="cost",
            total_phases=len(phases),
            run_params=dict(run_params or {}),
            source_service=source_service,
            meta=meta,
        )
    )

    published = 0
    for phase_spec in phases:
        envelope = JobEnvelope.create(
            job_type=JobType.API_COST_REQUESTED,
            subscription_id=subscription_id,
            pipeline_id=pipeline_id,
            payload={
                "batch_id": batch_id,
                "phase": phase_spec["phase"],
                "phase_index": phase_spec["phase_index"],
                "total_phases": phase_spec["total_phases"],
                "api_params": phase_spec.get("api_params") or {},
                "run_params": dict(run_params or {}),
                "meta": meta,
            },
            source_service=source_service,
        )
        envelope.idempotency_key = (
            f"{pipeline_id}:api.cost:{batch_id}:{phase_spec['phase_index']}"
        )
        if publish_envelope_safe(envelope, topic=TOPIC_API_COST_REQUESTED):
            published += 1

    if published != len(phases):
        get_batch_registry().mark_failed(batch_id, "Failed to publish all api.cost.requested jobs")
        raise RuntimeError(
            f"Published {published}/{len(phases)} api.cost.requested jobs for pipeline {pipeline_id}"
        )

    log.info(
        "api_throttle.cost_jobs_enqueued",
        pipeline_id=pipeline_id,
        subscription_id=subscription_id,
        batch_id=batch_id,
        phases=len(phases),
    )
    return batch_id


def _check_backpressure() -> None:
    from app.messaging.api_throttle.config import api_throttle_consumer_lag_threshold

    registry = get_batch_registry()
    inflight = registry.inflight_count()
    threshold = api_throttle_consumer_lag_threshold()
    if inflight < threshold:
        return
    delay = min(30.0, 0.5 * (inflight - threshold + 1))
    log.warning(
        "api_throttle.backpressure",
        inflight=inflight,
        threshold=threshold,
        sleep_sec=round(delay, 2),
    )
    time.sleep(delay)


def enqueue_single_cost_phase(
    *,
    subscription_id: str,
    pipeline_id: str,
    phase: str,
    api_params: dict | None,
    run_params: dict,
    source_service: str = "platform-cost",
    timeout_sec: float | None = None,
) -> dict:
    """Enqueue one cost API phase and block until api.cost.completed arrives."""
    from app.messaging.api_throttle.config import api_throttle_wait_timeout_sec

    _check_backpressure()
    batch_id = build_cost_batch_id()
    params = dict(api_params or {})
    get_batch_registry().register(
        ApiBatchState(
            batch_id=batch_id,
            pipeline_id=pipeline_id,
            subscription_id=subscription_id,
            api_kind="cost",
            total_phases=1,
            run_params=dict(run_params or {}),
            source_service=source_service,
            meta={"wait_mode": True},
        )
    )

    envelope = JobEnvelope.create(
        job_type=JobType.API_COST_REQUESTED,
        subscription_id=subscription_id,
        pipeline_id=pipeline_id,
        payload={
            "batch_id": batch_id,
            "phase": phase,
            "phase_index": 0,
            "total_phases": 1,
            "api_params": params,
            "run_params": dict(run_params or {}),
            "retry_count": 0,
            "meta": {},
        },
        source_service=source_service,
    )
    envelope.idempotency_key = f"{pipeline_id}:api.cost:{batch_id}:0"
    if not publish_envelope_safe(envelope, topic=TOPIC_API_COST_REQUESTED):
        get_batch_registry().mark_failed(batch_id, "Failed to publish api.cost.requested")
        raise RuntimeError(f"Failed to publish api.cost.requested for phase {phase}")

    wait = timeout_sec if timeout_sec is not None else api_throttle_wait_timeout_sec()
    state = get_batch_registry().wait_for_batch(batch_id, timeout_sec=wait)
    result = state.results.get(phase)
    if result is None:
        raise RuntimeError(f"API batch {batch_id} completed without result for phase {phase}")
    get_batch_registry().pop(batch_id)
    return dict(result)

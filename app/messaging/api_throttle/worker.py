"""Kafka API worker — execute throttled Azure calls."""

from __future__ import annotations

import time

import structlog

from app.http_client import AzureAPIError
from app.messaging.api_throttle import metrics as throttle_metrics
from app.messaging.api_throttle.aggregator import publish_api_completed
from app.messaging.api_throttle.config import api_throttle_max_retries, api_throttle_retry_delay_sec
from app.messaging.api_throttle.cost_executor import execute_cost_phase
from app.messaging.api_throttle.dlq import publish_dead_letter
from app.messaging.api_throttle.rate_limiter import record_api_429
from app.messaging.api_throttle.topics import requested_topic_for_domain
from app.messaging.api_throttle.envelope import ApiDomain
from app.messaging.job_envelope import JobEnvelope, JobType
from app.messaging.kafka_client import publish_envelope_safe

log = structlog.get_logger(__name__)


def _resolve_bearer(run_params: dict) -> str:
    from app.database import SessionLocal
    from app.sync_orchestrator import fetch_worker_token

    bearer = (run_params.get("token") or "").strip()
    if bearer:
        return bearer
    db = SessionLocal()
    try:
        return fetch_worker_token(db)
    finally:
        db.close()


def _retry_count(payload: dict) -> int:
    try:
        return max(0, int(payload.get("retry_count", 0)))
    except (TypeError, ValueError):
        return 0


def _is_rate_limit_error(exc: Exception) -> bool:
    if isinstance(exc, AzureAPIError) and exc.status == 429:
        return True
    text = str(exc)
    return "429" in text or "TooManyRequests" in text or "rate limit" in text.lower()


def _requeue_api_job(envelope: JobEnvelope, *, topic: str, delay_sec: float) -> bool:
    payload = dict(envelope.payload or {})
    payload["retry_count"] = _retry_count(payload) + 1
    retry = JobEnvelope.create(
        job_type=envelope.job_type,
        subscription_id=envelope.subscription_id,
        pipeline_id=envelope.pipeline_id,
        payload=payload,
        source_service=envelope.source_service,
        job_id=envelope.job_id,
    )
    retry.idempotency_key = envelope.idempotency_key
    if delay_sec > 0:
        time.sleep(min(delay_sec, 60.0))
    return publish_envelope_safe(retry, topic=topic)


def handle_api_cost_requested(envelope: JobEnvelope) -> None:
    payload = envelope.payload or {}
    phase = str(payload.get("phase") or "")
    batch_id = str(payload.get("batch_id") or "")
    phase_index = int(payload.get("phase_index", 0))
    total_phases = int(payload.get("total_phases", 1))
    api_params = dict(payload.get("api_params") or {})
    run_params = dict(payload.get("run_params") or {})

    with throttle_metrics.timed_phase("cost", phase):
        token = _resolve_bearer(run_params)
        result = execute_cost_phase(
            subscription_id=envelope.subscription_id,
            phase=phase,
            api_params=api_params,
            token=token,
        )

    if not publish_api_completed(
        api_kind="cost",
        subscription_id=envelope.subscription_id,
        pipeline_id=envelope.pipeline_id,
        batch_id=batch_id,
        phase=phase,
        phase_index=phase_index,
        total_phases=total_phases,
        result=result,
        run_params=run_params,
        source_service=envelope.source_service,
        meta=dict(payload.get("meta") or {}),
    ):
        raise RuntimeError(f"Failed to publish api.cost.completed for phase {phase}")


def handle_api_metrics_requested(envelope: JobEnvelope) -> None:
    """Stub handler — logs and publishes empty completed result."""
    payload = envelope.payload or {}
    phase = str(payload.get("phase") or "metrics_batch_stub")
    log.info(
        "api_throttle.metrics_stub",
        pipeline_id=envelope.pipeline_id,
        subscription_id=envelope.subscription_id,
        phase=phase,
    )
    publish_api_completed(
        api_kind="metrics",
        subscription_id=envelope.subscription_id,
        pipeline_id=envelope.pipeline_id,
        batch_id=str(payload.get("batch_id") or ""),
        phase=phase,
        phase_index=int(payload.get("phase_index", 0)),
        total_phases=int(payload.get("total_phases", 1)),
        result={"stub": True},
        run_params=dict(payload.get("run_params") or {}),
        source_service=envelope.source_service,
    )


def handle_api_inventory_requested(envelope: JobEnvelope) -> None:
    """Stub handler — logs and publishes empty completed result."""
    payload = envelope.payload or {}
    phase = str(payload.get("phase") or "inventory_batch_stub")
    log.info(
        "api_throttle.inventory_stub",
        pipeline_id=envelope.pipeline_id,
        subscription_id=envelope.subscription_id,
        phase=phase,
    )
    publish_api_completed(
        api_kind="inventory",
        subscription_id=envelope.subscription_id,
        pipeline_id=envelope.pipeline_id,
        batch_id=str(payload.get("batch_id") or ""),
        phase=phase,
        phase_index=int(payload.get("phase_index", 0)),
        total_phases=int(payload.get("total_phases", 1)),
        result={"stub": True},
        run_params=dict(payload.get("run_params") or {}),
        source_service=envelope.source_service,
    )


def _requested_topic_for_envelope(envelope: JobEnvelope) -> str:
    mapping = {
        JobType.API_COST_REQUESTED: ApiDomain.COST_MANAGEMENT,
        JobType.API_METRICS_REQUESTED: ApiDomain.MONITOR,
        JobType.API_INVENTORY_REQUESTED: ApiDomain.RESOURCE_GRAPH,
    }
    domain = mapping.get(envelope.job_type)
    if domain is None:
        raise ValueError(f"No request topic for job type {envelope.job_type}")
    return requested_topic_for_domain(domain)


def handle_api_requested(envelope: JobEnvelope, topic: str) -> None:
    payload = envelope.payload or {}
    phase = str(payload.get("phase") or "unknown")
    retries = _retry_count(payload)
    try:
        if envelope.job_type == JobType.API_COST_REQUESTED:
            handle_api_cost_requested(envelope)
        elif envelope.job_type == JobType.API_METRICS_REQUESTED:
            handle_api_metrics_requested(envelope)
        elif envelope.job_type == JobType.API_INVENTORY_REQUESTED:
            handle_api_inventory_requested(envelope)
        else:
            log.warning(
                "api_throttle.unknown_requested",
                topic=topic,
                job_type=envelope.job_type.value,
            )
    except Exception as exc:
        if _is_rate_limit_error(exc) and retries < api_throttle_max_retries():
            record_api_429("cost" if envelope.job_type == JobType.API_COST_REQUESTED else "metrics")
            throttle_metrics.get_metrics().record_429(
                api_kind=envelope.job_type.value.split(".")[1],
                phase=phase,
            )
            delay = api_throttle_retry_delay_sec()
            log.warning(
                "api_throttle.requeue_429",
                pipeline_id=envelope.pipeline_id,
                phase=phase,
                retry_count=retries + 1,
                delay_sec=round(delay, 1),
            )
            if _requeue_api_job(envelope, topic=_requested_topic_for_envelope(envelope), delay_sec=delay):
                return
        publish_dead_letter(
            envelope,
            error=str(exc),
            original_topic=topic,
        )
        raise

"""Publish completed api job results and finalize batches."""

from __future__ import annotations

import structlog

from app.messaging.api_throttle.batch_registry import get_batch_registry
from app.messaging.api_throttle.cost_aggregate import assemble_cost_data_payload
from app.messaging.api_throttle.topics import TOPIC_API_COST_COMPLETED
from app.messaging.config import kafka_data_pipeline_enabled
from app.messaging.data_ack import wait_for_persist
from app.messaging.data_producer import publish_stage_data
from app.messaging.job_envelope import JobEnvelope, JobType
from app.messaging.kafka_client import publish_envelope_safe

log = structlog.get_logger(__name__)


def publish_api_completed(
    *,
    api_kind: str,
    subscription_id: str,
    pipeline_id: str,
    batch_id: str,
    phase: str,
    phase_index: int,
    total_phases: int,
    result: dict,
    run_params: dict,
    source_service: str,
    meta: dict | None = None,
) -> bool:
    job_type = {
        "cost": JobType.API_COST_COMPLETED,
        "metrics": JobType.API_METRICS_COMPLETED,
        "inventory": JobType.API_INVENTORY_COMPLETED,
    }.get(api_kind)
    if job_type is None:
        raise ValueError(f"Unknown api_kind: {api_kind}")

    from app.messaging.api_throttle.topics import api_topic_for_job_type

    envelope = JobEnvelope.create(
        job_type=job_type,
        subscription_id=subscription_id,
        pipeline_id=pipeline_id,
        payload={
            "batch_id": batch_id,
            "phase": phase,
            "phase_index": phase_index,
            "total_phases": total_phases,
            "result": result,
            "run_params": dict(run_params or {}),
            "api_kind": api_kind,
            "meta": dict(meta or {}),
        },
        source_service=source_service,
    )
    envelope.idempotency_key = f"{pipeline_id}:api.{api_kind}.completed:{batch_id}:{phase_index}"
    topic = api_topic_for_job_type(job_type)
    return publish_envelope_safe(envelope, topic=topic)


def handle_api_completed(envelope: JobEnvelope) -> None:
    """Aggregate phase results; publish data.* when the batch is complete."""
    payload = envelope.payload or {}
    batch_id = str(payload.get("batch_id") or "")
    phase = str(payload.get("phase") or "")
    phase_index = int(payload.get("phase_index", -1))
    total_phases = int(payload.get("total_phases", 0))
    result = payload.get("result")
    api_kind = str(payload.get("api_kind") or envelope.job_type.value.split(".")[1])
    run_params = dict(payload.get("run_params") or {})
    meta = dict(payload.get("meta") or {})

    registry = get_batch_registry()
    state = registry.get(batch_id)
    if state is None and batch_id and total_phases > 0:
        from app.messaging.api_throttle.batch_registry import ApiBatchState

        state = ApiBatchState(
            batch_id=batch_id,
            pipeline_id=envelope.pipeline_id,
            subscription_id=envelope.subscription_id,
            api_kind=api_kind,
            total_phases=total_phases,
            run_params=run_params,
            source_service=envelope.source_service,
            meta=meta,
        )

    state = registry.record_result(
        batch_id=batch_id,
        phase=phase,
        phase_index=phase_index,
        result=result,
        state=state,
    )
    if state is None:
        log.warning(
            "api_throttle.orphan_completed",
            batch_id=batch_id,
            phase=phase,
            pipeline_id=envelope.pipeline_id,
        )
        return

    if not get_batch_registry().is_complete(state):
        log.info(
            "api_throttle.batch_progress",
            batch_id=batch_id,
            pipeline_id=state.pipeline_id,
            completed=len(state.completed_indexes),
            total=state.total_phases,
        )
        return

    if state.meta.get("wait_mode"):
        log.info(
            "api_throttle.inline_wait_complete",
            batch_id=batch_id,
            pipeline_id=state.pipeline_id,
            phase=phase,
        )
        return

    finalized = get_batch_registry().pop(batch_id)
    if finalized is None:
        return

    if api_kind == "cost":
        _finalize_cost_batch(finalized)
    else:
        log.info(
            "api_throttle.batch_complete_stub",
            api_kind=api_kind,
            pipeline_id=finalized.pipeline_id,
            batch_id=batch_id,
        )


def _finalize_cost_batch(state) -> None:
    if not kafka_data_pipeline_enabled():
        log.warning(
            "api_throttle.cost_finalize_skipped",
            pipeline_id=state.pipeline_id,
            reason="data_pipeline_disabled",
        )
        return

    data_payload = assemble_cost_data_payload(
        subscription_id=state.subscription_id,
        phase_results=state.results,
        meta=state.meta,
    )
    published = publish_stage_data(
        "cost",
        subscription_id=state.subscription_id,
        pipeline_id=state.pipeline_id,
        data_payload=data_payload,
        source_service=state.source_service,
        run_params=state.run_params,
    )
    if not published:
        from app.messaging.kafka_errors import KafkaPublishExhaustedError
        from app.sync_orchestrator import mark_pipeline_publish_failed_db

        error = f"Failed to publish data.cost.synced after api throttle batch {state.batch_id}"
        mark_pipeline_publish_failed_db(
            state.pipeline_id,
            state.subscription_id,
            "cost",
            error,
            source_service=state.source_service,
        )
        raise KafkaPublishExhaustedError(error)

    from app.messaging.api_throttle.config import api_aggregate_timeout_sec

    if not wait_for_persist(state.pipeline_id, "cost", timeout=api_aggregate_timeout_sec()):
        raise TimeoutError(
            f"Timed out waiting for cost persist after api throttle (pipeline_id={state.pipeline_id})"
        )

    log.info(
        "api_throttle.cost_batch_finalized",
        pipeline_id=state.pipeline_id,
        subscription_id=state.subscription_id,
        batch_id=state.batch_id,
        phases=state.total_phases,
    )

"""Per-stage sync pipeline execution for Kafka consumers (DB-backed state)."""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.messaging.job_envelope import JobEnvelope

log = structlog.get_logger(__name__)


def _handle_stage_exception(
    exc: Exception,
    *,
    pipeline_id: str,
    subscription_id: str,
    stage: str,
    source_service: str,
) -> None:
    from app.messaging.kafka_errors import KafkaPublishExhaustedError
    from app.sync_orchestrator import mark_pipeline_failed_db

    if isinstance(exc, KafkaPublishExhaustedError):
        log.warning(
            "sync_stage.publish_exhausted",
            pipeline_id=pipeline_id,
            subscription_id=subscription_id,
            stage=stage,
            error=str(exc)[:300],
        )
        raise
    mark_pipeline_failed_db(
        pipeline_id,
        subscription_id,
        stage,
        str(exc),
        source_service=source_service,
    )
    raise


def _load_pipeline(pipeline_id: str, subscription_id: str) -> dict[str, Any] | None:
    from app.sync_orchestrator import load_pipeline_by_id

    return load_pipeline_by_id(pipeline_id, subscription_id=subscription_id)


def _stage_already_done(state: dict[str, Any], stage: str) -> bool:
    row = (state.get("stages") or {}).get(stage) or {}
    return row.get("status") in {"done", "skipped", "failed"}


def _pipeline_active(state: dict[str, Any] | None) -> bool:
    return bool(state and state.get("status") in {"queued", "running"})


def _run_params(envelope: JobEnvelope) -> dict[str, Any]:
    payload = envelope.payload or {}
    run_params = payload.get("run_params")
    return dict(run_params) if isinstance(run_params, dict) else {}


def _resolve_bearer(run_params: dict[str, Any]) -> str:
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


def _scoped_types(run_params: dict[str, Any]) -> list[str] | None:
    from app.sync_scope import normalize_sync_types

    type_list = run_params.get("type_list")
    scope_resource_types = run_params.get("scope_resource_types")
    types_set = normalize_sync_types(type_list) if type_list else set()
    if types_set:
        return sorted(types_set)
    if scope_resource_types:
        return list(scope_resource_types)
    return None


def run_inventory_stage(envelope: JobEnvelope, *, source_service: str) -> None:
    from app.auth import arm_auth_context
    from app.database import SessionLocal
    from app.db_sync import sync_all, sync_scoped
    from app.sync_orchestrator import (
        assert_inventory_persisted,
        mark_pipeline_running_db,
        mark_stage_done_db,
        pipeline_row_still_active,
        supersede_other_pipelines_db,
    )

    sub = envelope.subscription_id
    pipeline_id = envelope.pipeline_id
    run_params = _run_params(envelope)

    state = _load_pipeline(pipeline_id, sub)
    if not _pipeline_active(state):
        log.info("sync_stage.inventory_skip_inactive", pipeline_id=pipeline_id, subscription_id=sub)
        return
    if _stage_already_done(state, "inventory"):
        log.info("sync_stage.inventory_skip_done", pipeline_id=pipeline_id, subscription_id=sub)
        return

    supersede_other_pipelines_db(sub, pipeline_id, force=bool(run_params.get("force")))
    if not pipeline_row_still_active(sub, pipeline_id):
        return

    mark_pipeline_running_db(pipeline_id, sub, "inventory", source_service=source_service)
    bearer = _resolve_bearer(run_params)
    scoped_types = _scoped_types(run_params)

    def _fetch_inventory() -> dict:
        db = SessionLocal()
        try:
            with arm_auth_context(db=db, token=bearer):
                if scoped_types:
                    return sync_scoped(sub, db, bearer, scoped_types, include_costs=False)
                return sync_all(sub, db, bearer)
        finally:
            db.close()

    from app.messaging.config import kafka_data_pipeline_enabled
    from app.messaging.data_stage import maybe_use_data_pipeline

    try:
        result = maybe_use_data_pipeline(
            envelope,
            stage="inventory",
            source_service=source_service,
            run_params=run_params,
            fetch_fn=_fetch_inventory,
            direct_fn=_fetch_inventory,
        )
    except Exception as exc:
        _handle_stage_exception(
            exc,
            pipeline_id=pipeline_id,
            subscription_id=sub,
            stage="inventory",
            source_service=source_service,
        )

    if kafka_data_pipeline_enabled():
        log.info("sync_stage.inventory_done", pipeline_id=pipeline_id, subscription_id=sub)
        return

    assert_inventory_persisted(result, scoped=bool(scoped_types))
    if not pipeline_row_still_active(sub, pipeline_id):
        return
    mark_stage_done_db(pipeline_id, sub, "inventory", result=result, source_service=source_service)
    log.info("sync_stage.inventory_done", pipeline_id=pipeline_id, subscription_id=sub)


def run_cost_stage(envelope: JobEnvelope, *, source_service: str) -> None:
    from app.auth import arm_auth_context
    from app.cost_explorer_sync import sync_cost_explorer
    from app.database import SessionLocal
    from app.sync_orchestrator import (
        mark_pipeline_running_db,
        mark_stage_done_db,
        mark_stage_skipped_db,
        pipeline_row_still_active,
    )

    sub = envelope.subscription_id
    pipeline_id = envelope.pipeline_id
    run_params = _run_params(envelope)
    include_costs = bool(run_params.get("include_costs", True))

    state = _load_pipeline(pipeline_id, sub)
    if not _pipeline_active(state):
        return
    if _stage_already_done(state, "cost"):
        return

    if not include_costs:
        mark_stage_skipped_db(pipeline_id, sub, "cost", source_service=source_service)
        from app.messaging.sync_producer import publish_next_stage

        publish_next_stage(
            "cost",
            subscription_id=sub,
            pipeline_id=pipeline_id,
            run_params=run_params,
            source_service=source_service,
        )
        return

    mark_pipeline_running_db(pipeline_id, sub, "cost", source_service=source_service)

    from app.messaging.api_throttle.stage import maybe_run_cost_via_api_throttle

    if maybe_run_cost_via_api_throttle(
        envelope,
        source_service=source_service,
        run_params=run_params,
    ):
        log.info("sync_stage.cost_delegated_api_throttle", pipeline_id=pipeline_id, subscription_id=sub)
        return

    bearer = _resolve_bearer(run_params)

    def _fetch_cost() -> dict:
        db = SessionLocal()
        try:
            with arm_auth_context(db=db, token=bearer):
                return sync_cost_explorer(sub, db, bearer)
        finally:
            db.close()

    from app.messaging.config import kafka_data_pipeline_enabled
    from app.messaging.data_stage import maybe_use_data_pipeline

    try:
        result = maybe_use_data_pipeline(
            envelope,
            stage="cost",
            source_service=source_service,
            run_params=run_params,
            fetch_fn=_fetch_cost,
            direct_fn=_fetch_cost,
        )
    except Exception as exc:
        _handle_stage_exception(
            exc,
            pipeline_id=pipeline_id,
            subscription_id=sub,
            stage="cost",
            source_service=source_service,
        )

    if kafka_data_pipeline_enabled():
        log.info("sync_stage.cost_done", pipeline_id=pipeline_id, subscription_id=sub)
        return

    if not pipeline_row_still_active(sub, pipeline_id):
        return
    mark_stage_done_db(pipeline_id, sub, "cost", result=result, source_service=source_service)
    log.info("sync_stage.cost_done", pipeline_id=pipeline_id, subscription_id=sub)


def run_metrics_stage(envelope: JobEnvelope, *, source_service: str) -> None:
    from app.auth import arm_auth_context
    from app.database import SessionLocal
    from app.sync_orchestrator import (
        mark_pipeline_running_db,
        mark_stage_done_db,
        pipeline_row_still_active,
    )
    from app.workers.inventory_metrics_worker import run_inventory_metrics_worker

    sub = envelope.subscription_id
    pipeline_id = envelope.pipeline_id
    run_params = _run_params(envelope)

    state = _load_pipeline(pipeline_id, sub)
    if not _pipeline_active(state):
        return
    if _stage_already_done(state, "metrics"):
        return

    mark_pipeline_running_db(pipeline_id, sub, "metrics", source_service=source_service)
    bearer = _resolve_bearer(run_params)
    scoped_types = _scoped_types(run_params)

    def _fetch_metrics() -> dict:
        db = SessionLocal()
        try:
            with arm_auth_context(db=db, token=bearer):
                return run_inventory_metrics_worker(
                    db,
                    sub,
                    token=bearer,
                    scoped_canonical_types=scoped_types,
                    sync_context=True,
                )
        finally:
            db.close()

    from app.messaging.config import kafka_data_pipeline_enabled
    from app.messaging.data_stage import maybe_use_data_pipeline

    try:
        result = maybe_use_data_pipeline(
            envelope,
            stage="metrics",
            source_service=source_service,
            run_params=run_params,
            fetch_fn=_fetch_metrics,
            direct_fn=_fetch_metrics,
        )
    except Exception as exc:
        _handle_stage_exception(
            exc,
            pipeline_id=pipeline_id,
            subscription_id=sub,
            stage="metrics",
            source_service=source_service,
        )

    if kafka_data_pipeline_enabled():
        log.info("sync_stage.metrics_done", pipeline_id=pipeline_id, subscription_id=sub)
        return

    if not pipeline_row_still_active(sub, pipeline_id):
        return
    mark_stage_done_db(pipeline_id, sub, "metrics", result=result, source_service=source_service)
    log.info("sync_stage.metrics_done", pipeline_id=pipeline_id, subscription_id=sub)


def run_analysis_stage(envelope: JobEnvelope, *, source_service: str) -> None:
    from app.batch_analyzer import create_analysis_job, execute_batch_job
    from app.database import SessionLocal
    from app.db_analyze import run_db_analysis
    from app.models import AnalysisJob
    from app.sync_orchestrator import (
        mark_pipeline_complete_db,
        mark_pipeline_running_db,
        mark_stage_done_db,
        pipeline_row_still_active,
        set_analysis_job_id_db,
    )

    sub = envelope.subscription_id
    pipeline_id = envelope.pipeline_id
    run_params = _run_params(envelope)

    state = _load_pipeline(pipeline_id, sub)
    if not _pipeline_active(state):
        return
    if _stage_already_done(state, "analysis"):
        return

    mark_pipeline_running_db(pipeline_id, sub, "analysis", source_service=source_service)
    profile = run_params.get("profile") or "default"
    engine_version = run_params.get("engine_version") or "extended"
    scope_components = run_params.get("scope_components")
    scope_resource_types = run_params.get("scope_resource_types")
    scoped_types = _scoped_types(run_params)
    analysis_types = scope_resource_types or scoped_types

    db = SessionLocal()
    job_id: str | None = None
    job_status = "unknown"
    try:
        job = create_analysis_job(
            db,
            subscription_id=sub,
            profile=profile,
            engine_version=engine_version,
            scope_components=scope_components,
            scope_resource_types=analysis_types,
            skip_monitor_fetch=True,
        )
        job_id = job.id
        set_analysis_job_id_db(pipeline_id, sub, job_id)
        db.commit()
    finally:
        db.close()

    def _fetch_analysis() -> dict:
        analysis_db = SessionLocal()
        try:
            job_row = analysis_db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if not job_row:
                raise RuntimeError(f"Analysis job not found: {job_id}")
            job_row.status = "running"
            analysis_db.commit()
            try:
                job_rule_overrides = json.loads(job_row.rule_overrides_json or "{}")
            except json.JSONDecodeError:
                job_rule_overrides = {}
            scope_components_local, scope_resource_types_local, skip_monitor_fetch = (
                _analysis_scope_from_job(job_row)
            )
            result = run_db_analysis(
                analysis_db,
                subscription_id=sub,
                profile=job_row.profile,
                engine_version=job_row.engine_version,
                rule_overrides=job_rule_overrides,
                scope_components=scope_components_local,
                scope_resource_types=scope_resource_types_local,
                fetch_monitor_metrics=not skip_monitor_fetch,
            )
            from app.messaging.data_collector import get_collector

            collector = get_collector()
            if collector is not None:
                analysis_section = collector.sections.get("analysis") or {}
                analysis_section["job_id"] = job_id
                collector.sections["analysis"] = analysis_section
            return {"job_id": job_id, "status": "completed", "result": result}
        finally:
            analysis_db.close()

    from app.messaging.config import kafka_data_pipeline_enabled
    from app.messaging.data_stage import maybe_use_data_pipeline

    try:
        if job_id:
            outcome = maybe_use_data_pipeline(
                envelope,
                stage="analysis",
                source_service=source_service,
                run_params=run_params,
                fetch_fn=_fetch_analysis,
                direct_fn=lambda: (_execute_analysis_job(job_id), {"job_id": job_id, "status": "completed"})[1],
            )
            job_status = outcome.get("status", "unknown")
        else:
            job_status = "failed"
    except Exception as exc:
        _handle_stage_exception(
            exc,
            pipeline_id=pipeline_id,
            subscription_id=sub,
            stage="analysis",
            source_service=source_service,
        )

    if kafka_data_pipeline_enabled():
        log.info(
            "sync_stage.analysis_done",
            pipeline_id=pipeline_id,
            subscription_id=sub,
            job_id=job_id,
            job_status=job_status,
        )
        return

    if not pipeline_row_still_active(sub, pipeline_id):
        return
    mark_stage_done_db(
        pipeline_id,
        sub,
        "analysis",
        result={"job_id": job_id, "status": job_status},
        source_service=source_service,
    )
    mark_pipeline_complete_db(pipeline_id, sub, source_service=source_service)
    log.info(
        "sync_stage.analysis_done",
        pipeline_id=pipeline_id,
        subscription_id=sub,
        job_id=job_id,
        job_status=job_status,
    )


def _execute_analysis_job(job_id: str) -> None:
    from app.batch_analyzer import execute_batch_job
    from app.database import SessionLocal
    from app.models import AnalysisJob

    execute_batch_job(job_id)
    status_db = SessionLocal()
    try:
        final_job = status_db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if final_job and final_job.status == "failed":
            raise RuntimeError(final_job.error_message or "Analysis job failed")
    finally:
        status_db.close()


def _analysis_scope_from_job(job: AnalysisJob):
    from app.batch_analyzer import _execution_scope_from_job

    return _execution_scope_from_job(job)

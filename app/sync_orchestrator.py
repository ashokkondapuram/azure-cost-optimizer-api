"""Unified subscription sync pipeline: inventory → cost → metrics → analysis."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

log = structlog.get_logger(__name__)

STAGE_ORDER = ("inventory", "cost", "metrics", "analysis")
_STAGE_PROGRESS = {
    "inventory": (0, 25),
    "cost": (25, 50),
    "metrics": (50, 75),
    "analysis": (75, 100),
}

_lock = threading.Lock()
_pending: set[str] = set()
_pipeline_by_sub: dict[str, dict[str, Any]] = {}
_worker_params_by_sub: dict[str, dict[str, Any]] = {}


def full_sync_pipeline_never_started_minutes() -> float:
    return max(2.0, float(os.getenv("FULL_SYNC_PIPELINE_NEVER_STARTED_MINUTES", "10")))


def full_sync_pipeline_max_runtime_hours() -> float:
    return max(0.5, float(os.getenv("FULL_SYNC_PIPELINE_MAX_RUNTIME_HOURS", "4")))


def full_sync_pipeline_max_queue_minutes() -> float:
    return max(5.0, float(os.getenv("FULL_SYNC_PIPELINE_MAX_QUEUE_MINUTES", "30")))


def full_sync_pipeline_worker_stall_seconds() -> float:
    return max(1.0, float(os.getenv("FULL_SYNC_PIPELINE_WORKER_STALL_SECONDS", "60")))


def full_sync_arm_token_timeout_seconds() -> float:
    return max(5.0, float(os.getenv("FULL_SYNC_ARM_TOKEN_TIMEOUT_SECONDS", "30")))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(when: datetime | None) -> datetime | None:
    if when is None:
        return None
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _empty_stages() -> dict[str, dict[str, Any]]:
    return {
        stage: {
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "error": None,
        }
        for stage in STAGE_ORDER
    }


def _progress_for_stage(stage: str | None, *, running: bool = False) -> int:
    if not stage or stage not in _STAGE_PROGRESS:
        return 0 if not running else 5
    low, high = _STAGE_PROGRESS[stage]
    return low if not running else (low + high) // 2


def _new_pipeline_state(subscription_id: str) -> dict[str, Any]:
    now = _now()
    return {
        "pipeline_id": str(uuid.uuid4()),
        "subscription_id": subscription_id,
        "status": "queued",
        "current_stage": None,
        "progress_pct": 0,
        "stages": _empty_stages(),
        "analysis_job_id": None,
        "started_at": None,
        "completed_at": None,
        "created_at": now,
        "error": None,
    }


def _serialize_stages_for_db(
    stages: dict[str, dict[str, Any]],
    run_params: dict[str, Any] | None = None,
    *,
    extra_meta: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {}
    for stage, row in stages.items():
        entry = dict(row)
        entry["started_at"] = _iso(entry.get("started_at")) if isinstance(entry.get("started_at"), datetime) else entry.get("started_at")
        entry["completed_at"] = _iso(entry.get("completed_at")) if isinstance(entry.get("completed_at"), datetime) else entry.get("completed_at")
        payload[stage] = entry
    meta: dict[str, Any] = {}
    if run_params:
        meta["run_params"] = run_params
    if extra_meta:
        meta.update(extra_meta)
    if meta:
        payload["_meta"] = meta
    return json.dumps(payload)


def _deserialize_stages(raw: str | dict | None) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    stages = _empty_stages()
    run_params: dict[str, Any] | None = None
    extra_meta: dict[str, Any] = {}
    if not raw:
        return stages, run_params, extra_meta
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError, json.JSONDecodeError):
        return stages, run_params, extra_meta
    if not isinstance(parsed, dict):
        return stages, run_params, extra_meta
    meta = parsed.get("_meta")
    if isinstance(meta, dict):
        if isinstance(meta.get("run_params"), dict):
            run_params = meta["run_params"]
        for key, value in meta.items():
            if key != "run_params":
                extra_meta[key] = value
    for stage in STAGE_ORDER:
        row = parsed.get(stage)
        if not isinstance(row, dict):
            continue
        stages[stage] = {
            "status": row.get("status") or "pending",
            "started_at": _parse_iso(row.get("started_at")),
            "completed_at": _parse_iso(row.get("completed_at")),
            "error": row.get("error"),
            **({"result": row["result"]} if "result" in row else {}),
        }
    return stages, run_params, extra_meta


def _persist_pipeline_state(state: dict[str, Any]) -> None:
    """Write pipeline progress using a short-lived DB session (safe under pool pressure)."""
    from app.database import SessionLocal
    from app.models import FullSyncPipelineRun

    sub = (state.get("subscription_id") or "").strip().lower()
    pipeline_id = state.get("pipeline_id")
    if not sub or not pipeline_id:
        return

    db = SessionLocal()
    try:
        row = db.query(FullSyncPipelineRun).filter(FullSyncPipelineRun.id == pipeline_id).first()
        if not row:
            row = FullSyncPipelineRun(
                id=pipeline_id,
                subscription_id=sub,
                created_at=state.get("created_at") or state.get("started_at") or _now(),
            )
            db.add(row)
        row.subscription_id = sub
        row.status = state.get("status") or "queued"
        row.current_stage = state.get("current_stage")
        row.progress_pct = int(state.get("progress_pct") or 0)
        extra_meta: dict[str, Any] = {}
        worker_entered = state.get("worker_entered_at")
        if isinstance(worker_entered, datetime):
            extra_meta["worker_entered_at"] = _iso(worker_entered)
        if state.get("publish_retriable"):
            extra_meta["publish_retriable"] = True
            if state.get("last_publish_error"):
                extra_meta["last_publish_error"] = str(state["last_publish_error"])[:500]
        row.stages_json = _serialize_stages_for_db(
            state.get("stages") or _empty_stages(),
            state.get("run_params"),
            extra_meta=extra_meta or None,
        )
        row.analysis_job_id = state.get("analysis_job_id")
        row.error_message = state.get("error")
        row.started_at = state.get("started_at")
        row.completed_at = state.get("completed_at")
        db.commit()
    except Exception:
        log.exception("full_sync.persist_failed", subscription_id=sub, pipeline_id=pipeline_id)
        db.rollback()
    finally:
        db.close()


def _load_pipeline_from_db(subscription_id: str) -> dict[str, Any] | None:
    from app.database import SessionLocal
    from app.models import FullSyncPipelineRun

    sub = (subscription_id or "").strip().lower()
    if not sub:
        return None

    db = SessionLocal()
    try:
        row = (
            db.query(FullSyncPipelineRun)
            .filter(FullSyncPipelineRun.subscription_id == sub)
            .order_by(FullSyncPipelineRun.created_at.desc())
            .first()
        )
        if not row:
            return None
        return _state_from_pipeline_row(row)
    finally:
        db.close()


def _stale_pipeline_reason(state: dict[str, Any], *, now: datetime | None = None) -> str | None:
    """Return expiry reason when a queued/running pipeline is no longer active."""
    status = state.get("status")
    if status not in {"queued", "running"}:
        return None
    now = now or _now()
    if status == "queued":
        started = _as_utc(state.get("started_at"))
        created = _as_utc(state.get("created_at"))
        worker_entered = _as_utc(state.get("worker_entered_at"))
        stall_seconds = full_sync_pipeline_worker_stall_seconds()
        if worker_entered and started is None:
            if now - worker_entered > timedelta(seconds=stall_seconds):
                return (
                    f"Sync worker started but did not begin inventory within "
                    f"{int(stall_seconds)} seconds."
                )
        if started is None:
            ref = created or now
            if ref and now - ref > timedelta(minutes=full_sync_pipeline_never_started_minutes()):
                return (
                    "Pipeline was queued but never started by a worker. "
                    "A new sync will restart it automatically."
                )
            return None
        if created and now - created > timedelta(minutes=full_sync_pipeline_max_queue_minutes()):
            return (
                f"Pipeline remained queued for more than "
                f"{int(full_sync_pipeline_max_queue_minutes())} minutes."
            )
        return None
    started = _as_utc(state.get("started_at")) or _as_utc(state.get("created_at"))
    if started and now - started > timedelta(hours=full_sync_pipeline_max_runtime_hours()):
        return (
            f"Pipeline exceeded the {full_sync_pipeline_max_runtime_hours():g}-hour time limit."
        )
    return None


def _fail_pipeline_row(row, reason: str, *, now: datetime | None = None) -> None:
    now = now or _now()
    row.status = "failed"
    row.error_message = reason[:500]
    row.completed_at = now


def _cancel_linked_analysis_job(db, subscription_id: str, job_id: str | None) -> None:
    if not job_id:
        return
    from app.batch_analyzer import cancel_analysis_job, expire_stale_analysis_jobs

    try:
        cancel_analysis_job(db, job_id, subscription_id)
    except ValueError:
        expire_stale_analysis_jobs(db, subscription_id=subscription_id)


def expire_stale_pipeline_runs(*, subscription_id: str | None = None) -> list[str]:
    """Mark orphaned queued/running pipelines as failed so new sync can start."""
    from app.database import SessionLocal
    from app.models import FullSyncPipelineRun

    sub_filter = (subscription_id or "").strip().lower() or None
    db = SessionLocal()
    expired: list[str] = []
    try:
        q = db.query(FullSyncPipelineRun).filter(
            FullSyncPipelineRun.status.in_(["queued", "running"]),
        )
        if sub_filter:
            q = q.filter(FullSyncPipelineRun.subscription_id == sub_filter)
        now = _now()
        for row in q.all():
            state = {
                "status": row.status,
                "started_at": row.started_at,
                "created_at": row.created_at,
            }
            reason = _stale_pipeline_reason(state, now=now)
            if not reason:
                continue
            _fail_pipeline_row(row, reason, now=now)
            expired.append(row.id)
            with _lock:
                _pending.discard(row.subscription_id)
                mem = _pipeline_by_sub.get(row.subscription_id)
                if mem and mem.get("pipeline_id") == row.id:
                    del _pipeline_by_sub[row.subscription_id]
            _cancel_linked_analysis_job(db, row.subscription_id, row.analysis_job_id)
            log.warning(
                "full_sync.pipeline_expired",
                subscription_id=row.subscription_id,
                pipeline_id=row.id,
                reason=reason,
            )
        if expired:
            db.commit()
    except Exception:
        log.exception("full_sync.expire_failed", subscription_id=sub_filter)
        db.rollback()
    finally:
        db.close()
    return expired


def _supersede_other_pipelines(
    subscription_id: str,
    keep_pipeline_id: str,
    *,
    reason: str = "Superseded by newer sync run.",
) -> int:
    """Mark older queued/running DB pipelines failed so a new worker can proceed."""
    from app.database import SessionLocal
    from app.models import FullSyncPipelineRun

    sub = subscription_id.strip().lower()
    keep_id = (keep_pipeline_id or "").strip()
    if not sub or not keep_id:
        return 0

    db = SessionLocal()
    superseded = 0
    try:
        rows = (
            db.query(FullSyncPipelineRun)
            .filter(
                FullSyncPipelineRun.subscription_id == sub,
                FullSyncPipelineRun.status.in_(["queued", "running"]),
                FullSyncPipelineRun.id != keep_id,
            )
            .all()
        )
        for row in rows:
            _fail_pipeline_row(row, reason)
            _cancel_linked_analysis_job(db, sub, row.analysis_job_id)
            superseded += 1
            with _lock:
                mem = _pipeline_by_sub.get(sub)
                if mem and mem.get("pipeline_id") == row.id:
                    del _pipeline_by_sub[sub]
        if superseded:
            db.commit()
            log.info(
                "full_sync.superseded_pipelines",
                subscription_id=sub,
                keep_pipeline_id=keep_id,
                count=superseded,
            )
    except Exception:
        log.exception("full_sync.supersede_failed", subscription_id=sub)
        db.rollback()
    finally:
        db.close()
    return superseded


def _pipeline_row_still_active(subscription_id: str, pipeline_id: str) -> bool:
    from app.database import SessionLocal
    from app.models import FullSyncPipelineRun

    sub = subscription_id.strip().lower()
    db = SessionLocal()
    try:
        row = (
            db.query(FullSyncPipelineRun)
            .filter(
                FullSyncPipelineRun.id == pipeline_id,
                FullSyncPipelineRun.subscription_id == sub,
            )
            .first()
        )
        return bool(row and row.status in {"queued", "running"})
    finally:
        db.close()


def _run_params_match(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    """Compare pipeline run params ignoring None defaults."""
    if not left or not right:
        return False
    keys = {
        "type_list",
        "include_costs",
        "scope_components",
        "scope_resource_types",
        "profile",
        "engine_version",
        "reason",
        "force",
    }
    for key in keys:
        if left.get(key) != right.get(key):
            return False
    return True


def _run_params_from_state(state: dict[str, Any]) -> dict[str, Any]:
    params = dict(state.get("run_params") or {})
    with _lock:
        cached = _worker_params_by_sub.get((state.get("subscription_id") or "").lower())
    if cached:
        params = {**cached, **params}
    return params


def cancel_full_sync_pipeline(
    subscription_id: str,
    *,
    reason: str = "Cancelled by user.",
) -> dict[str, Any]:
    """Cancel an active pipeline and any linked analysis job."""
    sub = (subscription_id or "").strip().lower()
    if not sub:
        return {"status": "error", "error": "subscription_id is required"}

    with _lock:
        _pending.discard(sub)
        mem = _pipeline_by_sub.pop(sub, None)

    from app.database import SessionLocal
    from app.models import FullSyncPipelineRun

    db = SessionLocal()
    cancelled = False
    try:
        row = (
            db.query(FullSyncPipelineRun)
            .filter(
                FullSyncPipelineRun.subscription_id == sub,
                FullSyncPipelineRun.status.in_(["queued", "running"]),
            )
            .order_by(FullSyncPipelineRun.created_at.desc())
            .first()
        )
        if row:
            _fail_pipeline_row(row, reason)
            _cancel_linked_analysis_job(db, sub, row.analysis_job_id)
            db.commit()
            cancelled = True
        elif mem and mem.get("status") in {"queued", "running"}:
            stage = mem.get("current_stage") or "inventory"
            _mark_pipeline_failed(mem, stage, reason)
            cancelled = True
    except Exception:
        log.exception("full_sync.cancel_failed", subscription_id=sub)
        db.rollback()
    finally:
        db.close()

    with _lock:
        mem = _pipeline_by_sub.get(sub)
        serialized = _serialize_pipeline(mem) if mem else None
    if serialized is None:
        db_state = _load_pipeline_from_db(sub)
        serialized = _serialize_pipeline(db_state) if db_state else None
    return {
        "status": "cancelled" if cancelled else "idle",
        "subscription_id": sub,
        "pending": bool(serialized and serialized.get("pending")),
        "pipeline": serialized,
    }


def reset_full_sync_pipeline(subscription_id: str) -> dict[str, Any]:
    """Admin reset — clear stuck pipeline state for a subscription."""
    return cancel_full_sync_pipeline(
        subscription_id,
        reason="Reset by administrator.",
    )


def is_full_sync_pending(subscription_id: str) -> bool:
    sub = (subscription_id or "").strip().lower()
    expire_stale_pipeline_runs(subscription_id=sub)
    with _lock:
        if sub in _pending:
            return True
    pipeline = get_pipeline_status(subscription_id)
    return bool(pipeline and pipeline.get("pending"))


def _state_from_pipeline_row(row) -> dict[str, Any]:
    stages, run_params, extra_meta = _deserialize_stages(row.stages_json)
    worker_entered = _parse_iso(extra_meta.get("worker_entered_at"))
    return {
        "pipeline_id": row.id,
        "subscription_id": row.subscription_id,
        "status": row.status,
        "current_stage": row.current_stage,
        "progress_pct": row.progress_pct or 0,
        "stages": stages,
        "analysis_job_id": row.analysis_job_id,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "created_at": row.created_at,
        "error": row.error_message,
        "run_params": run_params,
        "worker_entered_at": worker_entered,
        "publish_retriable": bool(extra_meta.get("publish_retriable")),
        "last_publish_error": extra_meta.get("last_publish_error"),
    }


def _stage_terminal_status(status: str | None) -> bool:
    return status in {"done", "skipped", "failed"}


def _should_run_stage(state: dict[str, Any], stage: str) -> bool:
    row = (state.get("stages") or {}).get(stage) or {}
    return not _stage_terminal_status(row.get("status"))


def resolve_resume_job_type(state: dict[str, Any]):
    """Return the orchestration job to re-publish for an interrupted pipeline.

    Returns ``None`` when every stage is already terminal (pipeline row may be stale).
    """
    from app.messaging.job_envelope import JobType
    from app.messaging.topics import next_job_type_after_stage

    stages = state.get("stages") or {}
    if all(_stage_terminal_status((stages.get(stage) or {}).get("status")) for stage in STAGE_ORDER):
        return None

    current_stage = state.get("current_stage")
    if not current_stage or current_stage == "queued":
        return JobType.SYNC_INVENTORY

    resume_job: JobType | None = None
    for stage in STAGE_ORDER:
        row = stages.get(stage) or {}
        status = row.get("status")
        if status in {"pending", "running"}:
            return {
                "inventory": JobType.SYNC_INVENTORY,
                "cost": JobType.SYNC_COST,
                "metrics": JobType.SYNC_METRICS,
                "analysis": JobType.SYNC_ANALYSIS,
            }[stage]
        if status in {"done", "skipped"}:
            resume_job = next_job_type_after_stage(stage)
    return resume_job or JobType.SYNC_INVENTORY


def list_incomplete_pipeline_states() -> list[dict[str, Any]]:
    """Load queued/running pipelines from PostgreSQL (oldest first)."""
    from app.database import SessionLocal
    from app.models import FullSyncPipelineRun

    db = SessionLocal()
    try:
        rows = (
            db.query(FullSyncPipelineRun)
            .filter(FullSyncPipelineRun.status.in_(["queued", "running"]))
            .order_by(FullSyncPipelineRun.created_at.asc())
            .all()
        )
        states = [_state_from_pipeline_row(row) for row in rows]
        retriable_failed: list[dict[str, Any]] = []
        failed_rows = (
            db.query(FullSyncPipelineRun)
            .filter(FullSyncPipelineRun.status == "failed")
            .order_by(FullSyncPipelineRun.created_at.asc())
            .all()
        )
        seen_ids = {state["pipeline_id"] for state in states}
        for row in failed_rows:
            state = _state_from_pipeline_row(row)
            if state.get("publish_retriable") and state["pipeline_id"] not in seen_ids:
                retriable_failed.append(state)
        return states + retriable_failed
    finally:
        db.close()


def resume_pipeline_state(
    state: dict[str, Any],
    *,
    source_service: str = "platform-inventory",
) -> bool:
    """Re-drive a single incomplete pipeline from its last persisted stage."""
    from app.messaging.config import kafka_pipeline_dispatch_enabled
    from app.messaging.sync_producer import publish_pipeline_completed, publish_sync_job

    sub = (state.get("subscription_id") or "").strip().lower()
    pipeline_id = state.get("pipeline_id")
    if not sub or not pipeline_id:
        return False
    if _stale_pipeline_reason(state):
        return False
    if state.get("publish_retriable") and state.get("status") == "failed":
        mark_pipeline_publish_failed_db(
            pipeline_id,
            sub,
            str(state.get("current_stage") or "inventory"),
            str(state.get("last_publish_error") or state.get("error") or "Kafka publish failed"),
            source_service=source_service,
        )
        state = load_pipeline_by_id(pipeline_id, subscription_id=sub) or state
    with _lock:
        if sub in _pending:
            return False
    if not _pipeline_row_still_active(sub, pipeline_id):
        return False

    run_params = _run_params_from_state(state)
    resume_job = resolve_resume_job_type(state)
    if resume_job is None:
        mark_pipeline_complete_db(pipeline_id, sub, source_service=source_service)
        if kafka_pipeline_dispatch_enabled():
            publish_pipeline_completed(
                subscription_id=sub,
                pipeline_id=pipeline_id,
                status="completed",
                source_service=source_service,
            )
        log.info(
            "full_sync.resume_finalize",
            subscription_id=sub,
            pipeline_id=pipeline_id,
        )
        return True

    log.info(
        "full_sync.resume_worker",
        subscription_id=sub,
        pipeline_id=pipeline_id,
        resume_job=resume_job.value,
        current_stage=state.get("current_stage"),
        scoped_types=run_params.get("scope_resource_types"),
    )
    if kafka_pipeline_dispatch_enabled():
        return publish_sync_job(
            resume_job,
            subscription_id=sub,
            pipeline_id=pipeline_id,
            payload={"run_params": run_params},
            source_service=source_service,
        )
    _start_pipeline_worker(sub, pipeline_id, run_params, state=state)
    return True


def resume_incomplete_pipelines(
    *,
    service_id: str | None = None,
    coordinator_service_id: str = "platform-inventory",
) -> list[str]:
    """On service startup, re-publish jobs for pipelines interrupted by restart.

    Only the coordinator service (default: platform-inventory) drives resume so
    multiple replicas do not duplicate orchestration publishes.
    """
    if service_id and service_id != coordinator_service_id:
        return []

    expire_stale_pipeline_runs()
    resumed: list[str] = []
    seen_subs: set[str] = set()

    for state in list_incomplete_pipeline_states():
        sub = (state.get("subscription_id") or "").strip().lower()
        pipeline_id = state.get("pipeline_id")
        if not sub or not pipeline_id:
            continue
        if sub in seen_subs:
            continue
        seen_subs.add(sub)
        if resume_pipeline_state(state, source_service=coordinator_service_id):
            resumed.append(pipeline_id)

    if resumed:
        log.info(
            "full_sync.resume_incomplete",
            count=len(resumed),
            pipeline_ids=resumed,
            coordinator=coordinator_service_id,
        )
    return resumed


def get_pipeline_status(subscription_id: str, *, resume: bool = True) -> dict[str, Any] | None:
    sub = (subscription_id or "").strip().lower()
    expire_stale_pipeline_runs(subscription_id=sub)
    with _lock:
        state = _pipeline_by_sub.get(sub)
        pending_local = sub in _pending
    if state:
        if (
            resume
            and not pending_local
            and state.get("status") in {"queued", "running"}
            and not _stale_pipeline_reason(state)
        ):
            _maybe_resume_pipeline_worker(state)
        return _serialize_pipeline(state)
    state = _load_pipeline_from_db(sub)
    if not state:
        return None
    if resume and state.get("status") in {"queued", "running"}:
        _maybe_resume_pipeline_worker(state)
        state = _load_pipeline_from_db(sub) or state
    return _serialize_pipeline(state)


def _maybe_resume_pipeline_worker(state: dict[str, Any]) -> None:
    """Restart a DB-active pipeline on this instance when no in-process worker exists."""
    resume_pipeline_state(state, source_service="platform-inventory")


def _abort_pipeline_worker(
    subscription_id: str,
    pipeline_id: str,
    *,
    reason: str,
    stage: str = "inventory",
) -> None:
    """Mark an abandoned worker run failed so polls do not show queued forever."""
    sub = subscription_id.strip().lower()
    with _lock:
        pipeline = _pipeline_by_sub.get(sub)
    if pipeline and pipeline.get("pipeline_id") == pipeline_id:
        _mark_pipeline_failed(pipeline, stage, reason)
        return
    from app.database import SessionLocal
    from app.models import FullSyncPipelineRun

    db = SessionLocal()
    try:
        row = (
            db.query(FullSyncPipelineRun)
            .filter(
                FullSyncPipelineRun.id == pipeline_id,
                FullSyncPipelineRun.subscription_id == sub,
            )
            .first()
        )
        if row and row.status in {"queued", "running"}:
            _fail_pipeline_row(row, reason)
            db.commit()
    except Exception:
        log.exception("full_sync.abort_failed", subscription_id=sub, pipeline_id=pipeline_id)
        db.rollback()
    finally:
        db.close()


def _start_pipeline_worker(
    subscription_id: str,
    pipeline_id: str,
    run_params: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
) -> None:
    from app.messaging.config import kafka_pipeline_dispatch_enabled

    if kafka_pipeline_dispatch_enabled():
        log.info(
            "full_sync.worker_skipped_kafka",
            subscription_id=subscription_id.strip().lower(),
            pipeline_id=pipeline_id,
        )
        return

    sub = subscription_id.strip().lower()
    with _lock:
        existing = _pipeline_by_sub.get(sub)
        if sub in _pending and existing and existing.get("pipeline_id") != pipeline_id:
            return
        _pending.add(sub)
        if state is not None:
            merged = dict(state)
            merged["run_params"] = run_params
            _pipeline_by_sub[sub] = merged
        _worker_params_by_sub[sub] = dict(run_params)

    threading.Thread(
        target=_execute_pipeline_worker,
        args=(sub, pipeline_id, run_params),
        daemon=True,
        name=f"full-sync-{sub[:8]}",
    ).start()
    log.info(
        "full_sync.worker_started",
        subscription_id=sub,
        pipeline_id=pipeline_id,
        scoped_types=run_params.get("scope_resource_types"),
    )


def _serialize_pipeline(state: dict[str, Any]) -> dict[str, Any]:
    stages = {}
    for stage in STAGE_ORDER:
        row = dict(state["stages"][stage])
        row["started_at"] = _iso(row.get("started_at"))
        row["completed_at"] = _iso(row.get("completed_at"))
        stages[stage] = row
    return {
        "pipeline_id": state["pipeline_id"],
        "subscription_id": state["subscription_id"],
        "status": state["status"],
        "current_stage": state["current_stage"],
        "progress_pct": state.get("progress_pct", 0),
        "stages": stages,
        "inventory": stages["inventory"]["status"],
        "cost": stages["cost"]["status"],
        "metrics": stages["metrics"]["status"],
        "analysis": stages["analysis"]["status"],
        "analysis_job_id": state.get("analysis_job_id"),
        "started_at": _iso(state.get("started_at")),
        "completed_at": _iso(state.get("completed_at")),
        "error": state.get("error"),
        "pending": state["status"] in {"queued", "running"},
    }


def _touch_pipeline(state: dict[str, Any]) -> None:
    _persist_pipeline_state(state)


def _set_stage(
    state: dict[str, Any],
    stage: str,
    status: str,
    *,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    row = state["stages"][stage]
    now = _now()
    if status == "running" and row["status"] == "pending":
        row["started_at"] = now
    if status in {"done", "failed", "skipped"}:
        row["completed_at"] = now
    row["status"] = status
    if error:
        row["error"] = error[:500]
    if result is not None:
        row["result"] = result
    _touch_pipeline(state)


def _mark_pipeline_running(state: dict[str, Any], stage: str) -> None:
    if state["started_at"] is None:
        state["started_at"] = _now()
    state["status"] = "running"
    state["current_stage"] = stage
    state["progress_pct"] = _progress_for_stage(stage, running=True)
    _set_stage(state, stage, "running")


def _mark_pipeline_complete(state: dict[str, Any]) -> None:
    state["status"] = "completed"
    state["current_stage"] = "completed"
    state["progress_pct"] = 100
    state["completed_at"] = _now()
    _touch_pipeline(state)


def _mark_pipeline_failed(state: dict[str, Any], stage: str, error: str) -> None:
    state["status"] = "failed"
    state["current_stage"] = stage
    state["error"] = error[:500]
    state["completed_at"] = _now()
    _set_stage(state, stage, "failed", error=error)
    _touch_pipeline(state)


def _worker_step(
    subscription_id: str,
    pipeline_id: str,
    step: str,
    **fields: Any,
) -> None:
    log.info(
        "full_sync.worker_step",
        subscription_id=subscription_id,
        pipeline_id=pipeline_id,
        step=step,
        **fields,
    )


def _fetch_worker_token(db) -> str:
    """Fetch ARM bearer token with a bounded wait so workers cannot hang forever."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    from app.auth import get_token

    timeout = full_sync_arm_token_timeout_seconds()
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="arm-token") as pool:
        future = pool.submit(get_token, db)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout as exc:
            raise RuntimeError(
                f"Azure AD token fetch timed out after {int(timeout)} seconds."
            ) from exc


def _already_queued_payload(
    existing: dict[str, Any] | None,
    *,
    reason: str = "already_running",
) -> dict[str, Any]:
    serialized = _serialize_pipeline(existing) if existing else None
    pipeline_id = (existing or {}).get("pipeline_id")
    status = (existing or {}).get("status")
    return {
        "status": "accepted",
        "already_queued": True,
        "pending": True,
        "reason": reason,
        "pipeline_id": pipeline_id,
        "pipeline": serialized,
        "message": (
            "Sync pipeline is already running for this subscription."
            if reason == "already_running"
            else "Sync pipeline is already queued for this subscription."
        ),
        "pipeline_status": status,
    }


def _inventory_arm_total(result: dict[str, Any] | None) -> int:
    """Sum ARM list counts returned by inventory sync."""
    if not result:
        return 0
    resources = result.get("resources") or {}
    if not isinstance(resources, dict):
        return 0
    return sum(int(v or 0) for v in resources.values())


def assert_inventory_persisted(result: dict[str, Any], *, scoped: bool) -> None:
    """Raise when inventory sync did not persist any rows to PostgreSQL."""
    db_total = int(result.get("db_total") or 0)
    arm_total = _inventory_arm_total(result)
    if db_total > 0:
        return
    if arm_total > 0:
        raise RuntimeError(
            f"Azure returned {arm_total} resources but none were saved to the database. "
            "Check database connectivity and server logs."
        )
    if scoped:
        types = result.get("types") or []
        label = ", ".join(types) if types else "requested types"
        raise RuntimeError(
            f"No resources were saved for {label}. Check Azure permissions and retry."
        )
    raise RuntimeError(
        "No resources were saved to the database. Check Azure permissions and subscription access."
    )


def _execute_pipeline_worker(
    subscription_id: str,
    pipeline_id: str,
    run_params: dict[str, Any],
) -> None:
    """Background worker — inventory → cost → metrics → analysis."""
    from app.auth import arm_auth_context
    from app.batch_analyzer import create_analysis_job, execute_batch_job
    from app.cost_explorer_sync import sync_cost_explorer
    from app.database import SessionLocal
    from app.db_sync import sync_all, sync_scoped
    from app.models import AnalysisJob
    from app.sync_scope import normalize_sync_types
    from app.workers.inventory_metrics_worker import run_inventory_metrics_worker

    sub = subscription_id.strip().lower()
    token = run_params.get("token")
    type_list = run_params.get("type_list")
    include_costs = bool(run_params.get("include_costs", True))
    scope_components = run_params.get("scope_components")
    scope_resource_types = run_params.get("scope_resource_types")
    profile = run_params.get("profile") or "default"
    engine_version = run_params.get("engine_version") or "extended"
    reason = run_params.get("reason") or "manual_api"
    force = bool(run_params.get("force"))

    log.info(
        "full_sync.worker_enter",
        subscription_id=sub,
        pipeline_id=pipeline_id,
        reason=reason,
        scoped_types=scope_resource_types or type_list,
    )

    try:
        with _lock:
            pipeline = _pipeline_by_sub.get(sub)
        if not pipeline or pipeline.get("pipeline_id") != pipeline_id:
            pipeline = _load_pipeline_from_db(sub)
            if not pipeline or pipeline.get("pipeline_id") != pipeline_id:
                log.warning(
                    "full_sync.worker_aborted",
                    subscription_id=sub,
                    pipeline_id=pipeline_id,
                    reason="pipeline_not_found",
                )
                _abort_pipeline_worker(
                    sub,
                    pipeline_id,
                    reason="Sync worker could not find the pipeline state. Please retry.",
                )
                return
            pipeline["run_params"] = run_params
            with _lock:
                _pipeline_by_sub[sub] = pipeline

        with _lock:
            pipeline = _pipeline_by_sub.get(sub)
            if pipeline and pipeline.get("pipeline_id") == pipeline_id:
                pipeline["worker_entered_at"] = _now()
        with _lock:
            pipeline = _pipeline_by_sub.get(sub)
        if not pipeline or pipeline.get("pipeline_id") != pipeline_id:
            log.warning(
                "full_sync.worker_aborted",
                subscription_id=sub,
                pipeline_id=pipeline_id,
                reason="pipeline_missing_after_enter",
            )
            _abort_pipeline_worker(
                sub,
                pipeline_id,
                reason="Sync worker lost pipeline state. Please retry.",
            )
            return
        _worker_step(sub, pipeline_id, "worker_entered")

        _touch_pipeline(pipeline)
        _worker_step(sub, pipeline_id, "after_persist")

        if force:
            _supersede_other_pipelines(
                sub,
                pipeline_id,
                reason="Superseded by new sync request.",
            )
        else:
            _supersede_other_pipelines(sub, pipeline_id)
        _worker_step(sub, pipeline_id, "after_supersede")

        expire_stale_pipeline_runs(subscription_id=sub)
        _worker_step(sub, pipeline_id, "after_expire")

        if not _pipeline_row_still_active(sub, pipeline_id):
            log.warning(
                "full_sync.worker_aborted",
                subscription_id=sub,
                pipeline_id=pipeline_id,
                reason="expired_or_superseded",
            )
            _abort_pipeline_worker(
                sub,
                pipeline_id,
                reason="Sync was superseded or expired before it could start. Please retry.",
            )
            return
        _worker_step(sub, pipeline_id, "after_active_check")

        bearer = (token or "").strip()
        if not bearer:
            token_db = SessionLocal()
            try:
                _worker_step(sub, pipeline_id, "token_fetch_start")
                bearer = _fetch_worker_token(token_db)
                _worker_step(sub, pipeline_id, "token_fetch_done")
            finally:
                token_db.close()

        types_set = normalize_sync_types(type_list) if type_list else set()
        scoped_types = sorted(types_set) if types_set else None
        if scope_resource_types and not scoped_types:
            scoped_types = list(scope_resource_types)

        with _lock:
            pipeline = _pipeline_by_sub.get(sub)
        if not pipeline or pipeline.get("pipeline_id") != pipeline_id:
            log.warning(
                "full_sync.worker_aborted",
                subscription_id=sub,
                pipeline_id=pipeline_id,
                reason="pipeline_replaced",
            )
            _abort_pipeline_worker(
                sub,
                pipeline_id,
                reason="Sync was replaced before inventory could start. Please retry.",
            )
            return

        # Stage 1 — inventory
        if _should_run_stage(pipeline, "inventory"):
            _mark_pipeline_running(pipeline, "inventory")
            log.info(
                "full_sync.inventory_start",
                subscription_id=sub,
                reason=reason,
                scoped_types=scoped_types,
            )
            db = SessionLocal()
            try:
                with arm_auth_context(db=db, token=bearer):
                    if scoped_types:
                        inventory_result = sync_scoped(
                            sub,
                            db,
                            bearer,
                            scoped_types,
                            include_costs=False,
                        )
                    else:
                        inventory_result = sync_all(sub, db, bearer)
                assert_inventory_persisted(inventory_result, scoped=bool(scoped_types))
            finally:
                db.close()
            if not _pipeline_row_still_active(sub, pipeline_id):
                return
            db_total = int(inventory_result.get("db_total") or 0)
            arm_total = _inventory_arm_total(inventory_result)
            with _lock:
                pipeline = _pipeline_by_sub.get(sub)
                if pipeline and pipeline.get("pipeline_id") == pipeline_id:
                    _set_stage(pipeline, "inventory", "done", result=inventory_result)
                    pipeline["progress_pct"] = _STAGE_PROGRESS["cost"][0]
            log.info(
                "full_sync.inventory_done",
                subscription_id=sub,
                db_total=db_total,
                arm_total=arm_total,
                scoped=bool(scoped_types),
            )
        else:
            log.info(
                "full_sync.inventory_skip_resume",
                subscription_id=sub,
                pipeline_id=pipeline_id,
            )

        # Stage 2 — cost
        if include_costs:
            with _lock:
                pipeline = _pipeline_by_sub.get(sub)
            if not pipeline or pipeline.get("pipeline_id") != pipeline_id:
                return
            if _should_run_stage(pipeline, "cost"):
                _mark_pipeline_running(pipeline, "cost")
                log.info("full_sync.cost_start", subscription_id=sub)
                db = SessionLocal()
                try:
                    with arm_auth_context(db=db, token=bearer):
                        cost_result = sync_cost_explorer(sub, db, bearer)
                finally:
                    db.close()
                with _lock:
                    pipeline = _pipeline_by_sub.get(sub)
                    if pipeline and pipeline.get("pipeline_id") == pipeline_id:
                        _set_stage(pipeline, "cost", "done", result=cost_result)
                        pipeline["progress_pct"] = _STAGE_PROGRESS["metrics"][0]
                log.info(
                    "full_sync.cost_done",
                    subscription_id=sub,
                    resources_with_cost=cost_result.get("resources_with_cost"),
                    mtd_by_service=cost_result.get("mtd_by_service"),
                    mtd_by_resource=cost_result.get("mtd_by_resource"),
                )
            else:
                log.info(
                    "full_sync.cost_skip_resume",
                    subscription_id=sub,
                    pipeline_id=pipeline_id,
                )
        else:
            with _lock:
                pipeline = _pipeline_by_sub.get(sub)
                if pipeline and pipeline.get("pipeline_id") == pipeline_id:
                    if _should_run_stage(pipeline, "cost"):
                        _set_stage(pipeline, "cost", "skipped")
                        pipeline["progress_pct"] = _STAGE_PROGRESS["metrics"][0]
                        _touch_pipeline(pipeline)

        # Stage 3 — metrics
        with _lock:
            pipeline = _pipeline_by_sub.get(sub)
        if not pipeline or pipeline.get("pipeline_id") != pipeline_id:
            return
        if _should_run_stage(pipeline, "metrics"):
            _mark_pipeline_running(pipeline, "metrics")
            log.info("full_sync.metrics_start", subscription_id=sub)
            db = SessionLocal()
            try:
                with arm_auth_context(db=db, token=bearer):
                    metrics_result = run_inventory_metrics_worker(
                        db,
                        sub,
                        token=bearer,
                        scoped_canonical_types=scoped_types,
                        sync_context=True,
                    )
            finally:
                db.close()
            with _lock:
                pipeline = _pipeline_by_sub.get(sub)
                if pipeline and pipeline.get("pipeline_id") == pipeline_id:
                    _set_stage(pipeline, "metrics", "done", result=metrics_result)
                    pipeline["progress_pct"] = _STAGE_PROGRESS["analysis"][0]
            log.info(
                "full_sync.metrics_done",
                subscription_id=sub,
                resources_processed=metrics_result.get("resources_processed"),
                metrics_loaded=metrics_result.get("metrics_loaded"),
                metrics_failed=metrics_result.get("metrics_failed"),
                status=metrics_result.get("status"),
            )
        else:
            log.info(
                "full_sync.metrics_skip_resume",
                subscription_id=sub,
                pipeline_id=pipeline_id,
            )

        # Stage 4 — analysis
        with _lock:
            pipeline = _pipeline_by_sub.get(sub)
        if not pipeline or pipeline.get("pipeline_id") != pipeline_id:
            return
        if _should_run_stage(pipeline, "analysis"):
            _mark_pipeline_running(pipeline, "analysis")
            log.info("full_sync.analysis_start", subscription_id=sub)
            analysis_types = scope_resource_types
            if not analysis_types and scoped_types:
                analysis_types = scoped_types
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
                with _lock:
                    pipeline = _pipeline_by_sub.get(sub)
                    if pipeline and pipeline.get("pipeline_id") == pipeline_id:
                        pipeline["analysis_job_id"] = job_id
                        _touch_pipeline(pipeline)
            finally:
                db.close()

            if job_id:
                execute_batch_job(job_id)
                status_db = SessionLocal()
                try:
                    final_job = status_db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
                    job_status = final_job.status if final_job else "unknown"
                    if final_job and final_job.status == "failed":
                        raise RuntimeError(final_job.error_message or "Analysis job failed")
                finally:
                    status_db.close()
            with _lock:
                pipeline = _pipeline_by_sub.get(sub)
                if pipeline and pipeline.get("pipeline_id") == pipeline_id:
                    _set_stage(
                        pipeline,
                        "analysis",
                        "done",
                        result={"job_id": job_id, "status": job_status},
                    )
                    _mark_pipeline_complete(pipeline)
            log.info(
                "full_sync.analysis_done",
                subscription_id=sub,
                job_id=job_id,
                job_status=job_status,
            )
        else:
            with _lock:
                pipeline = _pipeline_by_sub.get(sub)
                if (
                    pipeline
                    and pipeline.get("pipeline_id") == pipeline_id
                    and pipeline.get("status") != "completed"
                ):
                    _mark_pipeline_complete(pipeline)
            log.info(
                "full_sync.analysis_skip_resume",
                subscription_id=sub,
                pipeline_id=pipeline_id,
            )
    except Exception as exc:
        err = str(exc)[:500]
        with _lock:
            pipeline = _pipeline_by_sub.get(sub)
            if pipeline and pipeline.get("pipeline_id") == pipeline_id:
                stage = pipeline.get("current_stage") or "inventory"
                if stage == "completed":
                    stage = "analysis"
                _mark_pipeline_failed(pipeline, stage, err)
        log.exception("full_sync.failed", subscription_id=sub, error=err, pipeline_id=pipeline_id)
    finally:
        with _lock:
            _pending.discard(sub)
            _worker_params_by_sub.pop(sub, None)
        log.info(
            "full_sync.worker_exit",
            subscription_id=sub,
            pipeline_id=pipeline_id,
        )


def request_full_sync(
    subscription_id: str,
    *,
    token: str | None = None,
    type_list: list[str] | None = None,
    include_costs: bool = True,
    scope_components: list[str] | None = None,
    scope_resource_types: list[str] | None = None,
    profile: str = "default",
    engine_version: str = "extended",
    reason: str = "manual_api",
    force: bool = False,
) -> tuple[bool, dict[str, Any]]:
    """Enqueue the unified sync pipeline (deduplicated per subscription on this instance).

    Accept path sets in-memory state and starts a daemon worker immediately.
    DB persist and stale-run cleanup happen inside the worker's first step.
    """
    sub = (subscription_id or "").strip().lower()
    if not sub:
        return False, {"status": "error", "error": "subscription_id is required"}

    run_params = {
        "token": token,
        "type_list": type_list,
        "include_costs": include_costs,
        "scope_components": scope_components,
        "scope_resource_types": scope_resource_types,
        "profile": profile,
        "engine_version": engine_version,
        "reason": reason,
        "force": force,
    }

    if not force:
        with _lock:
            pending_local = sub in _pending
            existing_mem = _pipeline_by_sub.get(sub) if pending_local else None
        if pending_local:
            stall_reason = _stale_pipeline_reason(existing_mem) if existing_mem else None
            if stall_reason:
                cancel_full_sync_pipeline(sub, reason=stall_reason)
            else:
                return False, _already_queued_payload(existing_mem)

    if force:
        cancel_full_sync_pipeline(sub, reason="Superseded by new sync request.")
    else:
        existing_db = _load_pipeline_from_db(sub)
        if existing_db and existing_db.get("status") in {"queued", "running"}:
            stale_reason = _stale_pipeline_reason(existing_db)
            if stale_reason:
                cancel_full_sync_pipeline(
                    sub,
                    reason=stale_reason,
                )
            elif _run_params_match(existing_db.get("run_params"), run_params):
                with _lock:
                    pending_local = sub in _pending
                    mem = _pipeline_by_sub.get(sub)
                if pending_local:
                    stall_reason = _stale_pipeline_reason(mem) if mem else None
                    if stall_reason:
                        cancel_full_sync_pipeline(sub, reason=stall_reason)
                    else:
                        return False, _already_queued_payload(mem or existing_db)
                _maybe_resume_pipeline_worker(existing_db)
                return False, _already_queued_payload(existing_db, reason="already_queued_db")
            else:
                cancel_full_sync_pipeline(
                    sub,
                    reason="Superseded by new scoped sync request.",
                )

    state = _new_pipeline_state(sub)
    state["run_params"] = run_params
    pipeline_id = state["pipeline_id"]

    with _lock:
        _pending.add(sub)
        _pipeline_by_sub[sub] = state
        _worker_params_by_sub[sub] = dict(run_params)

    # Best-effort DB row so polls on any instance see the pipeline immediately.
    try:
        _touch_pipeline(state)
        from app.sync_progress import notify_progress_updated

        notify_progress_updated(state, event_type="queued", source="api")
    except Exception:
        log.exception("full_sync.accept_persist_failed", subscription_id=sub, pipeline_id=pipeline_id)

    from app.messaging.config import kafka_pipeline_dispatch_enabled
    from app.messaging.sync_producer import publish_inventory_requested

    kafka_dispatched = False
    if kafka_pipeline_dispatch_enabled():
        kafka_dispatched = publish_inventory_requested(
            subscription_id=sub,
            pipeline_id=pipeline_id,
            run_params=run_params,
            source_service="platform-inventory",
        )
        if kafka_dispatched:
            try:
                from app.messaging.sync_producer import publish_pipeline_status

                publish_pipeline_status(
                    subscription_id=sub,
                    pipeline_id=pipeline_id,
                    stage="inventory",
                    progress_pct=0,
                    status="queued",
                    source_service="platform-inventory",
                )
            except Exception:
                log.exception("full_sync.queued_status_publish_failed", pipeline_id=pipeline_id)
        if not kafka_dispatched:
            log.warning(
                "full_sync.kafka_publish_failed_fallback",
                subscription_id=sub,
                pipeline_id=pipeline_id,
            )

    if not kafka_dispatched:
        _start_pipeline_worker(sub, pipeline_id, run_params, state=state)

    with _lock:
        message = (
            "Full sync pipeline queued via Kafka: inventory → cost → metrics → analysis."
            if kafka_dispatched
            else "Full sync pipeline started: inventory → cost → metrics → analysis."
        )
        return True, {
            "status": "accepted",
            "async": True,
            "already_queued": False,
            "pending": True,
            "kafka": kafka_dispatched,
            "pipeline": _serialize_pipeline(_pipeline_by_sub[sub]),
            "message": message,
        }


# ── Public helpers for Kafka stage consumers (DB-backed) ─────────────────────


def pipeline_row_still_active(subscription_id: str, pipeline_id: str) -> bool:
    return _pipeline_row_still_active(subscription_id, pipeline_id)


def fetch_worker_token(db) -> str:
    return _fetch_worker_token(db)


def load_pipeline_by_id(
    pipeline_id: str,
    *,
    subscription_id: str | None = None,
) -> dict[str, Any] | None:
    from app.database import SessionLocal
    from app.models import FullSyncPipelineRun

    pid = (pipeline_id or "").strip()
    if not pid:
        return None
    sub_filter = (subscription_id or "").strip().lower() or None
    db = SessionLocal()
    try:
        q = db.query(FullSyncPipelineRun).filter(FullSyncPipelineRun.id == pid)
        if sub_filter:
            q = q.filter(FullSyncPipelineRun.subscription_id == sub_filter)
        row = q.first()
        if not row:
            return None
        return _state_from_pipeline_row(row)
    finally:
        db.close()


def _mutate_pipeline_db(
    pipeline_id: str,
    subscription_id: str,
    mutator,
) -> dict[str, Any] | None:
    state = load_pipeline_by_id(pipeline_id, subscription_id=subscription_id)
    if not state:
        return None
    mutator(state)
    _persist_pipeline_state(state)
    return state


def supersede_other_pipelines_db(
    subscription_id: str,
    keep_pipeline_id: str,
    *,
    force: bool = False,
) -> int:
    reason = "Superseded by new sync request." if force else "Superseded by newer sync run."
    return _supersede_other_pipelines(subscription_id, keep_pipeline_id, reason=reason)


def _emit_pipeline_status(
    state: dict[str, Any],
    *,
    stage: str,
    stage_status: str,
    source_service: str | None = None,
    error: str | None = None,
) -> None:
    """Publish pipeline progress to Kafka, cache, and SSE subscribers."""
    try:
        from app.sync_progress import notify_progress_updated

        notify_progress_updated(state, event_type="progress", source="db")
    except Exception:
        log.exception("full_sync.progress_notify_failed", pipeline_id=state.get("pipeline_id"), stage=stage)

    if not source_service:
        return
    try:
        from app.messaging.sync_producer import publish_pipeline_status

        publish_pipeline_status(
            subscription_id=state["subscription_id"],
            pipeline_id=state["pipeline_id"],
            stage=stage,
            progress_pct=int(state.get("progress_pct") or _progress_for_stage(stage, running=stage_status == "running")),
            status=stage_status,
            source_service=source_service,
            error=error,
        )
    except Exception:
        log.exception("full_sync.status_publish_failed", pipeline_id=state.get("pipeline_id"), stage=stage)


def mark_pipeline_running_db(
    pipeline_id: str,
    subscription_id: str,
    stage: str,
    *,
    source_service: str | None = None,
) -> None:
    def _mutate(state: dict[str, Any]) -> None:
        if state.get("worker_entered_at") is None:
            state["worker_entered_at"] = _now()
        state.pop("publish_retriable", None)
        state.pop("last_publish_error", None)
        _mark_pipeline_running(state, stage)

    state = _mutate_pipeline_db(pipeline_id, subscription_id, _mutate)
    if state:
        _emit_pipeline_status(state, stage=stage, stage_status="running", source_service=source_service)


def mark_stage_done_db(
    pipeline_id: str,
    subscription_id: str,
    stage: str,
    *,
    result: dict[str, Any] | None = None,
    source_service: str | None = None,
) -> None:
    def _mutate(state: dict[str, Any]) -> None:
        state.pop("publish_retriable", None)
        state.pop("last_publish_error", None)
        state["error"] = None
        _set_stage(state, stage, "done", result=result)
        next_idx = STAGE_ORDER.index(stage) + 1 if stage in STAGE_ORDER else len(STAGE_ORDER)
        if next_idx < len(STAGE_ORDER):
            state["progress_pct"] = _STAGE_PROGRESS[STAGE_ORDER[next_idx]][0]
        else:
            state["progress_pct"] = 100

    state = _mutate_pipeline_db(pipeline_id, subscription_id, _mutate)
    if state:
        _emit_pipeline_status(state, stage=stage, stage_status="done", source_service=source_service)


def mark_stage_skipped_db(
    pipeline_id: str,
    subscription_id: str,
    stage: str,
    *,
    source_service: str | None = None,
) -> None:
    def _mutate(state: dict[str, Any]) -> None:
        _set_stage(state, stage, "skipped")
        next_idx = STAGE_ORDER.index(stage) + 1 if stage in STAGE_ORDER else len(STAGE_ORDER)
        if next_idx < len(STAGE_ORDER):
            state["progress_pct"] = _STAGE_PROGRESS[STAGE_ORDER[next_idx]][0]

    state = _mutate_pipeline_db(pipeline_id, subscription_id, _mutate)
    if state:
        _emit_pipeline_status(state, stage=stage, stage_status="skipped", source_service=source_service)


def mark_pipeline_failed_db(
    pipeline_id: str,
    subscription_id: str,
    stage: str,
    error: str,
    *,
    source_service: str | None = None,
) -> None:
    def _mutate(state: dict[str, Any]) -> None:
        state.pop("publish_retriable", None)
        state.pop("last_publish_error", None)
        _mark_pipeline_failed(state, stage, error)

    state = _mutate_pipeline_db(pipeline_id, subscription_id, _mutate)
    if state:
        _emit_pipeline_status(
            state,
            stage=stage,
            stage_status="failed",
            source_service=source_service,
            error=error[:500],
        )


def mark_pipeline_publish_failed_db(
    pipeline_id: str,
    subscription_id: str,
    stage: str,
    error: str,
    *,
    source_service: str | None = None,
) -> None:
    """Record a retriable Kafka publish failure while keeping the pipeline active."""

    def _mutate(state: dict[str, Any]) -> None:
        state["status"] = "running"
        state["error"] = error[:500]
        state["current_stage"] = stage
        state["publish_retriable"] = True
        state["last_publish_error"] = error[:500]
        state["completed_at"] = None
        row = state["stages"][stage]
        row["status"] = "running"
        row["error"] = error[:500]
        row["completed_at"] = None
        state["progress_pct"] = _progress_for_stage(stage, running=True)

    state = _mutate_pipeline_db(pipeline_id, subscription_id, _mutate)
    if state:
        _emit_pipeline_status(
            state,
            stage=stage,
            stage_status="running",
            source_service=source_service,
            error=error[:500],
        )


def mark_pipeline_complete_db(
    pipeline_id: str,
    subscription_id: str,
    *,
    source_service: str | None = None,
) -> None:
    def _mutate(state: dict[str, Any]) -> None:
        _mark_pipeline_complete(state)

    state = _mutate_pipeline_db(pipeline_id, subscription_id, _mutate)
    if state:
        _emit_pipeline_status(state, stage="analysis", stage_status="done", source_service=source_service)


def set_analysis_job_id_db(pipeline_id: str, subscription_id: str, job_id: str) -> None:
    def _mutate(state: dict[str, Any]) -> None:
        state["analysis_job_id"] = job_id

    _mutate_pipeline_db(pipeline_id, subscription_id, _mutate)

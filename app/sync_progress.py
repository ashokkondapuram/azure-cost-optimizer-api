"""Sync pipeline progress aggregation for dashboard UI (Kafka + PostgreSQL)."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

import structlog

from app.sync_orchestrator import STAGE_ORDER, _serialize_pipeline, get_pipeline_status

log = structlog.get_logger(__name__)

STAGE_WEIGHT_PCT = 25
_UI_STAGE_STATUSES = frozenset({"pending", "running", "done", "failed"})

_lock = threading.Lock()
_cache_by_sub: dict[str, dict[str, Any]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | str | None) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
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


def _ui_stage_status(raw: str | None) -> str:
    status = (raw or "pending").lower()
    if status in {"done", "skipped"}:
        return "done"
    if status in _UI_STAGE_STATUSES:
        return status
    return "pending"


def compute_percent_complete(
    stages: dict[str, dict[str, Any]] | None,
    *,
    current_stage: str | None = None,
    pipeline_status: str | None = None,
    explicit_pct: int | None = None,
) -> int:
    """Equal 25% weight per stage; a running stage counts half its slice."""
    if pipeline_status == "completed":
        return 100
    if explicit_pct is not None:
        return max(0, min(100, int(explicit_pct)))
    if not stages:
        return 0

    total = 0.0
    for stage in STAGE_ORDER:
        row = stages.get(stage) or {}
        status = (row.get("status") or "pending").lower()
        if status in {"done", "skipped"}:
            total += STAGE_WEIGHT_PCT
        elif status == "running":
            total += STAGE_WEIGHT_PCT / 2
        elif status == "failed":
            total += STAGE_WEIGHT_PCT / 2

    if total == 0 and current_stage in STAGE_ORDER:
        idx = STAGE_ORDER.index(current_stage)
        total = idx * STAGE_WEIGHT_PCT + (STAGE_WEIGHT_PCT / 2)

    return max(0, min(100, int(round(total))))


def _stage_statuses_for_api(stages: dict[str, dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for stage in STAGE_ORDER:
        row = dict((stages or {}).get(stage) or {})
        out[stage] = {
            "status": _ui_stage_status(row.get("status")),
            "started_at": _iso(row.get("started_at")),
            "completed_at": _iso(row.get("completed_at")),
            **({"error": row["error"]} if row.get("error") else {}),
        }
    return out


def progress_message(
    *,
    pipeline_status: str | None,
    current_stage: str | None,
    stage_status: str | None = None,
) -> str:
    status = (pipeline_status or "").lower()
    if status == "queued":
        return "Sync pipeline queued"
    if status == "completed":
        return "Sync pipeline completed"
    if status == "failed":
        return "Sync pipeline failed"
    stage = current_stage or "inventory"
    labels = {
        "inventory": "Syncing inventory",
        "cost": "Syncing cost data",
        "metrics": "Syncing metrics",
        "analysis": "Running analysis",
    }
    label = labels.get(stage, "Syncing")
    if (stage_status or "").lower() == "done":
        return f"{label} — stage complete"
    return label


def _cache_key(subscription_id: str, pipeline_id: str) -> str:
    return f"{subscription_id.strip().lower()}:{pipeline_id}"


def _upsert_cache(entry: dict[str, Any]) -> dict[str, Any]:
    sub = (entry.get("subscription_id") or "").strip().lower()
    if not sub:
        return entry
    with _lock:
        _cache_by_sub[sub] = dict(entry)
    return entry


def clear_progress_cache(subscription_id: str | None = None) -> None:
    with _lock:
        if subscription_id:
            _cache_by_sub.pop(subscription_id.strip().lower(), None)
        else:
            _cache_by_sub.clear()


def serialize_progress_entry(state: dict[str, Any] | None) -> dict[str, Any] | None:
    """Shape returned by GET /sync/progress for one subscription pipeline."""
    if not state:
        return None

    serialized = _serialize_pipeline(state) if "inventory" not in state else state
    stages = serialized.get("stages") or {}
    stage_statuses = _stage_statuses_for_api(stages)
    pipeline_status = serialized.get("status") or "queued"
    current_stage = serialized.get("current_stage")
    percent = compute_percent_complete(
        stages,
        current_stage=current_stage,
        pipeline_status=pipeline_status,
        explicit_pct=serialized.get("progress_pct"),
    )
    pending = bool(serialized.get("pending")) or pipeline_status in {"queued", "running"}

    return {
        "pipeline_id": serialized.get("pipeline_id"),
        "subscription_id": serialized.get("subscription_id"),
        "status": pipeline_status,
        "current_stage": current_stage,
        "stage_statuses": stage_statuses,
        "stages": stage_statuses,
        "percent_complete": percent,
        "progress_pct": percent,
        "message": progress_message(
            pipeline_status=pipeline_status,
            current_stage=current_stage,
        ),
        "started_at": serialized.get("started_at"),
        "updated_at": _iso(_now()),
        "completed_at": serialized.get("completed_at"),
        "pending": pending,
        "error": serialized.get("error"),
        "analysis_job_id": serialized.get("analysis_job_id"),
        "inventory": stage_statuses["inventory"]["status"],
        "cost": stage_statuses["cost"]["status"],
        "metrics": stage_statuses["metrics"]["status"],
        "analysis": stage_statuses["analysis"]["status"],
    }


def notify_progress_updated(
    state: dict[str, Any],
    *,
    event_type: str = "progress",
    source: str = "db",
) -> dict[str, Any] | None:
    """Update in-memory cache and push an SSE event."""
    entry = serialize_progress_entry(state)
    if not entry:
        return None
    entry["source"] = source
    _upsert_cache(entry)

    from app.sync_pipeline_events import publish_sync_progress_event

    publish_sync_progress_event(
        {"type": event_type, "progress": entry},
        subscription_id=entry.get("subscription_id"),
        broadcast_all=True,
    )
    return entry


def apply_kafka_status_event(envelope) -> dict[str, Any] | None:
    """Apply sync.pipeline.status Kafka message to the progress cache."""
    from app.sync_orchestrator import load_pipeline_by_id

    payload = envelope.payload or {}
    sub = (envelope.subscription_id or "").strip().lower()
    pipeline_id = (envelope.pipeline_id or "").strip()
    if not sub or not pipeline_id:
        return None

    state = load_pipeline_by_id(pipeline_id, subscription_id=sub)
    if not state:
        log.debug("sync_progress.kafka_status_no_db_row", subscription_id=sub, pipeline_id=pipeline_id)
        stage = payload.get("stage")
        status = payload.get("status") or "running"
        entry = {
            "pipeline_id": pipeline_id,
            "subscription_id": sub,
            "status": "running" if status in {"running", "queued"} else status,
            "current_stage": stage,
            "progress_pct": int(payload.get("progress_pct") or 0),
            "stages": {
                s: {"status": "pending", "started_at": None, "completed_at": None, "error": None}
                for s in STAGE_ORDER
            },
            "error": payload.get("error"),
            "started_at": _iso(envelope.created_at),
            "completed_at": None,
            "analysis_job_id": None,
        }
        if stage and stage in STAGE_ORDER:
            for s in STAGE_ORDER:
                idx = STAGE_ORDER.index(s)
                stage_idx = STAGE_ORDER.index(stage)
                if idx < stage_idx:
                    entry["stages"][s]["status"] = "done"
                elif s == stage:
                    entry["stages"][s]["status"] = status
        return notify_progress_updated(entry, event_type="progress", source="kafka")

    return notify_progress_updated(state, event_type="progress", source="kafka")


def apply_kafka_completed_event(envelope) -> dict[str, Any] | None:
    """Apply sync.pipeline.completed Kafka message."""
    from app.sync_orchestrator import load_pipeline_by_id

    payload = envelope.payload or {}
    sub = (envelope.subscription_id or "").strip().lower()
    pipeline_id = (envelope.pipeline_id or "").strip()
    terminal_status = (payload.get("status") or "completed").lower()

    state = load_pipeline_by_id(pipeline_id, subscription_id=sub)
    if state and terminal_status == "completed" and state.get("status") != "completed":
        state = dict(state)
        state["status"] = "completed"
        state["current_stage"] = "completed"
        state["progress_pct"] = 100

    if not state:
        state = {
            "pipeline_id": pipeline_id,
            "subscription_id": sub,
            "status": terminal_status,
            "current_stage": "completed" if terminal_status == "completed" else None,
            "progress_pct": 100 if terminal_status == "completed" else 0,
            "stages": {
                s: {
                    "status": "done" if terminal_status == "completed" else "pending",
                    "started_at": None,
                    "completed_at": _iso(envelope.created_at) if terminal_status == "completed" else None,
                    "error": None,
                }
                for s in STAGE_ORDER
            },
            "error": payload.get("error"),
            "started_at": _iso(envelope.created_at),
            "completed_at": _iso(envelope.created_at) if terminal_status == "completed" else None,
            "analysis_job_id": None,
        }

    event_type = "completed" if terminal_status == "completed" else "failed"
    return notify_progress_updated(state, event_type=event_type, source="kafka")


def get_subscription_progress(subscription_id: str, *, resume: bool = False) -> dict[str, Any] | None:
    """Return progress for one subscription (cache preferred when fresher)."""
    sub = (subscription_id or "").strip().lower()
    if not sub:
        return None

    with _lock:
        cached = _cache_by_sub.get(sub)

    db_state = get_pipeline_status(sub, resume=resume)
    if cached and db_state:
        cached_at = _parse_iso(cached.get("updated_at"))
        db_updated = _parse_iso(db_state.get("completed_at") or db_state.get("started_at"))
        if cached_at and db_updated and cached_at >= db_updated:
            return cached
    if db_state:
        return serialize_progress_entry(db_state)
    return cached


def list_active_sync_progress(
    subscription_ids: list[str] | None = None,
    *,
    active_only: bool = True,
    resume: bool = False,
) -> list[dict[str, Any]]:
    """List sync progress rows suitable for the dashboard top bar."""
    from app.database import SessionLocal
    from app.models import FullSyncPipelineRun
    from app.sync_orchestrator import _state_from_pipeline_row, expire_stale_pipeline_runs

    expire_stale_pipeline_runs()
    subs_filter = [(s or "").strip().lower() for s in (subscription_ids or []) if (s or "").strip()]
    subs_filter = list(dict.fromkeys(subs_filter))

    db = SessionLocal()
    try:
        q = db.query(FullSyncPipelineRun)
        if active_only:
            q = q.filter(FullSyncPipelineRun.status.in_(["queued", "running"]))
        if subs_filter:
            q = q.filter(FullSyncPipelineRun.subscription_id.in_(subs_filter))
        rows = q.order_by(FullSyncPipelineRun.created_at.desc()).all()
        by_sub: dict[str, dict[str, Any]] = {}
        for row in rows:
            sub = (row.subscription_id or "").strip().lower()
            if sub and sub not in by_sub:
                by_sub[sub] = serialize_progress_entry(_state_from_pipeline_row(row)) or {}
    finally:
        db.close()

    with _lock:
        for sub, cached in _cache_by_sub.items():
            if subs_filter and sub not in subs_filter:
                continue
            if not active_only or cached.get("pending"):
                existing = by_sub.get(sub)
                if not existing:
                    by_sub[sub] = cached
                    continue
                cached_at = _parse_iso(cached.get("updated_at"))
                existing_at = _parse_iso(existing.get("updated_at"))
                if cached_at and (not existing_at or cached_at >= existing_at):
                    by_sub[sub] = cached

    if subs_filter:
        for sub in subs_filter:
            if sub in by_sub:
                continue
            entry = get_subscription_progress(sub, resume=resume)
            if entry and (not active_only or entry.get("pending")):
                by_sub[sub] = entry

    return [row for row in by_sub.values() if row.get("pipeline_id")]


def build_progress_response(
    subscription_ids: list[str] | None = None,
    *,
    active_only: bool = True,
    resume: bool = False,
) -> dict[str, Any]:
    """Aggregate response for GET /sync/progress."""
    rows = list_active_sync_progress(subscription_ids, active_only=active_only, resume=resume)
    return {
        "updated_at": _iso(_now()),
        "active_count": sum(1 for row in rows if row.get("pending")),
        "subscriptions": rows,
    }

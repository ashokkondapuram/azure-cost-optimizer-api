"""Background optimization analysis jobs — full engine run per job (no throttling)."""
from __future__ import annotations

import json
import os
import uuid
import structlog
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session
import sqlalchemy.exc

from app.database import SessionLocal
from app.analysis import run_db_analysis
from app.analysis_cooldown import assert_full_analysis_allowed
from app.models import AnalysisJob
from app.optimizer.component_map import (
    ANALYSIS_BATCHES,
    resolve_batches,
)
from app.sync_scope import normalize_sync_types

log = structlog.get_logger(__name__)


def _now():
    return datetime.now(timezone.utc)


def _as_utc(when: datetime | None) -> datetime | None:
    if when is None:
        return None
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def analysis_job_max_runtime_hours() -> float:
    return max(0.5, float(os.getenv("ANALYSIS_JOB_MAX_RUNTIME_HOURS", "4")))


def analysis_job_max_queue_minutes() -> float:
    return max(5.0, float(os.getenv("ANALYSIS_JOB_MAX_QUEUE_MINUTES", "30")))


def _stale_reason(job: AnalysisJob, *, now: datetime | None = None) -> str | None:
    """Return expiry reason when a queued/running job is no longer active."""
    if job.status not in {"queued", "running"}:
        return None
    now = now or _now()
    if job.status == "queued":
        created = _as_utc(job.created_at)
        if created and now - created > timedelta(minutes=analysis_job_max_queue_minutes()):
            return (
                f"Job remained queued for more than {int(analysis_job_max_queue_minutes())} minutes "
                "(worker may have restarted)."
            )
        return None
    started = _as_utc(job.started_at) or _as_utc(job.created_at)
    if started and now - started > timedelta(hours=analysis_job_max_runtime_hours()):
        return (
            f"Job exceeded the {analysis_job_max_runtime_hours():g}-hour analysis time limit "
            "(process may have restarted or hung)."
        )
    return None


def _emit_job_event(db: Session, job: AnalysisJob, event_type: str = "progress") -> None:
    from app.job_events import publish_job_event

    publish_job_event(job.subscription_id, {
        "type": event_type,
        "job": serialize_job(job),
    })


def _fail_job(db: Session, job: AnalysisJob, message: str) -> None:
    job.status = "failed"
    job.error_message = message[:2000]
    job.completed_at = _now()
    job.current_component = None
    try:
        components = json.loads(job.components_json or "[]")
    except json.JSONDecodeError:
        components = []
    for comp in components:
        if comp.get("status") in {None, "pending", "running"}:
            comp["status"] = "failed"
    job.components_json = json.dumps(components)
    db.commit()
    _emit_job_event(db, job, "failed")


def expire_stale_analysis_jobs(
    db: Session,
    *,
    subscription_id: str | None = None,
) -> list[str]:
    """Mark orphaned queued/running jobs as failed so new analysis can start."""
    now = _now()
    q = db.query(AnalysisJob).filter(AnalysisJob.status.in_(["queued", "running"]))
    if subscription_id:
        q = q.filter(AnalysisJob.subscription_id == subscription_id.strip().lower())
    expired: list[str] = []
    for job in q.all():
        reason = _stale_reason(job, now=now)
        if not reason:
            continue
        _fail_job(db, job, reason)
        expired.append(job.id)
        log.warning(
            "analysis.job_expired",
            job_id=job.id,
            subscription_id=job.subscription_id,
            status=job.status,
            reason=reason,
        )
    return expired


def cancel_analysis_job(db: Session, job_id: str, subscription_id: str) -> AnalysisJob:
    """Admin cancel for a queued or running job."""
    sub = subscription_id.strip().lower()
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    if not job or job.subscription_id != sub:
        raise ValueError("Analysis job not found")
    if job.status not in {"queued", "running"}:
        raise ValueError("Only queued or running jobs can be cancelled")
    _fail_job(db, job, "Cancelled by user.")
    return job


def has_active_analysis_job(db: Session, subscription_id: str) -> bool:
    sub = subscription_id.lower()
    expire_stale_analysis_jobs(db, subscription_id=sub)
    return (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.subscription_id == sub,
            AnalysisJob.status.in_(["queued", "running"]),
        )
        .count()
        > 0
    )


def _job_progress_label(scope_components: list[str] | None, *, skip_monitor_fetch: bool = False) -> str:
    """Single-step jobs run the full engine once; label the UI accordingly."""
    if skip_monitor_fetch:
        return "Rule refresh"
    if not scope_components:
        return "Full analysis"
    batches = resolve_batches(scope_components)
    if len(batches) >= len(ANALYSIS_BATCHES):
        return "Full analysis"
    if len(batches) == 1:
        return batches[0]["component"]
    return ", ".join(b["component"] for b in batches)


def _label_for_scope(
    scope_resource_types: list[str] | None,
    scope_components: list[str] | None,
    *,
    skip_monitor_fetch: bool = False,
) -> str:
    if skip_monitor_fetch:
        return "Rule refresh"
    if scope_resource_types:
        if len(scope_resource_types) == 1:
            return scope_resource_types[0]
        return ", ".join(scope_resource_types)
    return _job_progress_label(scope_components, skip_monitor_fetch=skip_monitor_fetch)


def _execution_scope_from_job(job: AnalysisJob) -> tuple[list[str] | None, list[str], bool]:
    """Resolve analysis scope from persisted job metadata (not UI labels)."""
    try:
        components_meta = json.loads(job.components_json or "[]")
    except json.JSONDecodeError:
        components_meta = []

    scope_resource_types: list[str] = []
    analysis_scope_components: list[str] = []
    skip_monitor_fetch = False
    display_labels = frozenset({"Full analysis", "Rule refresh"})
    valid_component_names = {b["component"] for b in ANALYSIS_BATCHES}

    for entry in components_meta:
        skip_monitor_fetch = skip_monitor_fetch or bool(entry.get("skip_monitor_fetch"))
        for ct in entry.get("scope_resource_types") or []:
            if ct and ct not in scope_resource_types:
                scope_resource_types.append(ct)
        for comp in entry.get("analysis_scope_components") or []:
            if comp and comp not in analysis_scope_components:
                analysis_scope_components.append(comp)

    if not analysis_scope_components:
        # Backward compatibility: older jobs only stored the display label.
        for entry in components_meta:
            label = (entry.get("component") or "").strip()
            if label and label not in display_labels and label in valid_component_names:
                analysis_scope_components.append(label)

    if skip_monitor_fetch:
        return None, [], True

    return (analysis_scope_components or None), scope_resource_types, False


def _is_scoped_analysis(
    scope_components: list[str] | None,
    scope_resource_types: list[str],
) -> bool:
    if scope_resource_types:
        return True
    if not scope_components:
        return False
    return len(resolve_batches(scope_components)) < len(ANALYSIS_BATCHES)


def create_analysis_job(
    db: Session,
    *,
    subscription_id: str,
    profile: str = "default",
    engine_version: str = "extended",
    rule_overrides: dict | None = None,
    scope_components: list[str] | None = None,
    scope_resource_types: list[str] | None = None,
    skip_monitor_fetch: bool = False,
) -> AnalysisJob:
    sub = subscription_id.lower()
    if has_active_analysis_job(db, sub):
        raise ValueError("Analysis already in progress for this subscription")
    assert_full_analysis_allowed(
        db,
        sub,
        scope_components=scope_components,
        scope_resource_types=scope_resource_types,
        skip_monitor_fetch=skip_monitor_fetch,
    )
    if scope_resource_types:
        batches = []
    else:
        batches = resolve_batches(scope_components)
    label = _label_for_scope(
        scope_resource_types,
        scope_components,
        skip_monitor_fetch=skip_monitor_fetch,
    )
    components = [
        {
            "component": label,
            "status": "pending",
            "findings": 0,
            "savings_usd": 0.0,
            "skip_monitor_fetch": skip_monitor_fetch,
            "scope_resource_types": list(scope_resource_types or []),
            "analysis_scope_components": list(scope_components) if scope_components else [],
        },
    ]
    job = AnalysisJob(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        profile=profile,
        engine_version=engine_version.lower(),
        status="queued",
        progress_pct=0,
        total_batches=1,
        completed_batches=0,
        components_json=json.dumps(components),
        rule_overrides_json=json.dumps(rule_overrides or {}),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    _emit_job_event(db, job, "queued")
    return job


def queue_post_sync_analysis(
    db: Session,
    background_tasks: BackgroundTasks,
    *,
    subscription_id: str,
    type_list: list[str] | None = None,
    components: str | None = None,
    profile: str = "default",
    engine_version: str = "extended",
) -> dict:
    """Always queue a full optimization run after inventory sync."""
    sub = subscription_id.lower()

    scope_components = None
    scope_resource_types = None
    if components:
        scope_components = [c.strip() for c in components.split(",") if c.strip()] or None
    elif type_list:
        types_set = normalize_sync_types(type_list)
        if types_set:
            scope_resource_types = sorted(types_set)

    try:
        job = create_analysis_job(
            db,
            subscription_id=sub,
            profile=profile,
            engine_version=engine_version,
            scope_components=scope_components,
            scope_resource_types=scope_resource_types,
        )
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}

    background_tasks.add_task(execute_batch_job, job.id)
    return {
        "status": "queued",
        "job_id": job.id,
        "scoped": bool(scope_components or scope_resource_types),
        "message": "Analysis started in the background. Check Optimization center for progress.",
    }


def serialize_job(job: AnalysisJob) -> dict:
    try:
        components = json.loads(job.components_json or "[]")
    except json.JSONDecodeError:
        components = []
    scope_label = "Full analysis"
    if components:
        names = [c.get("component") for c in components if c.get("component")]
        if len(names) == 1:
            scope_label = names[0]
        elif names:
            scope_label = ", ".join(names)

    elapsed_seconds = None
    if job.started_at and job.status == "running":
        elapsed_seconds = max(0, int((_now() - _as_utc(job.started_at)).total_seconds()))
    elif job.started_at and job.completed_at and job.status in {"completed", "failed"}:
        elapsed_seconds = max(0, int((_as_utc(job.completed_at) - _as_utc(job.started_at)).total_seconds()))

    stale_reason = _stale_reason(job)

    status_labels = {
        "queued": "Queued",
        "running": "Running",
        "completed": "Completed",
        "failed": "Failed",
    }

    return {
        "id": job.id,
        "subscription_id": job.subscription_id,
        "profile": job.profile,
        "engine_version": job.engine_version,
        "status": job.status,
        "status_label": status_labels.get(job.status, job.status),
        "progress_pct": job.progress_pct or 0,
        "current_component": job.current_component,
        "current_step": job.current_component,
        "total_batches": job.total_batches or 0,
        "completed_batches": job.completed_batches or 0,
        "components": components,
        "scope_label": scope_label,
        "run_id": job.run_id,
        "error_message": job.error_message,
        "is_active": job.status in {"queued", "running"},
        "is_stale": stale_reason is not None,
        "stale_reason": stale_reason,
        "elapsed_seconds": elapsed_seconds,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def job_history_snapshot(job: AnalysisJob | None) -> dict | None:
    """Compact job payload for run history list and detail."""
    if not job:
        return None
    payload = serialize_job(job)
    return {
        "id": payload["id"],
        "status": payload["status"],
        "status_label": payload["status_label"],
        "progress_pct": payload.get("progress_pct"),
        "scope_label": payload.get("scope_label"),
        "components": payload.get("components") or [],
        "error_message": payload.get("error_message"),
        "is_active": payload.get("is_active"),
        "created_at": payload.get("created_at"),
        "started_at": payload.get("started_at"),
        "completed_at": payload.get("completed_at"),
    }


def jobs_by_run_ids(
    db: Session,
    subscription_id: str,
    run_ids: list[str],
) -> dict[str, AnalysisJob]:
    if not run_ids:
        return {}
    sub = subscription_id.strip().lower()
    rows = (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.subscription_id == sub,
            AnalysisJob.run_id.in_(run_ids),
        )
        .all()
    )
    out: dict[str, AnalysisJob] = {}
    for job in rows:
        if job.run_id and job.run_id not in out:
            out[job.run_id] = job
    return out


def job_for_run(db: Session, subscription_id: str, run_id: str) -> AnalysisJob | None:
    sub = subscription_id.strip().lower()
    return (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.subscription_id == sub,
            AnalysisJob.run_id == run_id,
        )
        .order_by(AnalysisJob.completed_at.desc())
        .first()
    )


def _mark_job_components_completed(job: AnalysisJob, findings_count: int, savings_usd: float) -> None:
    try:
        components = json.loads(job.components_json or "[]")
    except json.JSONDecodeError:
        components = []
    for comp in components:
        comp["status"] = "completed"
        comp["findings"] = findings_count
        comp["savings_usd"] = round(savings_usd, 2)
    job.components_json = json.dumps(components)


def _update_job_progress(
    db: Session,
    job: AnalysisJob,
    *,
    pct: int,
    component: str | None = None,
    completed_batches: int | None = None,
) -> None:
    job.progress_pct = max(0, min(100, pct))
    if component is not None:
        job.current_component = component
    if completed_batches is not None:
        job.completed_batches = completed_batches
    db.commit()
    _emit_job_event(db, job, "progress")


def execute_batch_job(job_id: str) -> None:
    """Run full DB analysis for a queued job (single pass, no per-component throttling)."""
    db = SessionLocal()
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job or job.status not in {"queued", "running"}:
            return

        if _stale_reason(job):
            _fail_job(db, job, _stale_reason(job) or "Job expired.")
            return

        other_running = (
            db.query(AnalysisJob)
            .filter(
                AnalysisJob.subscription_id == job.subscription_id,
                AnalysisJob.status == "running",
                AnalysisJob.id != job_id,
            )
            .first()
        )
        if other_running:
            job.status = "failed"
            job.error_message = "Another analysis job is already running for this subscription"
            job.completed_at = _now()
            db.commit()
            _emit_job_event(db, job, "failed")
            return

        job.status = "running"
        job.started_at = _now()
        job.progress_pct = 0
        db.commit()
        _emit_job_event(db, job, "started")

        try:
            job_rule_overrides = json.loads(job.rule_overrides_json or "{}")
        except json.JSONDecodeError:
            job_rule_overrides = {}

        scope_components, scope_resource_types, skip_monitor_fetch = _execution_scope_from_job(job)
        if skip_monitor_fetch:
            scoped = False
        else:
            scoped = _is_scoped_analysis(scope_components, scope_resource_types)

        def on_progress(pct: int, component: str | None = None) -> None:
            _update_job_progress(db, job, pct=pct, component=component)

        result = run_db_analysis(
            db,
            subscription_id=job.subscription_id,
            profile=job.profile,
            engine_version=job.engine_version,
            rule_overrides=job_rule_overrides,
            scope_components=scope_components if scoped and not scope_resource_types else None,
            scope_resource_types=scope_resource_types or None,
            progress_callback=on_progress,
            fetch_monitor_metrics=not skip_monitor_fetch,
        )

        findings_count = result.get("summary", {}).get("total_findings", 0)
        savings_usd = result.get("summary", {}).get("total_estimated_monthly_savings_usd", 0.0)
        _mark_job_components_completed(job, findings_count, savings_usd)

        job.run_id = result["run_id"]
        job.status = "completed"
        job.progress_pct = 100
        job.completed_batches = job.total_batches or 1
        job.current_component = None
        job.completed_at = _now()
        db.commit()
        _emit_job_event(db, job, "completed")

        log.info(
            "analysis.completed",
            job_id=job_id,
            subscription_id=job.subscription_id,
            findings=findings_count,
            skip_monitor_fetch=skip_monitor_fetch,
        )

        try:
            from app.operations_scheduler import (
                run_scheduled_engine_scoring,
                scheduled_engine_scoring_after_analysis,
                scheduled_engine_scoring_enabled,
            )

            if scheduled_engine_scoring_after_analysis() and scheduled_engine_scoring_enabled():
                run_scheduled_engine_scoring([job.subscription_id])
        except Exception as exc:
            log.warning(
                "analysis.engine_scoring_after_job_failed",
                job_id=job_id,
                subscription_id=job.subscription_id,
                error=str(exc)[:500],
            )
    except ValueError as exc:
        log.warning("analysis.skipped", job_id=job_id, error=str(exc))
        db.rollback()
        try:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = str(exc)[:2000]
                job.completed_at = _now()
                db.commit()
                _emit_job_event(db, job, "failed")
        except (sqlalchemy.exc.SQLAlchemyError, Exception) as db_exc:
            log.warning("analysis.failed_to_mark_failed", job_id=job_id, error=str(db_exc))
            db.rollback()
    except Exception as exc:
        log.exception("analysis.failed", job_id=job_id, error=str(exc))
        db.rollback()
        try:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = str(exc)[:2000]
                job.completed_at = _now()
                db.commit()
                _emit_job_event(db, job, "failed")
        except (sqlalchemy.exc.SQLAlchemyError, Exception) as db_exc:
            log.warning("analysis.failed_to_mark_failed", job_id=job_id, error=str(db_exc))
            db.rollback()
    finally:
        db.close()


def queue_rule_config_reanalysis(
    db: Session,
    background_tasks: BackgroundTasks,
    *,
    profile: str = "default",
    engine_version: str = "extended",
) -> dict:
    """
    Re-run the optimization engine for every known subscription using DB inventory
    and cached monitor facts (no Azure fetch). Triggered after engine rule changes.
    """
    from app.subscription_store import list_subscriptions_db

    subs = sorted({
        (s.get("subscriptionId") or "").strip().lower()
        for s in list_subscriptions_db(db)
        if s.get("subscriptionId")
    })
    queued: list[str] = []
    skipped: list[dict[str, str]] = []

    for sub in subs:
        try:
            job = create_analysis_job(
                db,
                subscription_id=sub,
                profile=profile,
                engine_version=engine_version,
                skip_monitor_fetch=True,
            )
            background_tasks.add_task(execute_batch_job, job.id)
            queued.append(sub)
        except ValueError as exc:
            skipped.append({"subscription_id": sub, "reason": str(exc)[:500]})

    log.info(
        "rule_config.reanalysis_queued",
        profile=profile,
        queued=len(queued),
        skipped=len(skipped),
    )
    return {
        "status": "queued" if queued else "skipped",
        "profile": profile,
        "queued_subscriptions": queued,
        "skipped": skipped,
        "message": (
            "Recommendations are refreshing in the background using synced inventory "
            "and cached metrics (no Azure fetch)."
            if queued
            else "No subscriptions were queued — analysis may already be running."
        ),
    }

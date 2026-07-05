"""Scheduled background workers for Azure inventory sync and optimization analysis.

Runs inside the API process (daemon threads), similar to ``cost_scheduler``.
Use PostgreSQL advisory locks so only one worker runs sync across scaled instances.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.db_locks import (
    ENGINE_SCORING_ADVISORY_LOCK_ID,
    SCHEDULER_ADVISORY_LOCK_ID,
    release_lock,
    try_acquire_lock,
)
from app.scheduler_utils import env_bool, list_subscription_ids

log = structlog.get_logger()

_started = False
_start_lock = threading.Lock()

# Thread-safe status state
_status_lock = threading.Lock()
_last_sync_at: datetime | None = None
_last_analysis_at: datetime | None = None
_last_rollout_check_at: datetime | None = None
_last_engine_scoring_at: datetime | None = None
_last_sync_result: dict[str, Any] | None = None
_last_analysis_result: dict[str, Any] | None = None
_last_rollout_check_result: dict[str, Any] | None = None
_last_engine_scoring_result: dict[str, Any] | None = None


def _set_status(**kwargs: Any) -> None:
    """Thread-safe update of scheduler status globals."""
    global _last_sync_at, _last_analysis_at, _last_rollout_check_at, _last_engine_scoring_at
    global _last_sync_result, _last_analysis_result, _last_rollout_check_result, _last_engine_scoring_result
    with _status_lock:
        for k, v in kwargs.items():
            globals()[k] = v


def _default_operations_enabled() -> bool:
    from app.settings import get_settings
    return get_settings().is_production


def scheduled_operations_enabled() -> bool:
    if os.getenv("SCHEDULED_OPERATIONS_ENABLED") is not None:
        return env_bool("SCHEDULED_OPERATIONS_ENABLED", False)
    return _default_operations_enabled()


def scheduled_sync_enabled() -> bool:
    """Full inventory+cost sync (sync_all). Disabled when component sync is active."""
    if os.getenv("SCHEDULED_SYNC_ENABLED") is not None:
        return env_bool("SCHEDULED_SYNC_ENABLED", False)
    from app.component_sync_worker import component_sync_enabled
    if component_sync_enabled():
        return env_bool("SCHEDULED_FULL_SYNC_ENABLED", False)
    return scheduled_operations_enabled()


def scheduled_analysis_enabled() -> bool:
    if os.getenv("SCHEDULED_ANALYSIS_ENABLED") is not None:
        return env_bool("SCHEDULED_ANALYSIS_ENABLED", False)
    return scheduled_operations_enabled()


def scheduled_analysis_after_sync() -> bool:
    return env_bool("SCHEDULED_ANALYSIS_AFTER_SYNC", True)


def scheduled_rollout_observation_enabled() -> bool:
    if os.getenv("SCHEDULED_ROLLOUT_OBSERVATION_ENABLED") is not None:
        return env_bool("SCHEDULED_ROLLOUT_OBSERVATION_ENABLED", False)
    return scheduled_operations_enabled()


def scheduled_engine_scoring_enabled() -> bool:
    """Run advanced scoring + decision engine on a fixed interval (DB-only, no Azure APIs)."""
    if os.getenv("SCHEDULED_ENGINE_SCORING_ENABLED") is not None:
        return env_bool("SCHEDULED_ENGINE_SCORING_ENABLED", False)
    return scheduled_operations_enabled()


def scheduled_engine_scoring_after_analysis() -> bool:
    return env_bool("SCHEDULED_ENGINE_SCORING_AFTER_ANALYSIS", True)


def _rollout_observation_interval_seconds() -> float:
    return max(1.0, float(os.getenv("ROLLOUT_OBSERVATION_HOURS", "6"))) * 3600.0


def _sync_interval_seconds() -> float:
    return max(1.0, float(os.getenv("SCHEDULED_SYNC_HOURS", "24"))) * 3600.0


def _analysis_interval_seconds() -> float:
    return max(1.0, float(os.getenv("SCHEDULED_ANALYSIS_HOURS", "6"))) * 3600.0


def _engine_scoring_interval_seconds() -> float:
    return max(1.0, float(os.getenv("SCHEDULED_ENGINE_SCORING_HOURS", "3"))) * 3600.0


def _startup_delay_seconds() -> float:
    return max(15.0, float(os.getenv("SCHEDULED_STARTUP_DELAY_SECONDS", "60")))


# Stagger offsets (seconds) to prevent thundering-herd at startup
_ANALYSIS_STAGGER_SEC = 30.0
_ROLLOUT_STAGGER_SEC = 45.0
_ENGINE_SCORING_STAGGER_SEC = 60.0


# ---------------------------------------------------------------------------
# Advisory lock helpers (delegated to db_locks, kept here for backward compat)
# ---------------------------------------------------------------------------

def _try_acquire_scheduler_lock(db: Session) -> bool:
    return try_acquire_lock(db, SCHEDULER_ADVISORY_LOCK_ID)


def _release_scheduler_lock(db: Session) -> None:
    release_lock(db, SCHEDULER_ADVISORY_LOCK_ID)


def _try_acquire_engine_scoring_lock(db: Session) -> bool:
    return try_acquire_lock(db, ENGINE_SCORING_ADVISORY_LOCK_ID)


def _release_engine_scoring_lock(db: Session) -> None:
    release_lock(db, ENGINE_SCORING_ADVISORY_LOCK_ID)


def _has_active_analysis_job(db: Session, subscription_id: str) -> bool:
    from app.batch_analyzer import has_active_analysis_job
    return has_active_analysis_job(db, subscription_id)


def run_scheduled_sync() -> list[str]:
    """Pull fresh inventory + costs for every known subscription."""
    from app.auth import get_token, reload_credential
    from app.database import SessionLocal
    from app.db_sync import sync_all

    db = SessionLocal()
    synced: list[str] = []
    errors: list[dict[str, str]] = []
    try:
        if not _try_acquire_scheduler_lock(db):
            log.info("scheduled_sync.skipped", reason="lock_held")
            _set_status(_last_sync_result={"status": "skipped", "reason": "lock_held", "synced": []})
            return synced

        reload_credential(db)
        token = get_token(db)
        subs = list_subscription_ids(db)
        if not subs:
            log.info("scheduled_sync.skipped", reason="no_subscriptions")
            _set_status(_last_sync_result={"status": "skipped", "reason": "no_subscriptions", "synced": []})
            return synced

        log.info("scheduled_sync.start", subscriptions=len(subs))
        for sub in subs:
            try:
                sync_all(sub, db, token)
                synced.append(sub)
                log.info("scheduled_sync.subscription_done", subscription_id=sub)
            except Exception as exc:
                errors.append({"subscription_id": sub, "error": str(exc)[:500]})
                log.exception("scheduled_sync.subscription_failed", subscription_id=sub, error=str(exc))

        _set_status(
            _last_sync_at=datetime.now(timezone.utc),
            _last_sync_result={
                "status": "ok" if synced else "failed",
                "synced": synced,
                "errors": errors,
            },
        )
        return synced
    finally:
        try:
            _release_scheduler_lock(db)
        except Exception:
            pass
        db.close()


def run_scheduled_analysis(subscription_ids: list[str] | None = None) -> dict[str, Any]:
    """Run the optimization engine for subscriptions without an active analysis job."""
    from app.batch_analyzer import create_analysis_job, execute_batch_job
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        subs = subscription_ids or list_subscription_ids(db)
    finally:
        db.close()

    if not subs:
        result: dict[str, Any] = {"status": "skipped", "reason": "no_subscriptions", "completed": [], "skipped": [], "errors": []}
        _set_status(_last_analysis_result=result)
        return result

    completed: list[str] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    log.info("scheduled_analysis.start", subscriptions=len(subs))
    for sub in subs:
        # Single session per subscription unit-of-work
        db = SessionLocal()
        try:
            if _has_active_analysis_job(db, sub):
                skipped.append({"subscription_id": sub, "reason": "job_active"})
                log.info("scheduled_analysis.skipped", subscription_id=sub, reason="job_active")
                continue
            try:
                job = create_analysis_job(db, subscription_id=sub)
                job_id = job.id
            except ValueError as exc:
                skipped.append({"subscription_id": sub, "reason": str(exc)[:500]})
                log.warning("scheduled_analysis.skipped", subscription_id=sub, error=str(exc))
                continue
        finally:
            db.close()

        try:
            execute_batch_job(job_id)
            completed.append(sub)
            log.info("scheduled_analysis.subscription_done", subscription_id=sub, job_id=job_id)
        except Exception as exc:
            errors.append({"subscription_id": sub, "error": str(exc)[:500]})
            log.exception("scheduled_analysis.subscription_failed", subscription_id=sub, error=str(exc))

    result = {
        "status": "ok" if completed else ("partial" if errors else "skipped"),
        "completed": completed,
        "skipped": skipped,
        "errors": errors,
    }
    _set_status(
        _last_analysis_at=datetime.now(timezone.utc),
        _last_analysis_result=result,
    )

    if (
        completed
        and scheduled_engine_scoring_enabled()
        and scheduled_engine_scoring_after_analysis()
    ):
        try:
            scoring_result = run_scheduled_engine_scoring(completed)
            result["engine_scoring"] = scoring_result
        except Exception as exc:
            log.exception("scheduled_engine_scoring.after_analysis_failed", error=str(exc))
            result["engine_scoring"] = {"status": "failed", "error": str(exc)[:500]}

    return result


def run_scheduled_rollout_observation() -> dict[str, Any]:
    """Evaluate in-progress rollout stages for observation window completion."""
    from app.database import SessionLocal
    from app.rollout_observer import check_all_subscriptions

    db = SessionLocal()
    try:
        result = check_all_subscriptions(db)
        _set_status(
            _last_rollout_check_at=datetime.now(timezone.utc),
            _last_rollout_check_result=result,
        )
        return result
    finally:
        db.close()


def run_scheduled_engine_scoring(subscription_ids: list[str] | None = None) -> dict[str, Any]:
    """Run advanced scoring then decision engine for each subscription (database only).

    FIX: Advisory lock is now held on a single session for the entire operation
    lifetime, preventing the lock-released-on-wrong-connection bug.
    """
    from app.advanced_scoring import score_subscription
    from app.database import SessionLocal
    from app.optimizer.decision_engine import generate_optimization_actions

    # Resolve subscription list on a short-lived session
    db_list = SessionLocal()
    try:
        subs = subscription_ids or list_subscription_ids(db_list)
    finally:
        db_list.close()

    if not subs:
        result: dict[str, Any] = {
            "status": "skipped",
            "reason": "no_subscriptions",
            "completed": [],
            "errors": [],
        }
        _set_status(_last_engine_scoring_result=result)
        return result

    # Hold the advisory lock on a dedicated session kept open for the full scoring run
    db_lock = SessionLocal()
    lock_held = False
    try:
        lock_held = _try_acquire_engine_scoring_lock(db_lock)
        if not lock_held:
            log.info("scheduled_engine_scoring.skipped", reason="lock_held")
            result = {"status": "skipped", "reason": "lock_held", "completed": [], "errors": []}
            _set_status(_last_engine_scoring_result=result)
            return result

        completed: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        log.info("scheduled_engine_scoring.start", subscriptions=len(subs))
        for sub in subs:
            db = SessionLocal()
            try:
                scoring = score_subscription(db, sub)
                decision = generate_optimization_actions(db, sub)
                completed.append({
                    "subscription_id": sub,
                    "scoring_total": scoring.get("scoring", {}).get("total", 0),
                    "actions_created": decision.get("created", 0),
                    "actions_updated": decision.get("updated", 0),
                })
                log.info(
                    "scheduled_engine_scoring.subscription_done",
                    subscription_id=sub,
                    scoring_total=scoring.get("scoring", {}).get("total", 0),
                    actions_created=decision.get("created", 0),
                    actions_updated=decision.get("updated", 0),
                )
            except Exception as exc:
                errors.append({"subscription_id": sub, "error": str(exc)[:500]})
                log.exception(
                    "scheduled_engine_scoring.subscription_failed",
                    subscription_id=sub,
                    error=str(exc),
                )
            finally:
                db.close()

        result = {
            "status": "ok" if completed and not errors else ("partial" if completed else "failed"),
            "completed": completed,
            "errors": errors,
        }
        _set_status(
            _last_engine_scoring_at=datetime.now(timezone.utc),
            _last_engine_scoring_result=result,
        )
        return result

    finally:
        if lock_held:
            try:
                _release_engine_scoring_lock(db_lock)
            except Exception:
                pass
        db_lock.close()


def _cost_scheduler_status() -> dict[str, Any]:
    try:
        from app.cost_scheduler import get_cost_scheduler_status
        return get_cost_scheduler_status()
    except Exception:
        return {"enabled": False}


def _resource_discovery_status() -> dict[str, Any]:
    try:
        from app.resource_discovery_worker import get_resource_discovery_status
        return get_resource_discovery_status()
    except Exception:
        return {"enabled": False}


def get_scheduler_status() -> dict[str, Any]:
    from app.component_sync_worker import component_sync_enabled, get_component_sync_status

    component_on = component_sync_enabled()
    full_sync_on = scheduled_sync_enabled()
    if full_sync_on:
        sync_mode = "full_inventory_and_costs"
    elif component_on:
        sync_mode = "per_component_rotation"
    else:
        sync_mode = "disabled"

    with _status_lock:
        return {
            "enabled": scheduled_operations_enabled(),
            "sync": {
                "enabled": full_sync_on,
                "interval_hours": float(os.getenv("SCHEDULED_SYNC_HOURS", "24")),
                "mode": sync_mode,
                "last_run_at": _last_sync_at.isoformat() if _last_sync_at else None,
                "last_result": _last_sync_result,
            },
            "component_sync": get_component_sync_status(),
            "cost_refresh": _cost_scheduler_status(),
            "resource_discovery": _resource_discovery_status(),
            "analysis": {
                "enabled": scheduled_analysis_enabled(),
                "interval_hours": float(os.getenv("SCHEDULED_ANALYSIS_HOURS", "6")),
                "after_sync": scheduled_analysis_after_sync(),
                "last_run_at": _last_analysis_at.isoformat() if _last_analysis_at else None,
                "last_result": _last_analysis_result,
            },
            "rollout_observation": {
                "enabled": scheduled_rollout_observation_enabled(),
                "interval_hours": float(os.getenv("ROLLOUT_OBSERVATION_HOURS", "6")),
                "last_run_at": _last_rollout_check_at.isoformat() if _last_rollout_check_at else None,
                "last_result": _last_rollout_check_result,
            },
            "engine_scoring": {
                "enabled": scheduled_engine_scoring_enabled(),
                "interval_hours": float(os.getenv("SCHEDULED_ENGINE_SCORING_HOURS", "3")),
                "after_analysis": scheduled_engine_scoring_after_analysis(),
                "last_run_at": _last_engine_scoring_at.isoformat() if _last_engine_scoring_at else None,
                "last_result": _last_engine_scoring_result,
                "steps": ["advanced_scoring", "decision_engine"],
                "azure_api_calls": False,
            },
            "started": _started,
        }


def _sync_loop(interval_seconds: float) -> None:
    time.sleep(_startup_delay_seconds())
    while True:
        try:
            if scheduled_sync_enabled():
                synced = run_scheduled_sync()
                if scheduled_analysis_enabled() and scheduled_analysis_after_sync() and synced:
                    run_scheduled_analysis(synced)
        except Exception as exc:
            log.exception("scheduled_sync.cycle_failed", error=str(exc))
        time.sleep(interval_seconds)


def _analysis_loop(interval_seconds: float) -> None:
    time.sleep(_startup_delay_seconds() + _ANALYSIS_STAGGER_SEC)
    while True:
        try:
            if scheduled_analysis_enabled():
                run_scheduled_analysis()
        except Exception as exc:
            log.exception("scheduled_analysis.cycle_failed", error=str(exc))
        time.sleep(interval_seconds)


def _rollout_observation_loop(interval_seconds: float) -> None:
    time.sleep(_startup_delay_seconds() + _ROLLOUT_STAGGER_SEC)
    while True:
        try:
            if scheduled_rollout_observation_enabled():
                run_scheduled_rollout_observation()
        except Exception as exc:
            log.exception("rollout_observation.cycle_failed", error=str(exc))
        time.sleep(interval_seconds)


def _engine_scoring_loop(interval_seconds: float) -> None:
    time.sleep(_startup_delay_seconds() + _ENGINE_SCORING_STAGGER_SEC)
    while True:
        try:
            if scheduled_engine_scoring_enabled():
                run_scheduled_engine_scoring()
        except Exception as exc:
            log.exception("scheduled_engine_scoring.cycle_failed", error=str(exc))
        time.sleep(interval_seconds)


def start() -> None:
    """Start scheduled sync/analysis worker threads once (idempotent)."""
    global _started

    from app.component_sync_worker import component_sync_enabled, start_component_sync_worker

    if (
        not scheduled_sync_enabled()
        and not scheduled_analysis_enabled()
        and not component_sync_enabled()
        and not scheduled_rollout_observation_enabled()
        and not scheduled_engine_scoring_enabled()
    ):
        log.info("scheduled_operations.disabled")
        return

    with _start_lock:
        if _started:
            return

        if scheduled_sync_enabled():
            interval = _sync_interval_seconds()
            threading.Thread(
                target=_sync_loop,
                args=(interval,),
                daemon=True,
                name="scheduled-sync",
            ).start()
            log.info(
                "scheduled_sync.started",
                every_hours=interval / 3600.0,
                analysis_after_sync=scheduled_analysis_after_sync() and scheduled_analysis_enabled(),
            )

        run_analysis_loop = scheduled_analysis_enabled() and (
            not scheduled_sync_enabled() or not scheduled_analysis_after_sync()
        )
        if run_analysis_loop:
            interval = _analysis_interval_seconds()
            threading.Thread(
                target=_analysis_loop,
                args=(interval,),
                daemon=True,
                name="scheduled-analysis",
            ).start()
            log.info("scheduled_analysis.started", every_hours=interval / 3600.0)
        elif scheduled_analysis_enabled() and scheduled_sync_enabled():
            log.info("scheduled_analysis.chained_after_sync")

        start_component_sync_worker(startup_delay=_startup_delay_seconds())

        if scheduled_rollout_observation_enabled():
            rollout_interval = _rollout_observation_interval_seconds()
            threading.Thread(
                target=_rollout_observation_loop,
                args=(rollout_interval,),
                daemon=True,
                name="rollout-observation",
            ).start()
            log.info("rollout_observation.started", every_hours=rollout_interval / 3600.0)

        if scheduled_engine_scoring_enabled():
            engine_interval = _engine_scoring_interval_seconds()
            threading.Thread(
                target=_engine_scoring_loop,
                args=(engine_interval,),
                daemon=True,
                name="scheduled-engine-scoring",
            ).start()
            log.info("scheduled_engine_scoring.started", every_hours=engine_interval / 3600.0)

        _started = True
        log.info("scheduled_operations.started", status=get_scheduler_status())

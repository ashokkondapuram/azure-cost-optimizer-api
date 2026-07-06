"""Per-component scheduled inventory sync (rotating worker)."""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.component_sync_schedule import (
    component_sync_catalog,
    interval_minutes_for_component,
    pick_next_due_component,
)
from app.db_locks import SCHEDULER_ADVISORY_LOCK_ID, release_lock, try_acquire_lock
from app.optimizer.component_map import sync_types_for_component
from app.scheduler_utils import env_bool, list_subscription_ids

log = structlog.get_logger()

_component_started = False
_component_lock = threading.Lock()
_last_component_sync_at: dict[str, datetime] = {}
_last_component_sync_result: dict[str, Any] | None = None


def component_sync_enabled() -> bool:
    if os.getenv("SCHEDULED_COMPONENT_SYNC_ENABLED") is not None:
        return env_bool("SCHEDULED_COMPONENT_SYNC_ENABLED", False)
    from app.operations_scheduler import scheduled_operations_enabled
    return scheduled_operations_enabled()


def component_sync_tick_seconds() -> float:
    return max(60.0, float(os.getenv("SCHEDULED_COMPONENT_SYNC_TICK_MINUTES", "5")) * 60.0)


def analysis_after_component_sync() -> bool:
    return env_bool("SCHEDULED_ANALYSIS_AFTER_COMPONENT_SYNC", True)


def _as_utc(when: datetime) -> datetime:
    """Normalize DB-loaded timestamps to timezone-aware UTC."""
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def _hydrate_last_sync_from_db() -> None:
    """Load persisted per-component sync times (survives restarts)."""
    global _last_component_sync_at
    from app.database import SessionLocal
    from app.models import ComponentSyncState

    db = SessionLocal()
    try:
        rows = db.query(ComponentSyncState).all()
        for row in rows:
            if row.synced_at:
                _last_component_sync_at[row.component] = _as_utc(row.synced_at)
        if rows:
            log.info("scheduled_component_sync.hydrated", components=len(rows))
    except Exception as exc:
        log.warning("scheduled_component_sync.hydrate_failed", error=str(exc))
    finally:
        db.close()


def _persist_component_sync(db: Session, component: str, when: datetime, status: str) -> None:
    from app.models import ComponentSyncState

    row = db.query(ComponentSyncState).filter(ComponentSyncState.component == component).first()
    if row:
        row.synced_at = when
        row.last_status = status
    else:
        db.add(
            ComponentSyncState(
                component=component,
                synced_at=when,
                last_status=status,
            )
        )
    db.commit()


def _bust_subscription_caches(subscription_ids: list[str]) -> None:
    """Proactively evict stale cache entries for every just-synced subscription.

    Both the cost-query cache and the HTTP ETag / Cache-Control header cache
    are invalidated so that the next request sees fresh post-sync data instead
    of waiting for the TTL to expire naturally.
    """
    from app.cost_query_cache import invalidate_subscription_cost_cache

    for sub in subscription_ids:
        try:
            invalidate_subscription_cost_cache(sub)
        except Exception as exc:
            log.warning(
                "scheduled_component_sync.cache_bust_failed",
                subscription_id=sub,
                error=str(exc),
            )
    if subscription_ids:
        log.info(
            "scheduled_component_sync.cache_busted",
            subscriptions=len(subscription_ids),
        )


def run_component_sync(component: str) -> dict[str, Any]:
    """Sync one optimization component for all subscriptions."""
    from app.auth import get_token, reload_credential
    from app.batch_analyzer import create_analysis_job, execute_batch_job, has_active_analysis_job
    from app.database import SessionLocal
    from app.db_sync import sync_scoped

    global _last_component_sync_result

    types = sync_types_for_component(component)
    if not types:
        result = {"status": "skipped", "reason": "no_resource_types", "component": component}
        _last_component_sync_result = result
        return result

    db = SessionLocal()
    synced: list[str] = []
    errors: list[dict[str, str]] = []
    lock_held = False
    try:
        lock_held = try_acquire_lock(db, SCHEDULER_ADVISORY_LOCK_ID)
        if not lock_held:
            result = {"status": "skipped", "reason": "lock_held", "component": component}
            _last_component_sync_result = result
            return result

        reload_credential(db)
        token = get_token(db)
        subs = list_subscription_ids(db)
        if not subs:
            result = {"status": "skipped", "reason": "no_subscriptions", "component": component}
            _last_component_sync_result = result
            return result

        log.info("scheduled_component_sync.start", component=component, types=types, subscriptions=len(subs))
        for sub in subs:
            try:
                sync_scoped(sub, db, token, types, include_costs=False)
                synced.append(sub)
            except Exception as exc:
                errors.append({"subscription_id": sub, "error": str(exc)[:500]})
                log.exception(
                    "scheduled_component_sync.subscription_failed",
                    component=component,
                    subscription_id=sub,
                    error=str(exc),
                )

        if synced:
            synced_at = datetime.now(timezone.utc)
            _last_component_sync_at[component] = synced_at
            _persist_component_sync(db, component, synced_at, "ok")
            # Bust caches for all successfully synced subscriptions so the
            # next API request sees fresh post-sync data.
            _bust_subscription_caches(synced)

        result: dict[str, Any] = {
            "status": "ok" if synced else "failed",
            "component": component,
            "resource_types": types,
            "synced": synced,
            "errors": errors,
        }

        if analysis_after_component_sync() and synced:
            analysis_completed: list[str] = []
            analysis_skipped: list[dict[str, str]] = []
            for sub in synced:
                db2 = SessionLocal()
                try:
                    if has_active_analysis_job(db2, sub):
                        analysis_skipped.append({"subscription_id": sub, "reason": "job_active"})
                        continue
                    job = create_analysis_job(
                        db2,
                        subscription_id=sub,
                        scope_components=[component],
                    )
                    job_id = job.id
                except ValueError as exc:
                    analysis_skipped.append({"subscription_id": sub, "reason": str(exc)[:500]})
                    continue
                finally:
                    db2.close()
                try:
                    execute_batch_job(job_id)
                    analysis_completed.append(sub)
                except Exception as exc:
                    errors.append({"subscription_id": sub, "error": f"analysis: {exc}"[:500]})
            result["analysis"] = {
                "completed": analysis_completed,
                "skipped": analysis_skipped,
            }

        _last_component_sync_result = result
        log.info("scheduled_component_sync.done", **{k: v for k, v in result.items() if k != "analysis"})
        return result
    finally:
        if lock_held:
            try:
                release_lock(db, SCHEDULER_ADVISORY_LOCK_ID)
            except Exception:
                pass
        db.close()


def run_due_component_sync() -> dict[str, Any] | None:
    component, overdue = pick_next_due_component(_last_component_sync_at)
    if not component:
        return None
    log.info(
        "scheduled_component_sync.due",
        component=component,
        overdue_seconds=round(overdue, 1),
    )
    return run_component_sync(component)


def get_component_sync_status() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    components: list[dict[str, Any]] = []
    for entry in component_sync_catalog():
        component = entry["component"]
        last = _last_component_sync_at.get(component)
        if last is not None:
            last = _as_utc(last)
            _last_component_sync_at[component] = last
        interval_sec = interval_minutes_for_component(component) * 60.0
        enriched = dict(entry)
        if last:
            enriched["last_sync_at"] = last.isoformat()
            next_due = last + timedelta(seconds=interval_sec)
            enriched["next_due_at"] = next_due.isoformat()
            enriched["overdue_seconds"] = max(0.0, (now - next_due).total_seconds())
        else:
            enriched["last_sync_at"] = None
            enriched["next_due_at"] = None
            enriched["overdue_seconds"] = interval_sec
        components.append(enriched)

    return {
        "enabled": component_sync_enabled(),
        "tick_minutes": float(os.getenv("SCHEDULED_COMPONENT_SYNC_TICK_MINUTES", "5")),
        "analysis_after_sync": analysis_after_component_sync(),
        "intervals": {
            "fast_minutes": float(os.getenv("SCHEDULED_SYNC_INTERVAL_FAST_MINUTES", "15")),
            "standard_minutes": float(os.getenv("SCHEDULED_SYNC_INTERVAL_STANDARD_MINUTES", "30")),
            "slow_minutes": float(os.getenv("SCHEDULED_SYNC_INTERVAL_SLOW_MINUTES", "60")),
        },
        "components": components,
        "last_sync_at": {
            k: _as_utc(v).isoformat() for k, v in sorted(_last_component_sync_at.items())
        },
        "last_result": _last_component_sync_result,
        "started": _component_started,
    }


def _component_sync_loop(tick_seconds: float, startup_delay: float) -> None:
    time.sleep(startup_delay)
    while True:
        try:
            if component_sync_enabled():
                run_due_component_sync()
        except Exception as exc:
            log.exception("scheduled_component_sync.cycle_failed", error=str(exc))
        time.sleep(tick_seconds)


def start_component_sync_worker(*, startup_delay: float) -> None:
    global _component_started
    if not component_sync_enabled():
        log.info("scheduled_component_sync.disabled")
        return
    with _component_lock:
        if _component_started:
            return
        _hydrate_last_sync_from_db()
        tick = component_sync_tick_seconds()
        threading.Thread(
            target=_component_sync_loop,
            args=(tick, startup_delay),
            daemon=True,
            name="scheduled-component-sync",
        ).start()
        _component_started = True
        log.info(
            "scheduled_component_sync.started",
            tick_minutes=tick / 60.0,
            components=len(component_sync_catalog()),
        )

"""Background worker: persist Azure Monitor metrics into resource enrichment rows."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

import structlog

from app.settings import get_settings

log = structlog.get_logger()

_started = False
_lock = threading.Lock()
_last_run_at: datetime | None = None
_last_result: dict[str, Any] | None = None
_pending_syncs: set[str] = set()
_pending_lock = threading.Lock()


def metrics_sync_interval_hours() -> float:
    return metrics_sync_interval_minutes() / 60.0


def metrics_sync_interval_minutes() -> float:
    from app.sync_intervals import metrics_sync_interval_minutes as _minutes

    return _minutes()


def metrics_sync_worker_enabled() -> bool:
    return get_settings().metrics_sync_worker_enabled


def is_metrics_sync_pending(subscription_id: str) -> bool:
    sub = (subscription_id or "").strip().lower()
    with _pending_lock:
        return sub in _pending_syncs


def _list_subscription_ids(db) -> list[str]:
    from app.scheduler_utils import list_subscription_ids

    return list_subscription_ids(db)


def _refresh_once() -> None:
    global _last_run_at, _last_result
    from app.database import SessionLocal
    from app.workers.inventory_metrics_worker import run_inventory_metrics_worker

    log.info("metrics_sync_worker.start")
    db = SessionLocal()
    results: dict[str, Any] = {"subscriptions": [], "errors": []}
    try:
        for sub in _list_subscription_ids(db):
            if is_metrics_sync_pending(sub):
                log.info("metrics_sync_worker.skipped", subscription_id=sub, reason="pending")
                continue
            with _pending_lock:
                _pending_syncs.add(sub)
            try:
                stats = run_inventory_metrics_worker(db, sub, sync_context=True)
                results["subscriptions"].append(stats)
            except Exception as exc:
                results["errors"].append({"subscription_id": sub, "error": str(exc)[:500]})
                log.exception("metrics_sync_worker.sub_failed", subscription_id=sub, error=str(exc))
            finally:
                with _pending_lock:
                    _pending_syncs.discard(sub)
    finally:
        db.close()
    _last_run_at = datetime.now(timezone.utc)
    _last_result = results
    log.info(
        "metrics_sync_worker.complete",
        subscriptions=len(results["subscriptions"]),
        errors=len(results["errors"]),
    )


def _loop(interval_seconds: float, startup_delay: float) -> None:
    time.sleep(startup_delay)
    while True:
        try:
            if metrics_sync_worker_enabled():
                _refresh_once()
        except Exception as exc:
            log.exception("metrics_sync_worker.loop_failed", error=str(exc))
        time.sleep(interval_seconds)


def start_metrics_sync_worker(*, startup_delay: float | None = None) -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    from app.sync_intervals import metrics_sync_startup_delay_seconds

    delay = (
        startup_delay
        if startup_delay is not None
        else metrics_sync_startup_delay_seconds()
    )
    interval_minutes = metrics_sync_interval_minutes()
    interval = interval_minutes * 60.0
    thread = threading.Thread(
        target=_loop,
        args=(interval, delay),
        name="metrics-sync-worker",
        daemon=True,
    )
    thread.start()
    log.info(
        "metrics_sync_worker.scheduled",
        interval_minutes=interval_minutes,
        interval_hours=interval_minutes / 60.0,
        startup_delay_sec=delay,
    )


def worker_status() -> dict[str, Any]:
    return {
        "enabled": metrics_sync_worker_enabled(),
        "interval_minutes": metrics_sync_interval_minutes(),
        "interval_hours": metrics_sync_interval_hours(),
        "pending_syncs": sorted(_pending_syncs),
        "last_run_at": _last_run_at.isoformat() if _last_run_at else None,
        "last_result": _last_result,
    }

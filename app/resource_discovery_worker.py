"""Background worker: subscription-wide ARM resource discovery (inventory sync).

Lists all resources via ``GET /subscriptions/{id}/resources`` and upserts rows
that match the app's canonical inventory layout.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import structlog

log = structlog.get_logger()

_started = False
_lock = threading.Lock()
_last_run_at: datetime | None = None
_last_result: dict[str, Any] | None = None
_pending_syncs: set[str] = set()
_pending_lock = threading.Lock()


def inventory_sync_interval_minutes() -> float:
    from app.sync_intervals import inventory_sync_interval_minutes as _minutes

    return _minutes()


def resource_discovery_hours() -> float:
    return inventory_sync_interval_minutes() / 60.0


def inventory_sync_startup_delay_seconds() -> float:
    from app.sync_intervals import inventory_sync_startup_delay_seconds

    return inventory_sync_startup_delay_seconds()


def resource_discovery_worker_enabled() -> bool:
    raw = os.getenv("RESOURCE_DISCOVERY_WORKER_ENABLED")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def is_inventory_sync_pending(subscription_id: str) -> bool:
    sub = (subscription_id or "").strip().lower()
    with _pending_lock:
        return sub in _pending_syncs


def _list_subscription_ids(db) -> list[str]:
    from app.scheduler_utils import list_subscription_ids

    return list_subscription_ids(db)


def _refresh_once() -> None:
    global _last_run_at, _last_result
    from app.auth import get_token
    from app.database import SessionLocal
    from app.resource_discovery_sync import sync_resource_discovery

    log.info("inventory_sync_worker.start")
    db = SessionLocal()
    results: dict[str, Any] = {"subscriptions": [], "errors": []}
    try:
        token = get_token(db)
        for sub in _list_subscription_ids(db):
            if is_inventory_sync_pending(sub):
                log.info("inventory_sync_worker.skipped", subscription_id=sub, reason="pending")
                continue
            with _pending_lock:
                _pending_syncs.add(sub)
            try:
                synced = sync_resource_discovery(sub, db, token)
                results["subscriptions"].append(synced)
            except Exception as exc:
                results["errors"].append({"subscription_id": sub, "error": str(exc)[:500]})
                log.exception("inventory_sync_worker.sub_failed", subscription_id=sub, error=str(exc))
            finally:
                with _pending_lock:
                    _pending_syncs.discard(sub)
    finally:
        db.close()
    _last_run_at = datetime.now(timezone.utc)
    _last_result = results
    log.info(
        "inventory_sync_worker.complete",
        subscriptions=len(results["subscriptions"]),
        errors=len(results["errors"]),
    )


def _loop(interval_seconds: float, startup_delay: float) -> None:
    time.sleep(startup_delay)
    while True:
        try:
            if resource_discovery_worker_enabled():
                _refresh_once()
        except Exception as exc:
            log.warning("inventory_sync_worker.cycle_failed", error=str(exc))
        time.sleep(interval_seconds)


def get_resource_discovery_status() -> dict[str, Any]:
    minutes = inventory_sync_interval_minutes()
    return {
        "enabled": resource_discovery_worker_enabled(),
        "worker": "inventory_sync",
        "scope": "arm_resources_list",
        "interval_minutes": minutes,
        "interval_hours": minutes / 60.0,
        "startup_delay_sec": inventory_sync_startup_delay_seconds(),
        "pending_syncs": sorted(_pending_syncs),
        "last_run_at": _last_run_at.isoformat() if _last_run_at else None,
        "last_result": _last_result,
        "started": _started,
    }


def start() -> None:
    """Start the inventory sync worker thread once (idempotent)."""
    global _started
    if not resource_discovery_worker_enabled():
        log.info("inventory_sync_worker.disabled")
        return
    with _lock:
        if _started:
            return
        minutes = inventory_sync_interval_minutes()
        startup_delay = inventory_sync_startup_delay_seconds()
        threading.Thread(
            target=_loop,
            args=(minutes * 60.0, startup_delay),
            daemon=True,
            name="inventory-sync-worker",
        ).start()
        _started = True
        log.info(
            "inventory_sync_worker.scheduled",
            interval_minutes=minutes,
            every_hours=minutes / 60.0,
            startup_delay_sec=startup_delay,
        )

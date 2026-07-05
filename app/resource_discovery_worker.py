"""Background worker: subscription-wide ARM resource discovery every 6 hours.

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


def resource_discovery_hours() -> float:
    return float(os.getenv("RESOURCE_DISCOVERY_HOURS", os.getenv("COST_REFRESH_HOURS", "6")))


def resource_discovery_worker_enabled() -> bool:
    raw = os.getenv("RESOURCE_DISCOVERY_WORKER_ENABLED")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _list_subscription_ids(db) -> list[str]:
    from app.models import ResourceSnapshot
    from app.subscription_store import list_subscriptions_db

    subs = sorted({
        (s.get("subscriptionId") or "").strip().lower()
        for s in list_subscriptions_db(db)
        if s.get("subscriptionId")
    })
    if not subs:
        subs = sorted({s[0] for s in db.query(ResourceSnapshot.subscription_id).distinct() if s[0]})
    return subs


def _refresh_once() -> None:
    global _last_run_at, _last_result
    from app.auth import get_token
    from app.database import SessionLocal
    from app.resource_discovery_sync import sync_resource_discovery

    log.info("resource_discovery_worker.start")
    db = SessionLocal()
    results: dict[str, Any] = {"subscriptions": [], "errors": []}
    try:
        token = get_token(db)
        for sub in _list_subscription_ids(db):
            try:
                synced = sync_resource_discovery(sub, db, token)
                results["subscriptions"].append(synced)
            except Exception as exc:
                results["errors"].append({"subscription_id": sub, "error": str(exc)[:500]})
                log.exception("resource_discovery_worker.sub_failed", subscription_id=sub, error=str(exc))
    finally:
        db.close()
    _last_run_at = datetime.now(timezone.utc)
    _last_result = results
    log.info(
        "resource_discovery_worker.complete",
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
            log.warning("resource_discovery_worker.cycle_failed", error=str(exc))
        time.sleep(interval_seconds)


def get_resource_discovery_status() -> dict[str, Any]:
    return {
        "enabled": resource_discovery_worker_enabled(),
        "worker": "resource_discovery",
        "scope": "arm_resources_list",
        "interval_hours": resource_discovery_hours(),
        "last_run_at": _last_run_at.isoformat() if _last_run_at else None,
        "last_result": _last_result,
        "started": _started,
    }


def start() -> None:
    """Start the resource discovery worker thread once (idempotent)."""
    global _started
    if not resource_discovery_worker_enabled():
        log.info("resource_discovery_worker.disabled")
        return
    with _lock:
        if _started:
            return
        hours = resource_discovery_hours()
        startup_delay = float(os.getenv("RESOURCE_DISCOVERY_STARTUP_DELAY_SEC", "180"))
        threading.Thread(
            target=_loop,
            args=(hours * 3600.0, startup_delay),
            daemon=True,
            name="resource-discovery-worker",
        ).start()
        _started = True
        log.info(
            "resource_discovery_worker.scheduled",
            every_hours=hours,
            startup_delay_sec=startup_delay,
        )

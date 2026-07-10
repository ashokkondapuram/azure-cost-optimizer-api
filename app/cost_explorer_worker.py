"""Single background worker for Dashboard, Cost explorer, and billed-resource costs.

Syncs subscription totals, resource-type aggregates, and per-resource MTD costs.
Runs every COST_REFRESH_HOURS (default 1). Manual refresh: POST /costs/sync or
Fetch costs on the Cost explorer tab.
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
_pending_syncs: set[str] = set()
_pending_lock = threading.Lock()
_last_refresh_at: datetime | None = None
_last_refresh_result: dict[str, Any] | None = None


def cost_refresh_hours() -> float:
    return float(os.getenv("COST_REFRESH_HOURS", os.getenv("COST_EXPORT_REFRESH_HOURS", "1")))


def cost_explorer_worker_enabled() -> bool:
    raw = os.getenv("COST_EXPLORER_WORKER_ENABLED")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def cost_startup_delay_seconds() -> float:
    return float(os.getenv("COST_REFRESH_STARTUP_DELAY_SEC", "15"))


def list_cost_sync_subscription_ids(db) -> list[str]:
    """Subscriptions to refresh — cache, synced inventory, and default setting."""
    from app.models import ResourceSnapshot
    from app.subscription_store import _default_subscription_from_settings, list_subscriptions_db

    subs: set[str] = {
        (s.get("subscriptionId") or "").strip().lower()
        for s in list_subscriptions_db(db)
        if s.get("subscriptionId")
    }
    default_sid = _default_subscription_from_settings(db)
    if default_sid:
        subs.add(default_sid)
    if not subs:
        subs = {s[0].lower() for s in db.query(ResourceSnapshot.subscription_id).distinct() if s[0]}
    return sorted(subs)


def is_cost_sync_pending(subscription_id: str) -> bool:
    """True while a background cost sync thread is running for this subscription."""
    sub = (subscription_id or "").strip().lower()
    with _pending_lock:
        return sub in _pending_syncs


def request_cost_sync(subscription_id: str, *, reason: str = "on_demand") -> bool:
    """Enqueue a background Azure → DB cost sync (deduplicated per subscription)."""
    sub = (subscription_id or "").strip().lower()
    if not sub or not cost_explorer_worker_enabled():
        return False

    with _pending_lock:
        if sub in _pending_syncs:
            return False
        _pending_syncs.add(sub)

    def _run() -> None:
        from app.auth import get_token
        from app.cost_explorer_sync import sync_cost_explorer
        from app.database import SessionLocal

        log.info("cost_sync.background_start", subscription_id=sub, reason=reason)
        db = SessionLocal()
        try:
            token = get_token(db)
            synced = sync_cost_explorer(sub, db, token)
            log.info("cost_sync.background_done", subscription_id=sub, reason=reason, synced=synced)
        except Exception as exc:
            log.exception(
                "cost_sync.background_failed",
                subscription_id=sub,
                reason=reason,
                error=str(exc)[:300],
            )
        finally:
            db.close()
            with _pending_lock:
                _pending_syncs.discard(sub)

    threading.Thread(
        target=_run,
        daemon=True,
        name=f"cost-sync-{sub[:8]}",
    ).start()
    return True


def _refresh_once() -> None:
    global _last_refresh_at, _last_refresh_result
    from app.auth import get_token
    from app.cost_explorer_sync import sync_cost_explorer
    from app.database import SessionLocal

    log.info("cost_explorer_worker.start")
    db = SessionLocal()
    results: dict[str, Any] = {"subscriptions": [], "errors": []}
    try:
        try:
            token = get_token(db)
        except Exception as exc:
            log.error("cost_explorer_worker.token_failed", error=str(exc)[:300])
            results["errors"].append({"error": "token_unavailable", "detail": str(exc)[:500]})
            return

        subs = list_cost_sync_subscription_ids(db)
        log.info("cost_explorer_worker.subscriptions", count=len(subs))
        for sub in subs:
            try:
                synced = sync_cost_explorer(sub, db, token)
                results["subscriptions"].append({"subscription_id": sub, "synced": synced})
            except Exception as exc:
                results["errors"].append({"subscription_id": sub, "error": str(exc)[:500]})
                log.exception("cost_explorer_worker.sub_failed", subscription_id=sub, error=str(exc))
    finally:
        db.close()
    _last_refresh_at = datetime.now(timezone.utc)
    _last_refresh_result = results
    log.info(
        "cost_explorer_worker.complete",
        subscriptions=len(results["subscriptions"]),
        errors=len(results["errors"]),
    )


def _loop(interval_seconds: float, startup_delay: float) -> None:
    time.sleep(startup_delay)
    while True:
        try:
            if cost_explorer_worker_enabled():
                _refresh_once()
        except Exception as exc:
            log.warning("cost_explorer_worker.cycle_failed", error=str(exc))
        time.sleep(interval_seconds)


def get_cost_scheduler_status() -> dict[str, Any]:
    return {
        "enabled": cost_explorer_worker_enabled(),
        "worker": "cost_explorer",
        "scope": "subscription_resource_type_and_billed_resources",
        "interval_hours": cost_refresh_hours(),
        "startup_delay_sec": cost_startup_delay_seconds(),
        "pending_syncs": sorted(_pending_syncs),
        "last_run_at": _last_refresh_at.isoformat() if _last_refresh_at else None,
        "last_result": _last_refresh_result,
        "started": _started,
    }


def start() -> None:
    """Start the cost explorer worker thread once (idempotent)."""
    global _started
    if not cost_explorer_worker_enabled():
        log.info("cost_explorer_worker.disabled")
        return
    with _lock:
        if _started:
            return
        hours = cost_refresh_hours()
        startup_delay = cost_startup_delay_seconds()
        threading.Thread(
            target=_loop,
            args=(hours * 3600.0, startup_delay),
            daemon=True,
            name="cost-explorer-worker",
        ).start()
        _started = True
        log.info(
            "cost_explorer_worker.scheduled",
            every_hours=hours,
            startup_delay_sec=startup_delay,
            scope="subscription_resource_type_and_billed_resources",
        )

"""Single background worker for Dashboard, Cost explorer, and billed-resource costs.

Syncs subscription totals, resource-type aggregates, and per-resource MTD costs.
Runs every COST_SYNC_INTERVAL_MINUTES (default 60). Manual refresh: POST /costs/sync or
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
_last_sync_errors: dict[str, str] = {}
_last_sync_error_lock = threading.Lock()


def cost_refresh_hours() -> float:
    from app.sync_intervals import cost_sync_interval_minutes

    return cost_sync_interval_minutes() / 60.0


def cost_sync_interval_minutes() -> float:
    from app.sync_intervals import cost_sync_interval_minutes as _minutes

    return _minutes()


def cost_explorer_worker_enabled() -> bool:
    """Whether the scheduled background refresh loop runs (not on-demand sync)."""
    raw = os.getenv("COST_EXPLORER_WORKER_ENABLED")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def cost_startup_delay_seconds() -> float:
    from app.sync_intervals import cost_sync_startup_delay_seconds

    return cost_sync_startup_delay_seconds()


def list_cost_sync_subscription_ids(db) -> list[str]:
    """Subscriptions to refresh — scoped to default subscription when configured."""
    from app.models import ResourceSnapshot
    from app.subscription_store import list_active_subscription_ids

    subs = list_active_subscription_ids(db)
    if subs:
        return subs
    return sorted(
        s[0].lower()
        for s in db.query(ResourceSnapshot.subscription_id).distinct()
        if s[0]
    )


def is_cost_sync_pending(subscription_id: str) -> bool:
    """True while a background cost sync thread is running for this subscription."""
    sub = (subscription_id or "").strip().lower()
    with _pending_lock:
        return sub in _pending_syncs


def last_cost_sync_error(subscription_id: str) -> str | None:
    """Most recent background cost sync failure for a subscription, if any."""
    sub = (subscription_id or "").strip().lower()
    with _last_sync_error_lock:
        return _last_sync_errors.get(sub)


def _record_cost_sync_error(subscription_id: str, error: str) -> None:
    sub = (subscription_id or "").strip().lower()
    if not sub:
        return
    with _last_sync_error_lock:
        _last_sync_errors[sub] = (error or "")[:500]


def _clear_cost_sync_error(subscription_id: str) -> None:
    sub = (subscription_id or "").strip().lower()
    with _last_sync_error_lock:
        _last_sync_errors.pop(sub, None)


def request_cost_sync(subscription_id: str, *, reason: str = "on_demand") -> bool:
    """Enqueue a background Azure → DB cost sync (deduplicated per subscription).

    On-demand sync (POST /costs/sync, dashboard empty-data enqueue) always runs
    even when COST_EXPLORER_WORKER_ENABLED disables the scheduled refresh loop.
    """
    sub = (subscription_id or "").strip().lower()
    if not sub:
        return False

    with _pending_lock:
        if sub in _pending_syncs:
            return False
        _pending_syncs.add(sub)

    def _run() -> None:
        from app.auth import get_azure_token
        from app.cost_explorer_sync import sync_cost_explorer
        from app.database import SessionLocal

        log.info("cost_sync.background_start", subscription_id=sub, reason=reason)
        db = SessionLocal()
        try:
            token = get_azure_token(db)
            synced = sync_cost_explorer(sub, db, token)
            _clear_cost_sync_error(sub)
            log.info("cost_sync.background_done", subscription_id=sub, reason=reason, synced=synced)
        except Exception as exc:
            err = str(exc)[:500]
            _record_cost_sync_error(sub, err)
            log.exception(
                "cost_sync.background_failed",
                subscription_id=sub,
                reason=reason,
                error=err[:300],
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
            token = get_azure_token(db)
        except Exception as exc:
            log.error("cost_explorer_worker.token_failed", error=str(exc)[:300])
            results["errors"].append({"error": "token_unavailable", "detail": str(exc)[:500]})
            return

        subs = list_cost_sync_subscription_ids(db)
        log.info("cost_explorer_worker.subscriptions", count=len(subs))
        for sub in subs:
            if is_cost_sync_pending(sub):
                log.info("cost_explorer_worker.skipped", subscription_id=sub, reason="pending")
                continue
            try:
                synced = sync_cost_explorer(sub, db, token)
                _clear_cost_sync_error(sub)
                results["subscriptions"].append({"subscription_id": sub, "synced": synced})
            except Exception as exc:
                err = str(exc)[:500]
                _record_cost_sync_error(sub, err)
                results["errors"].append({"subscription_id": sub, "error": err})
                log.exception("cost_explorer_worker.sub_failed", subscription_id=sub, error=err)
    finally:
        db.close()
    _last_refresh_at = datetime.now(timezone.utc)
    _last_refresh_result = results
    log.info(
        "cost_explorer_worker.complete",
        subscriptions=len(results["subscriptions"]),
        errors=len(results["errors"]),
    )
    _sync_retail_prices_after_cost_refresh()


def _sync_retail_prices_after_cost_refresh() -> None:
    """Refresh global retail SKU price cache after scheduled cost sync."""
    if os.getenv("RETAIL_PRICE_SYNC_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        return
    from app.database import SessionLocal
    from app.retail_price_sync import sync_retail_sku_prices

    db = SessionLocal()
    try:
        stats = sync_retail_sku_prices(db, fetch_retail_api=True, seed_catalog=True)
        log.info("cost_explorer_worker.retail_prices_synced", **stats)
    except Exception as exc:
        log.warning("cost_explorer_worker.retail_prices_failed", error=str(exc)[:300])
    finally:
        db.close()


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
        "interval_minutes": cost_sync_interval_minutes(),
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
        minutes = cost_sync_interval_minutes()
        startup_delay = cost_startup_delay_seconds()
        threading.Thread(
            target=_loop,
            args=(minutes * 60.0, startup_delay),
            daemon=True,
            name="cost-explorer-worker",
        ).start()
        _started = True
        log.info(
            "cost_explorer_worker.scheduled",
            interval_minutes=minutes,
            every_hours=minutes / 60.0,
            startup_delay_sec=startup_delay,
            scope="subscription_resource_type_and_billed_resources",
        )

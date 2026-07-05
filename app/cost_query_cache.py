"""Application-level TTL cache and in-flight dedup for Cost Management live queries."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import structlog

log = structlog.get_logger()

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}

_metrics: dict[str, int] = {
    "hits": 0,
    "misses": 0,
    "api_calls": 0,
    "dedup_waits": 0,
    "errors": 0,
    "errors_429": 0,
}


@dataclass
class _InflightEntry:
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: BaseException | None = None
    done: bool = False


_inflight: dict[str, _InflightEntry] = {}


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


_HISTORICAL_TTL = _int_env("COST_CACHE_HISTORICAL_TTL_SEC", 86400)
_MTD_TTL = _int_env("COST_CACHE_MTD_TTL_SEC", 900)
_FORECAST_TTL = _int_env("COST_CACHE_FORECAST_TTL_SEC", 1800)
_DAILY_MTD_TTL = _int_env("COST_CACHE_DAILY_MTD_TTL_SEC", 3600)


def ttl_for_query(query_type: str, timeframe: str) -> int:
    tf = (timeframe or "").strip()
    if query_type == "forecast":
        return _FORECAST_TTL
    if query_type == "daily":
        if tf in ("MonthToDate", "BillingMonthToDate"):
            return _DAILY_MTD_TTL
        return _HISTORICAL_TTL
    if query_type in ("summary", "by_service"):
        if tf in ("TheLastMonth", "LastBillingMonth"):
            return _HISTORICAL_TTL
        if tf in ("MonthToDate", "BillingMonthToDate", "ThisYear"):
            return _MTD_TTL
        return _MTD_TTL
    return _MTD_TTL


def _cache_key(
    subscription_id: str,
    query_type: str,
    timeframe: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
) -> str:
    sub = subscription_id.strip().lower()
    fd = (from_date or "").strip()
    td = (to_date or "").strip()
    return f"cost:{sub}:{query_type}:{timeframe}:{fd}:{td}"


def cost_cache_metrics() -> dict[str, Any]:
    with _cache_lock:
        hits = _metrics["hits"]
        misses = _metrics["misses"]
        total = hits + misses
        hit_rate = round((hits / total) * 100, 1) if total else 0.0
        return {
            **_metrics,
            "entries": len(_cache),
            "inflight": len(_inflight),
            "hit_rate_pct": hit_rate,
        }


def record_cost_api_call() -> None:
    with _cache_lock:
        _metrics["api_calls"] += 1


def record_cost_429() -> None:
    with _cache_lock:
        _metrics["errors_429"] += 1


def invalidate_subscription_cost_cache(subscription_id: str) -> None:
    sub = (subscription_id or "").strip().lower()
    if not sub:
        return
    prefix = f"cost:{sub}:"
    with _cache_lock:
        for key in list(_cache.keys()):
            if key.startswith(prefix):
                _cache.pop(key, None)


def clear_cost_query_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if not entry:
        return None
    expires_at, value = entry
    if expires_at <= time.monotonic():
        _cache.pop(key, None)
        return None
    return value


def cached_cost_live_query(
    subscription_id: str,
    query_type: str,
    timeframe: str,
    loader: Callable[[], Any],
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    skip_cache: bool = False,
) -> Any:
    key = _cache_key(subscription_id, query_type, timeframe, from_date=from_date, to_date=to_date)
    ttl = ttl_for_query(query_type, timeframe)

    if not skip_cache and ttl > 0:
        with _cache_lock:
            cached = _cache_get(key)
            if cached is not None:
                _metrics["hits"] += 1
                log.debug("cost_cache.hit", query_type=query_type, timeframe=timeframe)
                return cached

    follower = False
    with _cache_lock:
        if not skip_cache and ttl > 0:
            cached = _cache_get(key)
            if cached is not None:
                _metrics["hits"] += 1
                return cached
        entry = _inflight.get(key)
        if entry is not None:
            follower = True
            _metrics["dedup_waits"] += 1
        else:
            _inflight[key] = _InflightEntry()
            _metrics["misses"] += 1

    if follower:
        entry = _inflight[key]
        log.debug("cost_cache.dedup_wait", query_type=query_type, timeframe=timeframe)
        entry.event.wait(timeout=120)
        if entry.error is not None:
            raise entry.error
        return entry.result

    entry = _inflight[key]
    try:
        record_cost_api_call()
        result = loader()
        if not skip_cache and ttl > 0 and result is not None:
            with _cache_lock:
                _cache[key] = (time.monotonic() + ttl, result)
        entry.result = result
        return result
    except Exception as exc:
        with _cache_lock:
            _metrics["errors"] += 1
        entry.error = exc
        raise
    finally:
        entry.done = True
        entry.event.set()
        with _cache_lock:
            _inflight.pop(key, None)

"""In-process TTL caches backed by cachetools (1-D)."""

from __future__ import annotations

import threading
from typing import Any, Callable

from cachetools import TTLCache

_cost_map_cache: TTLCache = TTLCache(maxsize=100, ttl=300)
_counts_cache: TTLCache = TTLCache(maxsize=100, ttl=300)
_findings_cache: TTLCache = TTLCache(maxsize=100, ttl=120)
_dashboard_cache: TTLCache = TTLCache(maxsize=100, ttl=180)
_cache_lock = threading.Lock()
_metrics: dict[str, int] = {
    "hits": 0,
    "misses": 0,
    "evictions": 0,
    "invalidations": 0,
}


def invalidate_subscription(subscription_id: str) -> None:
    """Purge cached reads for one subscription after sync or analysis."""
    sub = (subscription_id or "").strip().lower()
    if not sub:
        return
    from app.cost_query_cache import invalidate_subscription_cost_cache

    invalidate_subscription_cost_cache(sub)
    prefixes = (
        f"cost_map:{sub}",
        f"cost_overlays:{sub}",
        f"billed_total:{sub}",
        f"billing_currency:{sub}",
        f"inv_total:{sub}",
        f"counts:{sub}",
        sub,
    )
    removed = 0
    with _cache_lock:
        for cache in (_cost_map_cache, _counts_cache, _findings_cache, _dashboard_cache):
            for key in list(cache.keys()):
                if key == sub or any(str(key).startswith(p) for p in prefixes):
                    cache.pop(key, None)
                    removed += 1
        _metrics["invalidations"] += removed


def clear_subscription_read_caches() -> None:
    """Invalidate all subscription-scoped caches."""
    with _cache_lock:
        for cache in (_cost_map_cache, _counts_cache, _findings_cache, _dashboard_cache):
            _metrics["invalidations"] += len(cache)
            cache.clear()


def perf_cache_metrics() -> dict[str, Any]:
    """Hit/miss/eviction counters for subscription read caches."""
    with _cache_lock:
        hits = _metrics["hits"]
        misses = _metrics["misses"]
        total = hits + misses
        hit_rate = round((hits / total) * 100, 1) if total else 0.0
        entries = (
            len(_cost_map_cache)
            + len(_counts_cache)
            + len(_findings_cache)
            + len(_dashboard_cache)
        )
        return {
            **_metrics,
            "entries": entries,
            "hit_rate_pct": hit_rate,
            "caches": {
                "cost_map": len(_cost_map_cache),
                "counts": len(_counts_cache),
                "findings": len(_findings_cache),
                "dashboard": len(_dashboard_cache),
            },
        }


def _cached(cache: TTLCache, key: str, loader: Callable[[], Any]) -> Any:
    with _cache_lock:
        if key in cache:
            _metrics["hits"] += 1
            return cache[key]
        _metrics["misses"] += 1
        at_capacity = cache.maxsize > 0 and len(cache) >= cache.maxsize
    value = loader()
    with _cache_lock:
        if at_capacity:
            _metrics["evictions"] += 1
        cache[key] = value
    return value


def cached_cost_map(key: str, loader: Callable[[], dict]) -> dict:
    return _cached(_cost_map_cache, key, loader)


def cached_resource_counts(key: str, loader: Callable[[], dict]) -> dict:
    return _cached(_counts_cache, key, loader)


def cached_findings_summary(subscription_id: str, loader: Callable[[], Any]) -> Any:
    return _cached(_findings_cache, subscription_id.lower(), loader)


def cached_dashboard_overview(subscription_id: str, loader: Callable[[], Any]) -> Any:
    return _cached(_dashboard_cache, subscription_id.lower(), loader)

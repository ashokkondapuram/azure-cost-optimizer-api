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


def invalidate_subscription(subscription_id: str) -> None:
    """Purge cached reads for one subscription after sync or analysis."""
    sub = (subscription_id or "").strip().lower()
    if not sub:
        return
    from app.cost_query_cache import invalidate_subscription_cost_cache

    invalidate_subscription_cost_cache(sub)
    prefixes = (f"cost_map:{sub}", f"counts:{sub}", sub)
    with _cache_lock:
        for cache in (_cost_map_cache, _counts_cache, _findings_cache, _dashboard_cache):
            for key in list(cache.keys()):
                if key == sub or any(str(key).startswith(p) for p in prefixes):
                    cache.pop(key, None)


def clear_subscription_read_caches() -> None:
    """Invalidate all subscription-scoped caches."""
    with _cache_lock:
        _cost_map_cache.clear()
        _counts_cache.clear()
        _findings_cache.clear()
        _dashboard_cache.clear()


def _cached(cache: TTLCache, key: str, loader: Callable[[], Any]) -> Any:
    with _cache_lock:
        if key in cache:
            return cache[key]
    value = loader()
    with _cache_lock:
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

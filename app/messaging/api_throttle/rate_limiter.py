"""Per-API-kind token bucket rate limiters with adaptive backoff."""

from __future__ import annotations

import threading
import time
from typing import Callable

import structlog

from app.messaging.api_throttle import metrics as throttle_metrics
from app.messaging.api_throttle.config import (
    api_cost_burst,
    api_cost_rate_per_sec,
    api_inventory_burst,
    api_inventory_rate_per_sec,
    api_metrics_burst,
    api_metrics_rate_per_sec,
)

log = structlog.get_logger(__name__)


class _TokenBucket:
    """Thread-safe token bucket; smooths request rate to <= rate/second."""

    def __init__(self, *, rate_per_sec: float, burst: int):
        self._rate = max(0.01, float(rate_per_sec))
        self._capacity = max(1.0, float(burst))
        self._tokens = self._capacity
        self._ts = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    self._capacity,
                    self._tokens + (now - self._ts) * self._rate,
                )
                self._ts = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
            throttle_metrics.get_metrics().record_throttle_wait(wait)
            time.sleep(wait)


class _AdaptiveSlotLimiter:
    """Inter-call delay multiplier after 429 responses (azure_cost pattern)."""

    def __init__(
        self,
        *,
        bucket: _TokenBucket,
        base_delay_sec: float = 0.0,
    ):
        self._bucket = bucket
        self._base_delay_sec = base_delay_sec
        self._adaptive_multiplier = 1.0
        self._last_call_at = 0.0
        self._lock = threading.RLock()

    @property
    def adaptive_multiplier(self) -> float:
        with self._lock:
            return self._adaptive_multiplier

    def record_success(self) -> None:
        with self._lock:
            self._adaptive_multiplier = max(1.0, self._adaptive_multiplier * 0.9)

    def record_429(self) -> None:
        with self._lock:
            self._adaptive_multiplier = min(6.0, self._adaptive_multiplier * 1.5)

    def acquire(self, *, label: str = "api_call") -> None:
        with self._lock:
            delay = self._base_delay_sec * self._adaptive_multiplier
            elapsed = time.monotonic() - self._last_call_at
            if delay > 0 and elapsed < delay:
                wait = delay - elapsed
                log.info(
                    "api_throttle.throttle_wait",
                    seconds=round(wait, 2),
                    phase=label,
                    adaptive_multiplier=round(self._adaptive_multiplier, 2),
                )
                throttle_metrics.get_metrics().record_throttle_wait(wait)
                time.sleep(wait)
            self._last_call_at = time.monotonic()
        self._bucket.acquire()


_KIND_CONFIG: dict[str, tuple[Callable[[], float], Callable[[], int], float]] = {
    "cost": (api_cost_rate_per_sec, api_cost_burst, 10.0),
    "metrics": (api_metrics_rate_per_sec, api_metrics_burst, 0.25),
    "inventory": (api_inventory_rate_per_sec, api_inventory_burst, 0.25),
}

_limiters: dict[str, _AdaptiveSlotLimiter] = {}
_limiter_lock = threading.Lock()


def _limiter_for_kind(api_kind: str) -> _AdaptiveSlotLimiter:
    with _limiter_lock:
        limiter = _limiters.get(api_kind)
        if limiter is None:
            rate_fn, burst_fn, delay = _KIND_CONFIG.get(api_kind, (lambda: 1.0, lambda: 1, 0.0))
            bucket = _TokenBucket(rate_per_sec=rate_fn(), burst=burst_fn())
            limiter = _AdaptiveSlotLimiter(bucket=bucket, base_delay_sec=delay)
            _limiters[api_kind] = limiter
        return limiter


def acquire_api_slot(api_kind: str, *, label: str = "api_call") -> None:
    """Block until a rate-limited slot is available for *api_kind*."""
    _limiter_for_kind(api_kind).acquire(label=label)


def record_api_success(api_kind: str) -> None:
    _limiter_for_kind(api_kind).record_success()


def record_api_429(api_kind: str) -> None:
    _limiter_for_kind(api_kind).record_429()


def reset_limiters() -> None:
    global _limiters
    with _limiter_lock:
        _limiters = {}


# Back-compat aliases for ApiDomain-based helpers/tests.
from app.messaging.api_throttle.envelope import ApiDomain  # noqa: E402

_DOMAIN_TO_KIND = {
    ApiDomain.COST_MANAGEMENT: "cost",
    ApiDomain.MONITOR: "metrics",
    ApiDomain.RESOURCE_GRAPH: "inventory",
}


class DomainRateLimiter:
    """Thin wrapper over kind-based limiters for domain-centric tests."""

    def __init__(
        self,
        domain: ApiDomain,
        *,
        rate_fn: Callable[[], float] | None = None,
        burst_fn: Callable[[], float] | None = None,
        delay_fn: Callable[[], float] | None = None,
        **_kwargs,
    ):
        self._kind = _DOMAIN_TO_KIND[domain]
        self._domain = domain
        if rate_fn or burst_fn or delay_fn:
            bucket = _TokenBucket(
                rate_per_sec=rate_fn() if rate_fn else 1.0,
                burst=int(burst_fn() if burst_fn else 1),
            )
            self._limiter = _AdaptiveSlotLimiter(
                bucket=bucket,
                base_delay_sec=delay_fn() if delay_fn else 0.0,
            )
        else:
            self._limiter = _limiter_for_kind(self._kind)

    @property
    def adaptive_multiplier(self) -> float:
        return self._limiter.adaptive_multiplier

    def record_success(self) -> None:
        self._limiter.record_success()

    def record_429(self) -> None:
        self._limiter.record_429()

    def acquire(self, *, label: str = "api_call") -> None:
        self._limiter.acquire(label=label)


def get_rate_limiter(domain: ApiDomain) -> DomainRateLimiter:
    return DomainRateLimiter(domain)


def reset_rate_limiters() -> None:
    reset_limiters()

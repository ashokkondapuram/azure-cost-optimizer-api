"""Retry helpers for Azure Monitor metrics fetches."""

from __future__ import annotations

import os
import random

# Transient HTTP statuses worth retrying at the monitor-fetch layer.
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
_NON_RETRYABLE_STATUSES = frozenset({403, 404})


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def monitor_max_retries() -> int:
    """Max *additional* attempts after the first (default 2 → 3 total tries)."""
    return max(0, _int_env("ANALYSIS_MONITOR_METRICS_MAX_RETRIES", 2))


def sync_monitor_max_retries() -> int:
    """Retries during inventory/sync pipeline metrics (default 0 = fail fast)."""
    for name in ("SYNC_MONITOR_METRICS_MAX_RETRIES", "METRICS_SYNC_MAX_RETRIES"):
        raw = os.getenv(name)
        if raw is not None and str(raw).strip():
            return max(0, _int_env(name, 0))
    return 0


def monitor_retry_backoff_base_sec() -> float:
    return max(0.1, _float_env("ANALYSIS_MONITOR_METRICS_RETRY_BACKOFF_SEC", 2.0))


def monitor_retry_backoff_max_sec() -> float:
    return max(monitor_retry_backoff_base_sec(), _float_env("ANALYSIS_MONITOR_METRICS_RETRY_BACKOFF_MAX_SEC", 30.0))


def retry_backoff_seconds(attempt: int) -> float:
    """Exponential backoff with jitter; attempt is 0-based (first retry delay)."""
    base = min(
        monitor_retry_backoff_max_sec(),
        monitor_retry_backoff_base_sec() * (2 ** attempt),
    )
    jitter = random.uniform(0.0, base * 0.5)
    return base + jitter


def is_retryable_http_status(status: int) -> bool:
    if status in _NON_RETRYABLE_STATUSES:
        return False
    return status in _RETRYABLE_STATUSES


def is_retryable_fetch_error(err: str | None) -> bool:
    """Whether a monitor fetch error string should be retried."""
    if not err or err == "empty":
        return False
    if err == "timed_out":
        return True
    status_part = err.split(":", 1)[0]
    try:
        status = int(status_part)
    except ValueError:
        lower = err.lower()
        return any(token in lower for token in ("timeout", "timed out", "connection"))
    return is_retryable_http_status(status)

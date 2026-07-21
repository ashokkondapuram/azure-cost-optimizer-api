"""Structured monitoring hooks for API throttle workers."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import structlog

log = structlog.get_logger(__name__)


@dataclass
class ApiThrottleMetrics:
    """In-process counters for throttle observability (reset on process restart)."""

    throttle_waits: int = 0
    throttle_wait_ms_total: float = 0.0
    http_429_count: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    dlq_messages: int = 0
    consumer_lag_hint: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_throttle_wait(self, wait_sec: float) -> None:
        with self._lock:
            self.throttle_waits += 1
            self.throttle_wait_ms_total += wait_sec * 1000.0
        log.info(
            "api_throttle.wait",
            wait_ms=round(wait_sec * 1000.0, 1),
            total_waits=self.throttle_waits,
        )

    def record_429(self, *, api_kind: str, phase: str) -> None:
        with self._lock:
            self.http_429_count += 1
        log.warning(
            "api_throttle.http_429",
            api_kind=api_kind,
            phase=phase,
            total_429=self.http_429_count,
        )

    def record_job_completed(self, *, api_kind: str, phase: str, duration_sec: float) -> None:
        with self._lock:
            self.jobs_completed += 1
        log.info(
            "api_throttle.job_completed",
            api_kind=api_kind,
            phase=phase,
            duration_ms=round(duration_sec * 1000.0, 1),
            total_completed=self.jobs_completed,
        )

    def record_job_failed(self, *, api_kind: str, phase: str, error: str) -> None:
        with self._lock:
            self.jobs_failed += 1
        log.error(
            "api_throttle.job_failed",
            api_kind=api_kind,
            phase=phase,
            error=error[:300],
            total_failed=self.jobs_failed,
        )

    def record_dlq(self, *, api_kind: str, phase: str, pipeline_id: str) -> None:
        with self._lock:
            self.dlq_messages += 1
        log.error(
            "api_throttle.dlq",
            api_kind=api_kind,
            phase=phase,
            pipeline_id=pipeline_id,
            total_dlq=self.dlq_messages,
        )

    def record_lag_hint(self, *, topic: str, lag: int) -> None:
        with self._lock:
            self.consumer_lag_hint = max(self.consumer_lag_hint, lag)
        log.info("api_throttle.consumer_lag", topic=topic, lag=lag)

    def snapshot(self) -> dict[str, float | int]:
        with self._lock:
            return {
                "throttle_waits": self.throttle_waits,
                "throttle_wait_ms_total": round(self.throttle_wait_ms_total, 1),
                "http_429_count": self.http_429_count,
                "jobs_completed": self.jobs_completed,
                "jobs_failed": self.jobs_failed,
                "dlq_messages": self.dlq_messages,
                "consumer_lag_hint": self.consumer_lag_hint,
            }


_metrics = ApiThrottleMetrics()


def get_metrics() -> ApiThrottleMetrics:
    return _metrics


def reset_metrics() -> None:
    global _metrics
    _metrics = ApiThrottleMetrics()


def timed_phase(api_kind: str, phase: str):
    """Context manager that records job duration on success."""

    class _Timer:
        def __enter__(self):
            self._start = time.monotonic()
            return self

        def __exit__(self, exc_type, exc, tb):
            duration = time.monotonic() - self._start
            if exc_type is None:
                get_metrics().record_job_completed(
                    api_kind=api_kind,
                    phase=phase,
                    duration_sec=duration,
                )
            else:
                get_metrics().record_job_failed(
                    api_kind=api_kind,
                    phase=phase,
                    error=str(exc) if exc else "unknown",
                )
            return False

    return _Timer()

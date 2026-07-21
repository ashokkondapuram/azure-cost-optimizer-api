"""In-memory batch state for aggregating api.*.completed messages."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_BATCH_TTL_SEC = 3600.0


@dataclass
class ApiBatchState:
    batch_id: str
    pipeline_id: str
    subscription_id: str
    api_kind: str
    total_phases: int
    run_params: dict[str, Any]
    source_service: str
    meta: dict[str, Any] = field(default_factory=dict)
    results: dict[str, Any] = field(default_factory=dict)
    completed_indexes: set[int] = field(default_factory=set)
    failed: bool = False
    error: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    _done: threading.Event = field(default_factory=threading.Event, repr=False)


class ApiBatchRegistry:
    def __init__(self) -> None:
        self._batches: dict[str, ApiBatchState] = {}
        self._lock = threading.Lock()

    def register(self, state: ApiBatchState) -> None:
        with self._lock:
            self._purge_expired_locked()
            self._batches[state.batch_id] = state

    def get(self, batch_id: str) -> ApiBatchState | None:
        with self._lock:
            return self._batches.get(batch_id)

    def record_result(
        self,
        *,
        batch_id: str,
        phase: str,
        phase_index: int,
        result: Any,
        state: ApiBatchState | None = None,
    ) -> ApiBatchState | None:
        with self._lock:
            existing = self._batches.get(batch_id)
            if existing is None and state is not None:
                self._batches[batch_id] = state
                existing = state
            if existing is None or existing.failed:
                return existing
            if phase_index in existing.completed_indexes:
                log.info(
                    "api_throttle.duplicate_phase_result",
                    batch_id=batch_id,
                    phase=phase,
                    phase_index=phase_index,
                )
                return existing
            existing.completed_indexes.add(phase_index)
            existing.results[phase] = result
            if self.is_complete(existing):
                existing._done.set()
            return existing

    def mark_failed(self, batch_id: str, error: str) -> None:
        with self._lock:
            state = self._batches.get(batch_id)
            if state is not None:
                state.failed = True
                state.error = error
                state._done.set()

    def is_complete(self, state: ApiBatchState) -> bool:
        return len(state.completed_indexes) >= state.total_phases and not state.failed

    def wait_for_batch(
        self,
        batch_id: str,
        *,
        timeout_sec: float,
    ) -> ApiBatchState:
        state = self.get(batch_id)
        if state is None:
            raise TimeoutError(f"Unknown API batch: {batch_id}")
        if not state._done.wait(timeout_sec):
            raise TimeoutError(f"API batch {batch_id} timed out after {timeout_sec}s")
        current = self.get(batch_id)
        if current is None:
            raise RuntimeError(f"API batch {batch_id} disappeared after completion")
        if current.failed:
            raise RuntimeError(current.error or f"API batch {batch_id} failed")
        return current

    def pop(self, batch_id: str) -> ApiBatchState | None:
        with self._lock:
            return self._batches.pop(batch_id, None)

    def reset(self) -> None:
        with self._lock:
            self._batches.clear()

    def inflight_count(self) -> int:
        with self._lock:
            return len(self._batches)

    def _purge_expired_locked(self) -> None:
        now = time.monotonic()
        expired = [
            batch_id
            for batch_id, state in self._batches.items()
            if now - state.created_at > _BATCH_TTL_SEC
        ]
        for batch_id in expired:
            self._batches.pop(batch_id, None)


_registry = ApiBatchRegistry()


def get_batch_registry() -> ApiBatchRegistry:
    return _registry


def reset_batch_registry() -> None:
    _registry.reset()

"""In-process ack tracking between data producers and persistence consumers."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_events: dict[str, threading.Event] = {}
_processed: set[str] = set()


def persist_ack_key(pipeline_id: str, stage: str) -> str:
    return f"{pipeline_id}:{stage}:data_persisted"


def wait_for_persist(pipeline_id: str, stage: str, *, timeout: float = 600.0) -> bool:
    key = persist_ack_key(pipeline_id, stage)
    with _lock:
        event = _events.setdefault(key, threading.Event())
    return event.wait(timeout)


def signal_persisted(pipeline_id: str, stage: str) -> None:
    key = persist_ack_key(pipeline_id, stage)
    with _lock:
        _processed.add(key)
        event = _events.setdefault(key, threading.Event())
    event.set()


def already_persisted(pipeline_id: str, stage: str) -> bool:
    key = persist_ack_key(pipeline_id, stage)
    with _lock:
        return key in _processed


def reset_ack_state() -> None:
    """Test helper — clear in-memory ack state."""
    with _lock:
        _events.clear()
        _processed.clear()

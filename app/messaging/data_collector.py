"""Collect sync payloads during Azure fetch instead of writing directly to PostgreSQL."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from app.messaging.json_serialization import sanitize_for_json

_data_collector: contextvars.ContextVar[SyncDataCollector | None] = contextvars.ContextVar(
    "sync_data_collector",
    default=None,
)


@dataclass
class SyncDataCollector:
    """In-memory buffer for stage data routed through Kafka before DB persist."""

    stage: str
    sections: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)

    def add_section(self, name: str, payload: Any) -> None:
        self.sections[name] = payload

    def to_payload(self) -> dict[str, Any]:
        return sanitize_for_json(
            {
                "stage": self.stage,
                "sections": self.sections,
                "summary": self.summary,
            }
        )


def data_collection_active() -> bool:
    return _data_collector.get() is not None


def get_collector() -> SyncDataCollector | None:
    return _data_collector.get()


@contextmanager
def collect_sync_data(stage: str) -> Iterator[SyncDataCollector]:
    collector = SyncDataCollector(stage=stage)
    token = _data_collector.set(collector)
    try:
        yield collector
    finally:
        _data_collector.reset(token)

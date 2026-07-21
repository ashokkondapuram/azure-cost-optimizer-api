"""Standard job message schema for Kafka sync pipeline."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.messaging.json_serialization import json_default, sanitize_for_json


class JobType(str, Enum):
    SYNC_INVENTORY = "sync.inventory"
    SYNC_COST = "sync.cost"
    SYNC_METRICS = "sync.metrics"
    SYNC_ANALYSIS = "sync.analysis"
    PIPELINE_STATUS = "pipeline.status"
    PIPELINE_COMPLETED = "pipeline.completed"
    DATA_INVENTORY_SYNCED = "data.inventory.synced"
    DATA_COST_SYNCED = "data.cost.synced"
    DATA_METRICS_SYNCED = "data.metrics.synced"
    DATA_ANALYSIS_COMPLETED = "data.analysis.completed"
    API_COST_REQUESTED = "api.cost"
    API_COST_COMPLETED = "api.cost.completed"
    API_METRICS_REQUESTED = "api.metrics"
    API_METRICS_COMPLETED = "api.metrics.completed"
    API_INVENTORY_REQUESTED = "api.inventory"
    API_INVENTORY_COMPLETED = "api.inventory.completed"
    API_DEAD_LETTER = "api.dead-letter"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class JobEnvelope:
    """Canonical async job payload exchanged between platform microservices."""

    job_id: str
    job_type: JobType
    subscription_id: str
    pipeline_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)
    source_service: str = "platform-gateway"
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        self.subscription_id = (self.subscription_id or "").strip().lower()
        if isinstance(self.job_type, str):
            self.job_type = JobType(self.job_type)
        if not self.idempotency_key:
            self.idempotency_key = f"{self.pipeline_id}:{self.job_type.value}"

    @classmethod
    def create(
        cls,
        *,
        job_type: JobType,
        subscription_id: str,
        pipeline_id: str,
        payload: dict[str, Any] | None = None,
        source_service: str = "platform-gateway",
        job_id: str | None = None,
    ) -> JobEnvelope:
        return cls(
            job_id=job_id or str(uuid.uuid4()),
            job_type=job_type,
            subscription_id=subscription_id,
            pipeline_id=pipeline_id,
            payload=dict(payload or {}),
            source_service=source_service,
        )

    def to_json(self) -> str:
        data = asdict(self)
        data["job_type"] = self.job_type.value
        data = sanitize_for_json(data)
        return json.dumps(
            data,
            separators=(",", ":"),
            sort_keys=True,
            default=json_default,
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> JobEnvelope:
        data = json.loads(raw)
        return cls(
            job_id=str(data["job_id"]),
            job_type=JobType(data["job_type"]),
            subscription_id=str(data["subscription_id"]),
            pipeline_id=str(data["pipeline_id"]),
            payload=dict(data.get("payload") or {}),
            created_at=str(data.get("created_at") or _utc_now_iso()),
            source_service=str(data.get("source_service") or "unknown"),
            idempotency_key=data.get("idempotency_key"),
        )

    def partition_key(self) -> bytes:
        """Route all jobs for a subscription to the same partition (ordering)."""
        return self.subscription_id.encode("utf-8")

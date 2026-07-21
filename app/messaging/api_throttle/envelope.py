"""Job envelope for Kafka-buffered Azure API calls."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.messaging.json_serialization import json_default, sanitize_for_json


class ApiDomain(str, Enum):
    COST_MANAGEMENT = "cost_management"
    MONITOR = "monitor"
    RESOURCE_GRAPH = "resource_graph"


class ApiJobStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    DEAD_LETTER = "dead_letter"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ApiJobEnvelope:
    """Canonical payload for enqueued Azure API work."""

    job_id: str
    domain: ApiDomain
    operation: str
    subscription_id: str
    pipeline_id: str
    phase: str
    params: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    idempotency_key: str | None = None
    created_at: str = field(default_factory=_utc_now_iso)
    status: ApiJobStatus = ApiJobStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    retry_after_sec: float | None = None

    def __post_init__(self) -> None:
        self.subscription_id = (self.subscription_id or "").strip().lower()
        if isinstance(self.domain, str):
            self.domain = ApiDomain(self.domain)
        if isinstance(self.status, str):
            self.status = ApiJobStatus(self.status)
        if not self.idempotency_key:
            self.idempotency_key = f"{self.pipeline_id}:{self.domain.value}:{self.operation}"

    @classmethod
    def create(
        cls,
        *,
        domain: ApiDomain,
        operation: str,
        subscription_id: str,
        pipeline_id: str,
        phase: str,
        params: dict[str, Any] | None = None,
        job_id: str | None = None,
        retry_count: int = 0,
        idempotency_key: str | None = None,
    ) -> ApiJobEnvelope:
        return cls(
            job_id=job_id or str(uuid.uuid4()),
            domain=domain,
            operation=operation,
            subscription_id=subscription_id,
            pipeline_id=pipeline_id,
            phase=phase,
            params=dict(params or {}),
            retry_count=retry_count,
            idempotency_key=idempotency_key,
        )

    def to_json(self) -> str:
        data = asdict(self)
        data["domain"] = self.domain.value
        data["status"] = self.status.value
        data = sanitize_for_json(data)
        return json.dumps(data, separators=(",", ":"), sort_keys=True, default=json_default)

    @classmethod
    def from_json(cls, raw: str | bytes) -> ApiJobEnvelope:
        data = json.loads(raw)
        return cls(
            job_id=str(data["job_id"]),
            domain=ApiDomain(data["domain"]),
            operation=str(data["operation"]),
            subscription_id=str(data["subscription_id"]),
            pipeline_id=str(data["pipeline_id"]),
            phase=str(data.get("phase") or ""),
            params=dict(data.get("params") or {}),
            retry_count=int(data.get("retry_count") or 0),
            idempotency_key=data.get("idempotency_key"),
            created_at=str(data.get("created_at") or _utc_now_iso()),
            status=ApiJobStatus(data.get("status") or ApiJobStatus.PENDING.value),
            result=dict(data["result"]) if data.get("result") else None,
            error=data.get("error"),
            retry_after_sec=data.get("retry_after_sec"),
        )

    def partition_key(self) -> bytes:
        return self.subscription_id.encode("utf-8")

    def with_completion(
        self,
        *,
        status: ApiJobStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ApiJobEnvelope:
        return ApiJobEnvelope(
            job_id=self.job_id,
            domain=self.domain,
            operation=self.operation,
            subscription_id=self.subscription_id,
            pipeline_id=self.pipeline_id,
            phase=self.phase,
            params=dict(self.params),
            retry_count=self.retry_count,
            idempotency_key=self.idempotency_key,
            created_at=self.created_at,
            status=status,
            result=dict(result) if result else None,
            error=error,
        )

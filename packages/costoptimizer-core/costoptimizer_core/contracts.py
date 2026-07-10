"""Pydantic contracts for standard microservice APIs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service_id: str


class ServiceMetaResponse(BaseModel):
    service_id: str
    canonical_type: str
    api_slug: str
    component: str | None = None
    arm_type: str | None = None
    display_name: str | None = None
    migrated: bool = False


class SyncRequest(BaseModel):
    subscription_id: str
    include_costs: bool = True


class SyncResponse(BaseModel):
    subscription_id: str
    canonical_type: str
    resource_counts: dict[str, Any] = Field(default_factory=dict)
    cost_counts: dict[str, Any] = Field(default_factory=dict)


class AnalyzeRequest(BaseModel):
    subscription_id: str
    profile: str = "default"
    engine_version: str = "extended"
    refresh_azure_costs: bool = True


class AnalyzeResponse(BaseModel):
    subscription_id: str
    canonical_type: str
    component: str | None = None
    findings_count: int = 0
    result: dict[str, Any] = Field(default_factory=dict)


class MetricsCollectRequest(BaseModel):
    subscription_id: str
    resource_ids: list[str] = Field(default_factory=list)


class MetricsCollectResponse(BaseModel):
    subscription_id: str
    collected: int = 0
    stats: dict[str, Any] = Field(default_factory=dict)

"""Optimization Engine router — /optimize and /findings prefixes."""
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.analysis import run_db_analysis
from app.analysis_persist import persist_optimization_run
from app.batch_analyzer import (
    create_analysis_job,
    execute_batch_job,
    queue_post_sync_analysis,
    queue_rule_config_reanalysis,
    serialize_job,
)
from app.database import get_db
from app.optimizer.engine import OptimizationEngine
from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.engine_config import get_effective_config, upsert_rule_config, delete_rule_config
from app.optimizer.rule_catalog import (
    canonical_resource_rule_catalog,
    list_all_rules,
    list_components,
    list_rules_for_canonical_type,
    resolve_rule_id,
)
from app.optimizer.rule_registry import ALL_KNOWN_RULE_IDS, is_known_rule
from app.optimizer.unified_engine import append_cost_export_findings
from app.ai_analysis import enrich_analysis_with_ai
from app.finding_evidence import enrich_finding_for_api
from app.user_auth import require_admin_user, require_authenticated_user
from app.validators import validate_subscription_id, validate_finding_status
import structlog

log = structlog.get_logger()

router = APIRouter(tags=["Optimization Engine"])


class AnalyzeRequest(BaseModel):
    subscription_id:  str
    profile:          str  = Field("default")
    engine_version:   str  = Field("extended", description="standard | extended")
    data_source:      str  = Field("db", description="db | live")
    rule_overrides:   dict = Field(default_factory=dict)
    components:       Optional[list[str]] = None
    include_metrics:  bool = Field(True)
    include_ai:       bool = Field(True)
    timespan_metrics: str  = Field("P7D")

    @field_validator("subscription_id")
    @classmethod
    def _validate_subscription(cls, value: str) -> str:
        return validate_subscription_id(value)

    @field_validator("data_source")
    @classmethod
    def _validate_data_source(cls, value: str) -> str:
        v = (value or "db").strip().lower()
        if v not in {"db", "live"}:
            raise ValueError("data_source must be 'db' or 'live'")
        return v


class FindingStatusIn(BaseModel):
    status: str = Field(..., description="open | acknowledged | resolved | ignored")

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return validate_finding_status(value)


class BulkFindingStatusIn(BaseModel):
    finding_ids: list[str] = Field(..., min_length=1, max_length=500)
    status: str = Field(...)

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return validate_finding_status(value)


class RuleConfigIn(BaseModel):
    rule_id:     str  = Field(...)
    enabled:     bool = True
    overrides:   dict = Field(default_factory=dict)
    description: Optional[str] = None


class ActionWorkflowIn(BaseModel):
    workflow_status: str | None = Field(None)
    owner: str | None = None
    note: str | None = None
    clear_owner: bool = False

    @field_validator("workflow_status")
    @classmethod
    def _validate_workflow(cls, value: str | None) -> str | None:
        if value is None:
            return None
        v = value.strip().lower()
        valid = {"proposed", "approved", "executed", "rejected", "deferred"}
        if v not in valid:
            raise ValueError(f"workflow_status must be one of: {sorted(valid)}")
        return v


class BulkActionWorkflowIn(BaseModel):
    action_ids: list[str] = Field(..., min_length=1, max_length=500)
    workflow_status: str = Field(...)
    note: str | None = None

    @field_validator("workflow_status")
    @classmethod
    def _validate_workflow(cls, value: str) -> str:
        v = value.strip().lower()
        valid = {"proposed", "approved", "executed", "rejected", "deferred"}
        if v not in valid:
            raise ValueError(f"workflow_status must be one of: {sorted(valid)}")
        return v


class BulkActionAssignIn(BaseModel):
    action_ids: list[str] = Field(..., min_length=1, max_length=500)
    owner: str = Field(..., min_length=1, max_length=200)
    note: str | None = None


class FindingExecutionIn(BaseModel):
    action_type: str = Field(...)
    before_state: dict[str, Any] = Field(default_factory=dict)


class FindingValidationIn(BaseModel):
    after_state: dict[str, Any] = Field(default_factory=dict)
    regressed: bool = False


class BatchResourceLookupIn(BaseModel):
    subscription_id: str
    resource_ids: list[str] = Field(..., min_length=1, max_length=25)
    timespan: str = Field("P7D")
    include_metrics: bool = True
    include_advanced_analysis: bool = True


class BulkResourceTagsIn(BaseModel):
    subscription_id: str
    resource_ids: list[str] = Field(..., min_length=1, max_length=50)
    tags: dict[str, str] = Field(default_factory=dict)


class ResourceTagsIn(BaseModel):
    tags: dict[str, str] = Field(default_factory=dict)

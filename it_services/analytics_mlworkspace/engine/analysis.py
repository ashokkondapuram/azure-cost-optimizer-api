"""Analysis rules — owned by analytics-mlworkspace IT service."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.analytics_mlworkspace.engine.optimization_rules import (
    evaluate_ml_workspace_compute,
    evaluate_ml_workspace_dev_idle,
)


def analyze_ml_workspaces(
    engine,
    subscription_id: str,
    workspaces: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    compute_rule = engine.rules.get("ML_WORKSPACE_COMPUTE_EXTENDED")
    idle_rule = engine.rules.get("ML_WORKSPACE_IDLE_EXTENDED")
    for ws in workspaces:
        monthly = resource_cost(cost_by_resource, ws.get("id", ""))
        append_stub_draft(out, engine, subscription_id, ws, compute_rule, evaluate_ml_workspace_compute(ws, monthly, compute_rule))
        append_stub_draft(out, engine, subscription_id, ws, idle_rule, evaluate_ml_workspace_dev_idle(ws, monthly, idle_rule))
    return out

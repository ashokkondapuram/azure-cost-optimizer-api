"""Analysis rules — owned by analytics-databricks IT service."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.analytics_databricks.engine.optimization_rules import (
    evaluate_databricks_cluster_cost,
    evaluate_databricks_dev_workspace,
)


def analyze_databricks(
    engine,
    subscription_id: str,
    workspaces: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    cluster_rule = engine.rules.get("DATABRICKS_CLUSTER_EXTENDED")
    dev_rule = engine.rules.get("DATABRICKS_DEV_WORKSPACE_EXTENDED")
    for ws in workspaces:
        monthly = resource_cost(cost_by_resource, ws.get("id", ""))
        append_stub_draft(out, engine, subscription_id, ws, cluster_rule, evaluate_databricks_cluster_cost(ws, monthly, cluster_rule))
        append_stub_draft(out, engine, subscription_id, ws, dev_rule, evaluate_databricks_dev_workspace(ws, monthly, dev_rule))
    return out

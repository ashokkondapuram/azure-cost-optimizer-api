"""Analysis rules — owned by analytics-synapse IT service."""

from __future__ import annotations

from typing import Any

from app.cost_utils import resource_cost
from app.optimizer.core.finding import ExtendedFinding
from app.stub_engine_common import append_stub_draft
from it_services.analytics_synapse.engine.optimization_rules import (
    evaluate_synapse_pause_cost,
    evaluate_synapse_sql_idle,
)


def analyze_synapse(
    engine,
    subscription_id: str,
    workspaces: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    pause_rule = engine.rules.get("SYNAPSE_PAUSE_EXTENDED")
    idle_rule = engine.rules.get("SYNAPSE_SQL_IDLE_EXTENDED")
    for ws in workspaces:
        monthly = resource_cost(cost_by_resource, ws.get("id", ""))
        append_stub_draft(out, engine, subscription_id, ws, pause_rule, evaluate_synapse_pause_cost(ws, monthly, pause_rule))
        append_stub_draft(out, engine, subscription_id, ws, idle_rule, evaluate_synapse_sql_idle(ws, monthly, idle_rule))
    return out

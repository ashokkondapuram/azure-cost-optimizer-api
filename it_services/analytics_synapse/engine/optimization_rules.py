"""Synapse optimization decision rules — pause schedules and SQL pool activity."""

from __future__ import annotations

from typing import Any

from app.resource_utilization import fact_value, make_check, monitor_facts_status
from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_finding_draft, metric_finding_draft

_CANONICAL = "analytics/synapse"


def _thresholds(rule: Any) -> dict[str, float]:
    return threshold_values(
        rule,
        _CANONICAL,
        min_cost="min_monthly_cost_usd",
        idle_min_cost="idle_min_monthly_cost_usd",
        savings_factor="savings_factor",
        idle_savings_factor="idle_savings_factor",
        query_low="sql_query_low_count",
        min_savings="min_monthly_savings_usd",
    )


def evaluate_synapse_pause_cost(
    workspace: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    return cost_finding_draft(
        rule_id="SYNAPSE_PAUSE_EXTENDED",
        resource=workspace,
        monthly=monthly_cost,
        detail_suffix="Dedicated SQL pools may run continuously without pause schedules.",
        recommendation=(
            "Pause dedicated SQL pools outside business hours, scale DWUs to workload peaks, "
            "and use serverless SQL for ad hoc queries."
        ),
        savings_factor=th["savings_factor"],
        waste_score=70,
        priority="P1",
        impact="Analytics compute cost optimization",
        min_savings=th["min_savings"],
    )


def evaluate_synapse_sql_idle(
    workspace: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["idle_min_cost"]:
        return None
    if monitor_facts_status(workspace, "sql_query_count") == "available":
        queries = fact_value(workspace, "sql_query_count")
        if queries is not None and queries >= th["query_low"]:
            return None
    name = workspace.get("name") or ""
    return metric_finding_draft(
        rule_id="SYNAPSE_SQL_IDLE_EXTENDED",
        resource=workspace,
        monthly=monthly_cost,
        detail=(
            f"Synapse workspace '{name}' has MTD spend of ${monthly_cost:,.2f} "
            "with low dedicated SQL pool activity."
        ),
        recommendation="Pause or scale down dedicated SQL pools when query volume is low.",
        savings=monthly_cost * th["idle_savings_factor"] if monthly_cost > 0 else 0.0,
        waste_score=58,
        priority="P2",
        impact="Reduce idle dedicated SQL pool charges",
        determination="low_sql_activity",
        summary="Synapse workspace shows low SQL pool utilization.",
        checks=[make_check("SQL query count", fact_value(workspace, "sql_query_count"), f"< {th['query_low']:.0f}", passed=True)],
        extra={"sql_query_count": fact_value(workspace, "sql_query_count")},
        required_keys=("sql_query_count",),
    )

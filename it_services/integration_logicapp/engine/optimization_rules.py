"""Logic App optimization decision rules — plan cost and run volume."""

from __future__ import annotations

from typing import Any

from app.resource_utilization import fact_value, make_check, utilization_gate
from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_finding_draft, metric_finding_draft

_CANONICAL = "integration/logicapp"


def _thresholds(rule: Any) -> dict[str, float]:
    return threshold_values(
        rule,
        _CANONICAL,
        min_cost="min_monthly_cost_usd",
        runs_low="runs_started_low",
        savings_factor="savings_factor",
        idle_savings_factor="idle_savings_factor",
        min_savings="min_monthly_savings_usd",
    )


def evaluate_logicapp_plan_cost(
    workflow: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    props = workflow.get("properties") or {}
    state = (props.get("state") or "").lower()
    return cost_finding_draft(
        rule_id="LOGIC_APP_PLAN_EXTENDED",
        resource=workflow,
        monthly=monthly_cost,
        detail_suffix=f"Workflow state is {state or 'unknown'}.",
        recommendation=(
            "Trim run history retention, consolidate workflows, "
            "and use Consumption plan for intermittent workloads."
        ),
        savings_factor=th["savings_factor"],
        waste_score=45,
        priority="P3",
        impact="Reduce workflow storage and execution charges",
        min_savings=th["min_savings"],
        extra_evidence={"state": state},
    )


def evaluate_logicapp_low_runs(
    workflow: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    if not utilization_gate(workflow, "runs_started", allow_inventory_only=False):
        return None
    runs = fact_value(workflow, "runs_started")
    if runs is not None and runs >= th["runs_low"]:
        return None
    name = workflow.get("name") or ""
    return metric_finding_draft(
        rule_id="LOGIC_APP_LOW_RUNS_EXTENDED",
        resource=workflow,
        monthly=monthly_cost,
        detail=(
            f"Logic App '{name}' started {runs if runs is not None else 'few'} runs "
            f"in the evaluation window (threshold: {th['runs_low']:.0f})."
        ),
        recommendation="Move low-volume workflows to Consumption plan or consolidate into shared workflows.",
        savings=monthly_cost * th["idle_savings_factor"] if monthly_cost > 0 else 0.0,
        waste_score=42,
        priority="P3",
        impact="Reduce Logic App execution charges",
        determination="low_run_volume",
        summary="Logic App run volume is below optimization threshold.",
        checks=[make_check("Runs started", runs, f"< {th['runs_low']:.0f}", passed=True)],
        extra={"runs_started": runs},
        required_keys=("runs_started",),
    )

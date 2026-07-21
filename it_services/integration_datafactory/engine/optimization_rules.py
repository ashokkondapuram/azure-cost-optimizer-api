"""Data Factory optimization decision rules — pipeline activity and IR cost."""

from __future__ import annotations

from typing import Any

from app.resource_utilization import fact_value, make_check, utilization_gate
from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_finding_draft, env_tag, metric_finding_draft

_CANONICAL = "integration/datafactory"


def _thresholds(rule: Any) -> dict[str, float]:
    return threshold_values(
        rule,
        _CANONICAL,
        min_cost="min_monthly_cost_usd",
        pipeline_low="pipeline_runs_low",
        savings_factor="savings_factor",
        idle_savings_factor="idle_savings_factor",
        min_savings="min_monthly_savings_usd",
    )


def evaluate_datafactory_ir_cost(
    factory: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    return cost_finding_draft(
        rule_id="DATA_FACTORY_IR_EXTENDED",
        resource=factory,
        monthly=monthly_cost,
        detail_suffix="Review self-hosted integration runtimes and pipeline schedules.",
        recommendation=(
            "Pause unused pipelines, right-size integration runtimes, "
            "and use Azure-hosted IR only when needed."
        ),
        savings_factor=th["savings_factor"],
        waste_score=52,
        priority="P2",
        impact="Optimize pipeline and IR runtime cost",
        min_savings=th["min_savings"],
        extra_evidence={"environment": env_tag(factory)},
    )


def evaluate_datafactory_idle_pipelines(
    factory: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    if not utilization_gate(factory, "pipeline_succeeded", allow_inventory_only=False):
        return None
    runs = fact_value(factory, "pipeline_succeeded")
    if runs is not None and runs >= th["pipeline_low"]:
        return None
    name = factory.get("name") or ""
    return metric_finding_draft(
        rule_id="DATA_FACTORY_IDLE_PIPELINES_EXTENDED",
        resource=factory,
        monthly=monthly_cost,
        detail=(
            f"Data Factory '{name}' has low successful pipeline activity "
            f"({runs if runs is not None else 'n/a'} runs, threshold {th['pipeline_low']:.0f})."
        ),
        recommendation="Pause idle pipelines and decommission unused self-hosted integration runtimes.",
        savings=monthly_cost * th["idle_savings_factor"] if monthly_cost > 0 else 0.0,
        waste_score=48,
        priority="P2",
        impact="Reduce pipeline orchestration cost",
        determination="idle_pipelines",
        summary="Data Factory shows low pipeline execution volume.",
        checks=[make_check("Successful runs", runs, f"< {th['pipeline_low']:.0f}", passed=True)],
        extra={"pipeline_succeeded": runs},
        required_keys=("pipeline_succeeded",),
    )

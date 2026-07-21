"""ML workspace optimization decision rules — compute cost and dev workloads."""

from __future__ import annotations

from typing import Any

from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_finding_draft, env_tag

_CANONICAL = "analytics/mlworkspace"


def _thresholds(rule: Any) -> dict[str, float]:
    return threshold_values(
        rule,
        _CANONICAL,
        min_cost="min_monthly_cost_usd",
        dev_min_cost="dev_min_monthly_cost_usd",
        savings_factor="savings_factor",
        dev_savings_factor="dev_savings_factor",
        min_savings="min_monthly_savings_usd",
    )


def evaluate_ml_workspace_compute(
    workspace: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    return cost_finding_draft(
        rule_id="ML_WORKSPACE_COMPUTE_EXTENDED",
        resource=workspace,
        monthly=monthly_cost,
        detail_suffix="Review idle compute clusters and managed online endpoints.",
        recommendation=(
            "Delete idle compute clusters, use low-priority VMs for training, "
            "and scale managed online endpoints to zero when unused."
        ),
        savings_factor=th["savings_factor"],
        waste_score=54,
        priority="P2",
        impact="Analytics compute cost optimization",
        min_savings=th["min_savings"],
    )


def evaluate_ml_workspace_dev_idle(
    workspace: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    env = env_tag(workspace)
    if env not in {"dev", "development", "test", "qa", "sandbox", "nonprod", "non-prod"}:
        return None
    if monthly_cost < th["dev_min_cost"]:
        return None
    return cost_finding_draft(
        rule_id="ML_WORKSPACE_IDLE_EXTENDED",
        resource=workspace,
        monthly=monthly_cost,
        detail_suffix=f"Non-production ML workspace (environment: {env or 'unknown'}) has idle compute spend.",
        recommendation="Shut down idle compute instances and use serverless endpoints where possible.",
        savings_factor=th["dev_savings_factor"],
        waste_score=50,
        priority="P2",
        impact="Reduce non-production ML compute spend",
        min_savings=th["min_savings"],
        extra_evidence={"environment": env},
    )

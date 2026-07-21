"""Databricks optimization decision rules — cost and environment thresholds."""

from __future__ import annotations

from typing import Any

from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_finding_draft, env_tag

_CANONICAL = "analytics/databricks"


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


def evaluate_databricks_cluster_cost(
    workspace: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    return cost_finding_draft(
        rule_id="DATABRICKS_CLUSTER_EXTENDED",
        resource=workspace,
        monthly=monthly_cost,
        detail_suffix="Review cluster auto-termination and job vs all-purpose cluster usage.",
        recommendation=(
            "Enable auto-termination on clusters, use job clusters instead of all-purpose, "
            "and apply spot instances for non-critical workloads."
        ),
        savings_factor=th["savings_factor"],
        waste_score=68,
        priority="P1",
        impact="Analytics compute cost optimization",
        min_savings=th["min_savings"],
    )


def evaluate_databricks_dev_workspace(
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
        rule_id="DATABRICKS_DEV_WORKSPACE_EXTENDED",
        resource=workspace,
        monthly=monthly_cost,
        detail_suffix=f"Non-production workspace (environment: {env or 'unknown'}) has elevated spend.",
        recommendation=(
            "Use job clusters with auto-termination, smaller worker SKUs, and spot instances "
            "for dev/test workloads."
        ),
        savings_factor=th["dev_savings_factor"],
        waste_score=62,
        priority="P2",
        impact="Reduce non-production Databricks spend",
        min_savings=th["min_savings"],
        extra_evidence={"environment": env},
    )

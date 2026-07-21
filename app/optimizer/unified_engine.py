"""Unified analysis entry — inventory engine + cost-export rules with shared profile config."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.cost_export_recommendations import analyze_cost_export_resources
from app.analysis_summary import merge_analysis_results
from app.optimizer.engine_config import get_effective_config
from app.resource_store import list_cost_resources_db


def merge_rule_overrides(
    db: Session,
    profile: str,
    rule_overrides: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """Merge persisted profile config with optional request-time overrides."""
    return {**get_effective_config(db, profile), **(rule_overrides or {})}


def run_cost_export_analysis(
    db: Session,
    subscription_id: str,
    *,
    profile: str = "default",
    rule_overrides: dict[str, dict] | None = None,
) -> list[dict[str, Any]]:
    """Run cost-export rules using the same profile overrides as the inventory engine."""
    merged = merge_rule_overrides(db, profile, rule_overrides)
    resources = list_cost_resources_db(db, subscription_id)
    return analyze_cost_export_resources(
        subscription_id,
        resources,
        rule_overrides=merged,
    )


def append_cost_export_findings(
    db: Session,
    subscription_id: str,
    result: dict[str, Any],
    *,
    profile: str = "default",
    rule_overrides: dict[str, dict] | None = None,
    engine_version: str = "extended",
) -> dict[str, Any]:
    """Merge cost-export findings into an inventory engine result payload."""
    cost_findings = run_cost_export_analysis(
        db,
        subscription_id,
        profile=profile,
        rule_overrides=rule_overrides,
    )
    if not cost_findings:
        return result

    merged = merge_analysis_results(
        [result, {"findings": cost_findings}],
        engine_version,
    )
    merged["engine_version"] = engine_version
    merged["cost_export_findings"] = len(cost_findings)
    if result.get("metrics_context"):
        merged["metrics_context"] = result["metrics_context"]
    return merged

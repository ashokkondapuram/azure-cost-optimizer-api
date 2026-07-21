"""Log Analytics optimization decision rules — retention and ingestion."""

from __future__ import annotations

from typing import Any

from app.resource_utilization import fact_value, make_check
from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_savings, metric_finding_draft

_CANONICAL = "monitoring/loganalytics"


def _thresholds(rule: Any) -> dict[str, float]:
    return threshold_values(
        rule,
        _CANONICAL,
        min_cost="min_monthly_cost_usd",
        retention_high="retention_days_high",
        ingestion_high="ingestion_gb_high",
        savings_factor="savings_factor",
        min_savings="min_monthly_savings_usd",
    )


def evaluate_log_analytics_retention(
    workspace: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    props = workspace.get("properties") or {}
    retention = int(props.get("retentionInDays") or 0)
    ingestion = fact_value(workspace, "ingestion_gb")
    if monthly_cost < th["min_cost"] and ingestion is None:
        return None
    high_retention = retention > th["retention_high"]
    high_ingestion = ingestion is not None and ingestion > th["ingestion_high"]
    if not high_retention and not high_ingestion and monthly_cost < th["min_cost"]:
        return None
    name = workspace.get("name") or ""
    detail = f"Log Analytics workspace '{name}' has MTD spend of ${monthly_cost:,.2f}."
    if high_retention:
        detail += f" Retention is {retention} days."
    if high_ingestion:
        detail += f" Ingestion is {ingestion:.1f} GB in the evaluation window."
    return metric_finding_draft(
        rule_id="LOG_ANALYTICS_RETENTION_EXTENDED",
        resource=workspace,
        monthly=monthly_cost,
        detail=detail,
        recommendation=(
            "Review data collection rules, shorten retention, "
            "and use Basic logs or commitment tiers where appropriate."
        ),
        savings=cost_savings(monthly_cost, th["savings_factor"], min_savings=th["min_savings"]),
        waste_score=65,
        priority="P1",
        impact="Reduce observability ingestion cost",
        determination="ingestion_review",
        summary="Log Analytics workspace shows high retention or ingestion.",
        checks=[
            make_check("Retention days", retention, f"> {th['retention_high']:.0f}", passed=high_retention),
            make_check("Ingestion GB", ingestion, f"> {th['ingestion_high']:.0f}", passed=high_ingestion),
        ],
        extra={"retention_days": retention, "ingestion_gb": ingestion},
    )


def evaluate_log_analytics_high_ingestion(
    workspace: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    ingestion = fact_value(workspace, "ingestion_gb")
    if ingestion is None or float(ingestion) <= th["ingestion_high"]:
        return None
    if monthly_cost < th["min_savings"]:
        return None
    name = workspace.get("name") or ""
    return metric_finding_draft(
        rule_id="LOG_ANALYTICS_INGESTION_EXTENDED",
        resource=workspace,
        monthly=monthly_cost,
        detail=(
            f"Log Analytics workspace '{name}' ingested {float(ingestion):.1f} GB "
            f"(threshold: {th['ingestion_high']:.0f} GB)."
        ),
        recommendation="Tune data collection rules, enable table-level retention, and review diagnostic settings.",
        savings=cost_savings(monthly_cost, th["savings_factor"], min_savings=th["min_savings"]),
        waste_score=60,
        priority="P1",
        impact="Lower high-volume log ingestion cost",
        determination="high_ingestion",
        summary="Log ingestion exceeds configured threshold.",
        checks=[make_check("Ingestion GB", ingestion, f"> {th['ingestion_high']:.0f}", passed=True)],
        extra={"ingestion_gb": ingestion},
        required_keys=("ingestion_gb",),
    )

"""Application Insights optimization decision rules — sampling and request volume."""

from __future__ import annotations

from typing import Any

from app.resource_utilization import fact_value, make_check, utilization_gate
from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_savings, metric_finding_draft

_CANONICAL = "monitoring/appinsights"


def _thresholds(rule: Any) -> dict[str, float]:
    return threshold_values(
        rule,
        _CANONICAL,
        min_cost="min_monthly_cost_usd",
        requests_low="request_count_low",
        savings_factor="savings_factor",
        min_savings="min_monthly_savings_usd",
    )


def evaluate_appinsights_sampling(
    component: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    requests = fact_value(component, "request_count")
    name = component.get("name") or ""
    detail = f"Application Insights component '{name}' has MTD spend of ${monthly_cost:,.2f}."
    if requests is not None:
        detail += f" Request count is {requests:,.0f} in the evaluation window."
    return metric_finding_draft(
        rule_id="APP_INSIGHTS_SAMPLING_EXTENDED",
        resource=component,
        monthly=monthly_cost,
        detail=detail,
        recommendation=(
            "Enable adaptive sampling, cap daily ingestion, "
            "and move long-term analytics to Log Analytics with tuned retention."
        ),
        savings=cost_savings(monthly_cost, th["savings_factor"], min_savings=th["min_savings"]),
        waste_score=55,
        priority="P2",
        impact="Lower telemetry ingestion without losing signal",
        determination="sampling_review",
        summary="Application Insights ingestion cost warrants sampling review.",
        checks=[make_check("Request count", requests, "Review", passed=True)],
        extra={"request_count": requests},
    )


def evaluate_appinsights_low_traffic(
    component: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    if not utilization_gate(component, "request_count", allow_inventory_only=False):
        return None
    requests = fact_value(component, "request_count")
    if requests is not None and requests >= th["requests_low"]:
        return None
    name = component.get("name") or ""
    return metric_finding_draft(
        rule_id="APP_INSIGHTS_LOW_TRAFFIC_EXTENDED",
        resource=component,
        monthly=monthly_cost,
        detail=(
            f"Application Insights '{name}' has low request volume "
            f"({requests if requests is not None else 'n/a'} requests)."
        ),
        recommendation="Consolidate telemetry into a shared workspace or reduce daily data cap.",
        savings=cost_savings(monthly_cost, th["savings_factor"], min_savings=th["min_savings"]),
        waste_score=48,
        priority="P3",
        impact="Reduce telemetry cost for low-traffic apps",
        determination="low_traffic",
        summary="Request volume is below optimization threshold.",
        checks=[make_check("Request count", requests, f"< {th['requests_low']:.0f}", passed=True)],
        extra={"request_count": requests},
        required_keys=("request_count",),
    )

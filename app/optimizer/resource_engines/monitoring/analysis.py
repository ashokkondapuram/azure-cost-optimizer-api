"""Monitoring resource optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import fact_value
from app.resource_utilization import structured_evidence


def analyze_log_analytics(
    engine,
    subscription_id: str,
    workspaces: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("LOG_ANALYTICS_RETENTION_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for ws in workspaces:
        props = ws.get("properties") or {}
        name = ws.get("name") or ""
        retention = int(props.get("retentionInDays") or 0)
        monthly = resource_cost(cost_by_resource, ws.get("id", ""))
        ingestion = fact_value(ws, "ingestion_gb")
        if monthly < rule.min_monthly_savings_usd and ingestion is None:
            continue
        high_retention = retention > 90
        high_ingestion = ingestion is not None and ingestion > 10
        if not high_retention and not high_ingestion and monthly < 50:
            continue
        detail = f"Log Analytics workspace '{name}' has MTD spend of ${monthly:,.2f}."
        if high_retention:
            detail += f" Retention is {retention} days."
        if high_ingestion:
            detail += f" Ingestion is {ingestion:.1f} GB in the evaluation window."
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=ws,
            detail=detail,
            recommendation="Review data collection rules, shorten retention, and use Basic logs or commitment tiers where appropriate.",
            savings=savings_from_factor(monthly, 0.30) if monthly > 0 else 0,
            waste_score=65,
            confidence=confidence_with_monitor(72, ws),
            priority="P1",
            impact="Reduce observability ingestion cost",
            evidence=structured_evidence(
                ws,
                determination="ingestion_review",
                summary="Log Analytics workspace shows high retention or ingestion.",
                extra={"retention_days": retention, "monthly_cost_usd": monthly, "ingestion_gb": ingestion},
            ),
        ))
    return out


def analyze_app_insights(
    engine,
    subscription_id: str,
    components: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("APP_INSIGHTS_SAMPLING_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for comp in components:
        name = comp.get("name") or ""
        monthly = resource_cost(cost_by_resource, comp.get("id", ""))
        if monthly < 30:
            continue
        requests = fact_value(comp, "request_count")
        detail = f"Application Insights component '{name}' has MTD spend of ${monthly:,.2f}."
        if requests is not None:
            detail += f" Request count is {requests:,.0f} in the evaluation window."
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=comp,
            detail=detail,
            recommendation="Enable adaptive sampling, cap daily ingestion, and move long-term analytics to Log Analytics with tuned retention.",
            savings=savings_from_factor(monthly, 0.25),
            waste_score=55,
            confidence=confidence_with_monitor(70, comp),
            priority="P2",
            impact="Lower telemetry ingestion without losing signal",
            evidence={"monthly_cost_usd": monthly, "request_count": requests},
        ))
    return out

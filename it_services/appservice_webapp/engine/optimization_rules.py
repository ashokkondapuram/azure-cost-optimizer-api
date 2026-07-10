"""App Service optimization decision rules — plan load and consolidation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.app_service_catalog import optimization_thresholds as app_thresholds
from app.app_service_plan_catalog import consolidation_defaults, optimization_thresholds as plan_thresholds
from app.compute_pricing import estimate_app_service_savings
from app.resource_utilization import (
    confidence_with_monitor,
    cpu_pct,
    fact_value,
    is_low_request_volume,
    make_check,
    monitor_facts_status,
    structured_evidence,
    webapp_utilization_summary,
)


@dataclass(frozen=True)
class ComputeFindingDraft:
    rule_id: str
    detail: str
    recommendation: str
    savings: float
    waste_score: int
    confidence: int
    priority: str
    impact: str
    evidence: dict[str, Any]


def evaluate_webapp_plan_load_low(
    plan: dict[str, Any],
    app_count: int,
    monthly_cost: float,
    rule: Any,
) -> ComputeFindingDraft | None:
    defaults = app_thresholds()
    th = {
        "load_low_pct": float(getattr(rule, "plan_load_low_pct", defaults.get("plan_load_low_pct", 20.0))),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 5.0))),
    }
    if app_count == 0:
        return None
    if monitor_facts_status(plan, "cpu_pct", "cpu_time") not in {"available", "partial"}:
        return None
    cpu = cpu_pct(plan) or fact_value(plan, "cpu_pct")
    if cpu is None or float(cpu) >= th["load_low_pct"]:
        return None
    name = plan.get("name") or ""
    sku = plan.get("sku") or {}
    tier = sku.get("tier") or ""
    savings = estimate_app_service_savings(monthly_cost, tier, savings_factor=0.25, min_savings=th["min_savings"])
    return ComputeFindingDraft(
        rule_id="WEBAPP_PLAN_LOAD_LOW_EXTENDED",
        detail=(
            f"App Service Plan '{name}' ({tier}) averages {float(cpu):.1f}% CPU load "
            f"with {app_count} hosted app(s)."
        ),
        recommendation="Downsize plan tier or enable autoscaling on Standard+ plans to match actual load.",
        savings=savings,
        waste_score=56,
        confidence=confidence_with_monitor(76, plan),
        priority="P2",
        impact="Plan right-sizing reduces fixed App Service charges",
        evidence=structured_evidence(
            plan,
            determination="low_plan_load",
            summary="App Service Plan CPU utilization is below downsize threshold.",
            checks=[
                make_check("Average CPU %", cpu, f"< {th['load_low_pct']:.0f}%", passed=True),
                make_check("Hosted apps", app_count, ">= 1", passed=True),
            ],
            extra={"tier": tier, "monthly_cost_usd": monthly_cost},
        ),
    )


def evaluate_asp_consolidation_candidate(
    plan: dict[str, Any],
    app_count: int,
    monthly_cost: float,
    rule: Any,
) -> ComputeFindingDraft | None:
    defaults = plan_thresholds()
    cons = consolidation_defaults()
    th = {
        "max_apps": float(getattr(rule, "asp_consolidation_app_max", defaults.get("consolidation_app_count_max", 5.0))),
        "min_apps_dedicated": float(cons.get("min_apps_for_dedicated_plan", 5)),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 10.0))),
    }
    sku = plan.get("sku") or {}
    tier = (sku.get("tier") or "").lower()
    if tier in {"free", "shared"}:
        return None
    if app_count == 0 or app_count >= th["min_apps_dedicated"]:
        return None
    if app_count > th["max_apps"]:
        return None
    name = plan.get("name") or ""
    savings = estimate_app_service_savings(monthly_cost, tier, savings_factor=0.40, min_savings=th["min_savings"])
    return ComputeFindingDraft(
        rule_id="ASP_CONSOLIDATION_CANDIDATE_EXTENDED",
        detail=(
            f"App Service Plan '{name}' ({tier}) hosts only {app_count} app(s) — "
            f"consolidation may reduce platform overhead."
        ),
        recommendation="Merge apps from underutilized plans into a shared Standard plan with autoscaling.",
        savings=savings,
        waste_score=62,
        confidence=68,
        priority="P2",
        impact="Plan consolidation can reduce duplicate App Service Plan charges",
        evidence=structured_evidence(
            plan,
            determination="consolidation_candidate",
            summary="Plan hosts fewer apps than recommended for a dedicated tier.",
            checks=[
                make_check("Hosted apps", app_count, f"< {int(th['min_apps_dedicated'])}", passed=True),
            ],
            extra={"tier": tier, "monthly_cost_usd": monthly_cost},
        ),
    )

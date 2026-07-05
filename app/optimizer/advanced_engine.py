"""Multi-signal optimization scoring engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.optimizer.dependency_analyzer import infer_criticality_from_tags, is_compliance_locked, sla_tier
from app.optimizer.scoring_weights import (
    CRITICALITY_RANK,
    SLA_RISK,
    TIER_THRESHOLDS,
    clamp_score,
    load_weights,
)

_EFFORT_BY_TYPE: dict[str, tuple[str, float, bool]] = {
    "compute/vm": ("simple", 70.0, True),
    "compute/disk": ("simple", 75.0, True),
    "compute/vmss": ("medium", 45.0, False),
    "containers/aks": ("complex", 25.0, False),
    "database/sql": ("complex", 20.0, False),
    "appservice/webapp": ("medium", 50.0, True),
}

_RESIZE_RULES = frozenset({
    "VM_UNDERUTILIZED_EXTENDED", "VM_RIGHTSIZE_FAMILY", "VM_SKU_SIZING_EXTENDED",
})
_DISK_RULES = frozenset({"DISK_OVERSIZE_EXTENDED", "DISK_UNUSED_EXTENDED"})
_COMMIT_RULES = frozenset({"VM_COMMITMENT_CANDIDATE"})
_PERF_RULES = frozenset({"VM_DISK_BOTTLENECK", "VM_NETWORK_BOTTLENECK", "DISK_UNDERPROVISIONED"})


@dataclass
class DimensionScores:
    cost: float = 0.0
    safety: float = 0.0
    effort: float = 0.0
    workload: float = 0.0
    business: float = 0.0
    overall: float = 0.0
    performance_risk: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)


def _savings_from_signals(
    *,
    monthly_cost: float,
    advisor_savings: float,
    finding_savings: float,
) -> tuple[float, float]:
    monthly = round(max(advisor_savings, finding_savings, 0.0), 2)
    confidence = 50.0
    if advisor_savings > 0 and finding_savings > 0:
        confidence = 85.0
    elif advisor_savings > 0 or finding_savings > 0:
        confidence = 65.0
    return monthly, confidence


def _cost_dimension(
    *,
    monthly_savings: float,
    savings_confidence: float,
    monthly_cost: float,
    trend_penalty: float,
) -> float:
    if monthly_savings <= 0:
        return 10.0 if monthly_cost > 0 else 0.0
    savings_ratio = min(1.0, monthly_savings / max(monthly_cost, 1.0))
    raw = savings_ratio * 60.0 + (savings_confidence / 100.0) * 40.0
    return clamp_score(raw - trend_penalty)


def _performance_risk_score(
    *,
    facts: dict[str, float],
    workload: dict[str, Any],
    trends: dict[str, Any],
    has_perf_advisor: bool,
    has_bottleneck: bool,
) -> float:
    avg_cpu = float(facts.get("avg_cpu_pct") or 0)
    max_cpu = float(facts.get("max_cpu_pct") or avg_cpu)
    burstiness = float(workload.get("burstiness_score") or 0)
    volatility = float(trends.get("utilization_volatility") or 0) * 100

    risk = 0.0
    if max_cpu > 80:
        risk += 35
    elif max_cpu > 60:
        risk += 20
    risk += min(25, burstiness * 0.4)
    risk += min(20, volatility * 0.5)
    if has_perf_advisor:
        risk += 15
    if has_bottleneck:
        risk += 25
    if workload.get("workload_type") == "bursty":
        risk += 10
    return clamp_score(risk)


def _safety_dimension(
    perf_risk: float,
    blast_radius: int,
    max_criticality: str,
    sla_risk: float,
) -> float:
    dep_penalty = min(40, blast_radius * 8)
    crit_penalty = {c: v * 8 for c, v in CRITICALITY_RANK.items()}.get(max_criticality, 8)
    combined_risk = perf_risk * 0.5 + dep_penalty + crit_penalty + sla_risk * 0.3
    return clamp_score(100.0 - combined_risk)


def _effort_dimension(resource_type: str, action_type: str) -> tuple[str, float, bool]:
    effort, score, automated = _EFFORT_BY_TYPE.get(resource_type, ("medium", 50.0, False))
    if action_type in {"investigate", "manual_review"}:
        return effort, clamp_score(score - 10), automated
    if action_type in {"resize_down", "downgrade_disk"}:
        return effort, clamp_score(score), automated
    if action_type == "buy_reservation":
        return "medium", 55.0, False
    return effort, clamp_score(score), automated


def _workload_dimension(workload: dict[str, Any]) -> float:
    wtype = workload.get("workload_type") or "interactive"
    burstiness = float(workload.get("burstiness_score") or 0)
    base = {
        "steady": 85.0,
        "interactive": 60.0,
        "bursty": 35.0,
        "batch": 45.0,
    }.get(wtype, 50.0)
    if workload.get("detected_seasonality"):
        base -= 10
    base -= min(20, burstiness * 0.2)
    trend = workload.get("utilization_trend")
    if trend == "increasing":
        base -= 15
    elif trend == "decreasing":
        base += 5
    return clamp_score(base)


def _business_dimension(tags: dict[str, str], monthly_cost: float) -> tuple[float, str]:
    crit = infer_criticality_from_tags(tags, monthly_cost=monthly_cost)
    rank = CRITICALITY_RANK.get(crit, 2)
    score = clamp_score(100.0 - rank * 20.0)
    return score, crit


def _primary_action(
    *,
    rule_ids: set[str],
    has_cost_advisor: bool,
    has_perf_advisor: bool,
    perf_risk: float,
    monthly_savings: float,
) -> tuple[str, str]:
    if has_cost_advisor and has_perf_advisor:
        return "manual_review", "Manual review"
    if perf_risk >= 50 or (has_cost_advisor and perf_risk >= 35):
        return "manual_review", "Manual review"
    if rule_ids & _COMMIT_RULES:
        return "buy_reservation", "High"
    if rule_ids & _RESIZE_RULES:
        return "resize_down", "High" if perf_risk < 25 else "Medium"
    if rule_ids & _DISK_RULES:
        return "downgrade_disk", "High" if perf_risk < 25 else "Medium"
    if has_cost_advisor or monthly_savings > 0:
        return "investigate", "Medium"
    if rule_ids:
        return "investigate", "Low"
    return "keep", "Low"


def assign_recommendation_tier(
    *,
    overall: float,
    perf_risk: float,
    blast_radius: int,
    compliance_locked: bool,
    sla: str,
    monthly_savings: float,
) -> str:
    if compliance_locked:
        return "blocked"
    if sla == "gold":
        return "blocked"
    if monthly_savings <= 0 and overall < 50:
        return "blocked"
    if overall <= TIER_THRESHOLDS["tier3_min_overall"]:
        return "blocked"
    if (
        overall > TIER_THRESHOLDS["tier1_min_overall"]
        and perf_risk < TIER_THRESHOLDS["tier1_max_perf_risk"]
        and blast_radius <= TIER_THRESHOLDS["tier1_max_blast_radius"]
        and sla in {"none", "bronze"}
    ):
        return "tier1_safe"
    if (
        overall > TIER_THRESHOLDS["tier2_min_overall"]
        and perf_risk < TIER_THRESHOLDS["tier2_max_perf_risk"]
        and blast_radius <= TIER_THRESHOLDS["tier2_max_blast_radius"]
    ):
        return "tier2_balanced"
    if overall > TIER_THRESHOLDS["tier3_min_overall"]:
        return "tier3_risky"
    return "blocked"


def synthesize_overall(dimensions: DimensionScores) -> float:
    weights = load_weights()
    overall = (
        dimensions.cost * weights["cost"]
        + dimensions.safety * weights["safety"]
        + dimensions.effort * weights["effort"]
        + dimensions.workload * weights["workload"]
        + dimensions.business * weights["business"]
    )
    return clamp_score(overall)


def score_resource(
    *,
    resource_id: str,
    resource_name: str,
    resource_type: str,
    monthly_cost: float,
    tags: dict[str, str],
    facts: dict[str, float],
    workload: dict[str, Any],
    dependencies: dict[str, Any],
    trends: dict[str, Any],
    advisor_savings: float = 0.0,
    finding_savings: float = 0.0,
    rule_ids: set[str] | None = None,
    has_cost_advisor: bool = False,
    has_perf_advisor: bool = False,
) -> dict[str, Any]:
    """Score one resource and return a scorecard dict."""
    rule_ids = rule_ids or set()
    has_bottleneck = bool(rule_ids & _PERF_RULES)

    monthly_savings, savings_confidence = _savings_from_signals(
        monthly_cost=monthly_cost,
        advisor_savings=advisor_savings,
        finding_savings=finding_savings,
    )
    trend_penalty = float(trends.get("confidence_penalty") or 0)
    savings_confidence = clamp_score(max(0, savings_confidence - trend_penalty))

    perf_risk = _performance_risk_score(
        facts=facts,
        workload=workload,
        trends=trends,
        has_perf_advisor=has_perf_advisor,
        has_bottleneck=has_bottleneck,
    )
    blast_radius = int(dependencies.get("blast_radius") or 0)
    max_crit = dependencies.get("max_criticality") or "low"
    sla = dependencies.get("sla_tier") or sla_tier(tags)
    sla_risk_val = SLA_RISK.get(sla, 0.0)

    primary_action, action_conf = _primary_action(
        rule_ids=rule_ids,
        has_cost_advisor=has_cost_advisor,
        has_perf_advisor=has_perf_advisor,
        perf_risk=perf_risk,
        monthly_savings=monthly_savings,
    )
    if primary_action == "manual_review":
        action_conf = "Manual review"

    effort_label, effort_score, automation = _effort_dimension(resource_type, primary_action)
    business_score, business_crit = _business_dimension(tags, monthly_cost)

    dims = DimensionScores(
        cost=_cost_dimension(
            monthly_savings=monthly_savings,
            savings_confidence=savings_confidence,
            monthly_cost=monthly_cost,
            trend_penalty=trend_penalty * 0.3,
        ),
        safety=_safety_dimension(perf_risk, blast_radius, max_crit, sla_risk_val),
        effort=effort_score,
        workload=_workload_dimension(workload),
        business=business_score,
        performance_risk=perf_risk,
    )
    dims.overall = synthesize_overall(dims)

    tier = assign_recommendation_tier(
        overall=dims.overall,
        perf_risk=perf_risk,
        blast_radius=blast_radius,
        compliance_locked=is_compliance_locked(tags),
        sla=sla,
        monthly_savings=monthly_savings,
    )

    payback = None
    if monthly_savings > 0:
        effort_months = {"trivial": 0.1, "simple": 0.25, "medium": 1.0, "complex": 3.0}.get(effort_label, 1.0)
        payback = max(1, int(round(effort_months)))

    seasonal_impact = 15.0 if workload.get("detected_seasonality") else 0.0

    return {
        "resource_id": resource_id,
        "resource_name": resource_name,
        "resource_type": resource_type,
        "cost_savings_monthly": monthly_savings,
        "cost_savings_confidence": savings_confidence,
        "cost_payback_months": payback,
        "performance_risk_score": perf_risk,
        "dependency_blast_radius": blast_radius,
        "dependency_criticality_max": max_crit,
        "sla_constraint_risk": sla_risk_val,
        "implementation_effort": effort_label,
        "automation_available": automation,
        "workload_stability_score": dims.workload,
        "seasonal_impact_on_recommendation": seasonal_impact,
        "business_priority_score": dims.business,
        "business_criticality": business_crit,
        "cost_dimension_score": dims.cost,
        "safety_dimension_score": dims.safety,
        "effort_dimension_score": dims.effort,
        "workload_dimension_score": dims.workload,
        "business_dimension_score": dims.business,
        "overall_recommendation_score": dims.overall,
        "recommendation_tier": tier,
        "primary_action": primary_action,
        "action_confidence": action_conf,
        "scoring_evidence": {
            "rule_ids": sorted(rule_ids),
            "has_cost_advisor": has_cost_advisor,
            "has_perf_advisor": has_perf_advisor,
            "sla_tier": sla,
            "workload_type": workload.get("workload_type"),
            "weights": load_weights(),
        },
    }

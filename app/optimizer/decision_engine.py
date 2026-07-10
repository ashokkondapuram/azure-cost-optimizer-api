"""Synthesize optimization actions using the advanced multi-signal scoring engine."""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.metrics_loader import load_cached_resource_facts
from app.models import (
    AdvisorRecommendation,
    OptimizationAction,
    OptimizationFinding,
    ResourceSnapshot,
    WorkloadProfile,
)
from app.optimizer.advanced_engine import score_resource
from app.optimizer.dependency_analyzer import analyze_dependencies, enrich_dependency_criticality
from app.optimizer.trend_analyzer import analyze_resource_trends
from app.optimizer.workload_profiler import profile_resource
from app.savings_aggregation import resolve_resource_savings
from app.utils import json_field, norm_arm_id, parse_tags_json, utc_now

log = structlog.get_logger()

_ACTION_REASONS: dict[str, str] = {
    "resize_down": "Right-size underutilized compute based on utilization, cost, and workload stability",
    "downgrade_disk": "Reduce disk tier or size — cost outweighs performance headroom",
    "decommission": "Remove idle or unused resources to eliminate recurring charges",
    "buy_reservation": "Stable workload qualifies for reservation or savings plan",
    "investigate": "Review cost and utilization signals before changing this resource",
    "manual_review": "Savings opportunity conflicts with performance, SLA, or dependency risk",
    "keep": "No actionable optimization at this time",
}


def _parse_json_blob(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _finding_evidence(finding: OptimizationFinding) -> dict[str, Any]:
    return _parse_json_blob(finding.evidence_json, {})


def _workload_dict(profile: WorkloadProfile | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if profile:
        return {
            "workload_type": profile.workload_type,
            "burstiness_score": profile.burstiness_score,
            "peak_hour_factor": profile.peak_hour_factor,
            "utilization_trend": profile.utilization_trend,
            "utilization_variance_7d": profile.utilization_variance_7d,
            "utilization_variance_30d": profile.utilization_variance_30d,
            "utilization_coefficient_variance": profile.utilization_coefficient_variance,
            "detected_seasonality": bool(profile.detected_seasonality),
            "seasonal_peak_percentage": profile.seasonal_peak_percentage,
            "classifier_class": profile.classifier_class,
        }
    return fallback or {}


def _merge_optimization_metrics(findings: list[OptimizationFinding]) -> dict[str, Any]:
    """Merge cost + performance metrics from engine findings into one block."""
    merged_cost: dict[str, dict[str, Any]] = {}
    merged_perf: dict[str, dict[str, Any]] = {}
    data_quality = ""
    component = ""

    for finding in findings:
        om = (_finding_evidence(finding).get("optimization_metrics") or {})
        if not data_quality and om.get("data_quality"):
            data_quality = str(om["data_quality"])
        if not component and om.get("component"):
            component = str(om["component"])
        for metric in om.get("cost") or []:
            mid = metric.get("id")
            if mid and mid not in merged_cost:
                merged_cost[mid] = metric
        for metric in om.get("performance") or []:
            mid = metric.get("id")
            if mid and mid not in merged_perf:
                merged_perf[mid] = metric

    cost = list(merged_cost.values())
    performance = list(merged_perf.values())
    if not cost and not performance:
        return {}

    return {
        "cost": cost,
        "performance": performance,
        "data_quality": data_quality,
        "component": component,
        "display_mode": "action_analysis",
    }


def _facts_from_findings(findings: list[OptimizationFinding]) -> dict[str, float]:
    facts: dict[str, float] = {}
    for finding in findings:
        ev = _finding_evidence(finding)
        for key, val in ev.items():
            if isinstance(val, (int, float)) and key not in facts:
                facts[key] = float(val)
        for key, val in (ev.get("resource_details") or {}).items():
            if isinstance(val, (int, float)) and key not in facts:
                facts[key] = float(val)
    return facts


def _perf_risk_label(score: float) -> str:
    if score >= 50:
        return "High"
    if score >= 25:
        return "Medium"
    return "Low"


def _synthesize_action_reason(
    *,
    scorecard: dict[str, Any],
    findings: list[OptimizationFinding],
    workload: dict[str, Any],
) -> str:
    action = scorecard.get("primary_action") or "investigate"
    base = _ACTION_REASONS.get(action, "Review optimization signals for this resource")

    finding_names = [f.rule_name for f in findings if f.rule_name][:2]
    if finding_names:
        base = f"{base} — triggered by {', '.join(finding_names)}"

    wtype = workload.get("workload_type")
    if wtype and action in {"resize_down", "buy_reservation"}:
        base = f"{base} ({wtype} workload)"

    tier = scorecard.get("recommendation_tier")
    if tier == "tier3_risky" and action != "manual_review":
        base = f"{base}. Higher risk — validate in non-production first"

    return base


def _build_combined_evidence(
    *,
    cost_advisor: list[AdvisorRecommendation],
    perf_advisor: list[AdvisorRecommendation],
    findings: list[OptimizationFinding],
    optimization_metrics: dict[str, Any],
    advisor_savings: float,
    finding_savings: float,
    facts: dict[str, float],
    savings_breakdown: Any | None = None,
) -> dict[str, Any]:
    """Compact summary of merged advisor, engine findings, and monitor metrics."""
    cost_metric_count = len(optimization_metrics.get("cost") or [])
    perf_metric_count = len(optimization_metrics.get("performance") or [])
    monitor_fact_count = sum(
        1 for key in facts
        if key.endswith("_pct") or "cpu" in key or "mem" in key or "disk" in key
    )

    unified = None
    if savings_breakdown is not None:
        unified = savings_breakdown.unified_monthly

    return {
        "advisor_count": len(cost_advisor) + len(perf_advisor),
        "cost_advisor_count": len(cost_advisor),
        "performance_advisor_count": len(perf_advisor),
        "findings_count": len(findings),
        "metrics_count": cost_metric_count + perf_metric_count,
        "cost_metrics_count": cost_metric_count,
        "performance_metrics_count": perf_metric_count,
        "monitor_fact_count": monitor_fact_count,
        "has_advisor": bool(cost_advisor or perf_advisor),
        "has_findings": bool(findings),
        "has_metrics": (cost_metric_count + perf_metric_count) > 0 or monitor_fact_count > 0,
        "advisor_monthly_savings": round(advisor_savings, 2) if advisor_savings is not None and advisor_savings > 0 else None,
        "finding_monthly_savings": round(finding_savings, 2) if finding_savings is not None and finding_savings > 0 else None,
        "unified_monthly_savings": round(unified, 2) if unified is not None and unified > 0 else (
            round(finding_savings, 2) if finding_savings and finding_savings > 0 else None
        ),
        "savings_by_action_class": getattr(savings_breakdown, "by_action_class", None),
        "overlap_action_classes": getattr(savings_breakdown, "overlap_action_classes", None),
        "sources_merged": True,
    }


def _build_analysis_payload(
    *,
    scorecard: dict[str, Any],
    snapshot: ResourceSnapshot | None,
    findings: list[OptimizationFinding],
    optimization_metrics: dict[str, Any],
    workload: dict[str, Any],
    dependencies: dict[str, Any],
    combined_evidence: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Return cost_evidence, utilization_evidence, decision_rules_applied."""
    monthly_cost = float(snapshot.monthly_cost_usd or 0) if snapshot else 0.0
    if monthly_cost <= 0:
        for finding in findings:
            ev = _finding_evidence(finding)
            candidate = ev.get("monthly_cost_usd") or ev.get("monthly_cost")
            if candidate:
                try:
                    monthly_cost = float(candidate)
                    break
                except (TypeError, ValueError):
                    continue

    cost_evidence = {
        "current_monthly_cost": monthly_cost or None,
        "estimated_monthly_savings": scorecard.get("cost_savings_monthly"),
        "savings_confidence": scorecard.get("cost_savings_confidence"),
        "payback_months": scorecard.get("cost_payback_months"),
        "overall_score": scorecard.get("overall_recommendation_score"),
        "recommendation_tier": scorecard.get("recommendation_tier"),
        "cost_dimension_score": scorecard.get("cost_dimension_score"),
        "business_criticality": scorecard.get("business_criticality"),
        "implementation_effort": scorecard.get("implementation_effort"),
        "automation_available": scorecard.get("automation_available"),
        "signal_count": len(findings),
        "combined_evidence": combined_evidence,
    }

    utilization_evidence = {
        "optimization_metrics": optimization_metrics,
        "workload": {
            k: workload.get(k)
            for k in (
                "workload_type",
                "utilization_trend",
                "burstiness_score",
                "detected_seasonality",
                "classifier_class",
            )
            if workload.get(k) is not None
        },
        "performance_risk_score": scorecard.get("performance_risk_score"),
        "dependency_blast_radius": scorecard.get("dependency_blast_radius"),
        "dependency_criticality_max": scorecard.get("dependency_criticality_max"),
        "sla_constraint_risk": scorecard.get("sla_constraint_risk"),
        "workload_stability_score": scorecard.get("workload_stability_score"),
        "seasonal_impact": scorecard.get("seasonal_impact_on_recommendation"),
        "dimensions": {
            "cost": scorecard.get("cost_dimension_score"),
            "safety": scorecard.get("safety_dimension_score"),
            "effort": scorecard.get("effort_dimension_score"),
            "workload": scorecard.get("workload_dimension_score"),
            "business": scorecard.get("business_dimension_score"),
        },
        "triggering_rules": sorted({f.rule_id for f in findings if f.rule_id}),
        "dependencies": {
            "blast_radius": dependencies.get("blast_radius"),
            "max_criticality": dependencies.get("max_criticality"),
            "sla_tier": dependencies.get("sla_tier"),
        },
    }

    rules_applied = list(utilization_evidence["triggering_rules"])
    scoring_evidence = scorecard.get("scoring_evidence") or {}
    if scoring_evidence.get("has_cost_advisor"):
        rules_applied.append("signal:cost")
    if scoring_evidence.get("has_perf_advisor"):
        rules_applied.append("signal:performance")
    tier = scorecard.get("recommendation_tier")
    if tier:
        rules_applied.append(f"tier:{tier}")

    return cost_evidence, utilization_evidence, rules_applied


def _decide_for_resource(
    *,
    resource_id: str,
    advisor_rows: list[AdvisorRecommendation],
    findings: list[OptimizationFinding],
    snapshot: ResourceSnapshot | None,
    facts: dict[str, float],
    workload: dict[str, Any],
    dependencies: dict[str, Any],
    trends: dict[str, Any],
) -> dict[str, Any] | None:
    open_findings = [f for f in findings if (f.status or "open").lower() in {"open", "acknowledged"}]
    if not advisor_rows and not open_findings:
        return None

    cost_advisor = [a for a in advisor_rows if (a.category or "").lower() == "cost" and a.status == "Active"]
    perf_advisor = [
        a for a in advisor_rows
        if (a.category or "").lower() in {"performance", "highavailability"} and a.status == "Active"
    ]

    advisor_savings = sum(a.potential_savings_monthly or 0.0 for a in cost_advisor)
    finding_savings = sum(f.estimated_savings_usd or 0.0 for f in open_findings)
    savings_breakdown = resolve_resource_savings(
        resource_id=resource_id,
        advisor_recs=cost_advisor,
        findings=open_findings,
    )
    unified_savings = savings_breakdown.unified_monthly
    rule_ids = {f.rule_id for f in open_findings if f.rule_id}

    monthly_cost = float(snapshot.monthly_cost_usd or 0) if snapshot else 0.0
    tags = parse_tags_json(snapshot.tags_json) if snapshot else {}
    merged_facts = {**_facts_from_findings(open_findings), **facts}

    scorecard = score_resource(
        resource_id=resource_id,
        resource_name=(
            (snapshot.resource_name if snapshot else None)
            or (open_findings[0].resource_name if open_findings else None)
            or resource_id.rsplit("/", 1)[-1]
        ),
        resource_type=(
            (snapshot.resource_type if snapshot else None)
            or (open_findings[0].resource_type if open_findings else None)
            or "unknown"
        ),
        monthly_cost=monthly_cost,
        tags=tags,
        facts=merged_facts,
        workload=workload,
        dependencies=dependencies,
        trends=trends,
        advisor_savings=advisor_savings,
        finding_savings=finding_savings,
        unified_monthly_savings=unified_savings,
        rule_ids=rule_ids,
        has_cost_advisor=bool(cost_advisor),
        has_perf_advisor=bool(perf_advisor),
    )

    primary_action = scorecard.get("primary_action") or "investigate"
    tier = scorecard.get("recommendation_tier") or "blocked"

    if primary_action == "keep":
        return None
    if tier == "blocked" and not open_findings and not cost_advisor:
        return None

    optimization_metrics = _merge_optimization_metrics(open_findings)
    combined_evidence = _build_combined_evidence(
        cost_advisor=cost_advisor,
        perf_advisor=perf_advisor,
        findings=open_findings,
        optimization_metrics=optimization_metrics,
        advisor_savings=advisor_savings,
        finding_savings=finding_savings,
        facts=merged_facts,
        savings_breakdown=savings_breakdown,
    )
    cost_evidence, utilization_evidence, rules_applied = _build_analysis_payload(
        scorecard=scorecard,
        snapshot=snapshot,
        findings=open_findings,
        optimization_metrics=optimization_metrics,
        workload=workload,
        dependencies=dependencies,
        combined_evidence=combined_evidence,
    )

    action_reason = _synthesize_action_reason(
        scorecard=scorecard,
        findings=open_findings,
        workload=workload,
    )

    return {
        "resource_id": resource_id,
        "resource_type": scorecard["resource_type"],
        "resource_name": scorecard["resource_name"],
        "action_type": primary_action,
        "action_reason": action_reason,
        "confidence": scorecard.get("action_confidence") or "Medium",
        "performance_risk": _perf_risk_label(float(scorecard.get("performance_risk_score") or 0)),
        "estimated_monthly_savings": scorecard.get("cost_savings_monthly"),
        "recommendation_tier": tier,
        "overall_score": scorecard.get("overall_recommendation_score"),
        "advisor_finding": {},
        "cost_evidence": cost_evidence,
        "utilization_evidence": utilization_evidence,
        "decision_rules_applied": rules_applied,
        "advisor_recommendation_id": cost_advisor[0].id if cost_advisor else None,
    }


def generate_optimization_actions(
    db: Session,
    subscription_id: str,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Build or refresh optimization_actions for a subscription using advanced analysis."""
    sub = subscription_id.strip().lower()

    enrich_dependency_criticality(db, sub)

    advisor_rows = (
        db.query(AdvisorRecommendation)
        .filter(
            AdvisorRecommendation.subscription_id == sub,
            AdvisorRecommendation.status == "Active",
        )
        .all()
    )
    open_findings = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status.in_(["open", "acknowledged"]),
        )
        .all()
    )

    advisor_by_resource: dict[str, list[AdvisorRecommendation]] = defaultdict(list)
    for row in advisor_rows:
        rid = norm_arm_id(row.resource_id)
        if rid:
            advisor_by_resource[rid].append(row)

    findings_by_resource: dict[str, list[OptimizationFinding]] = defaultdict(list)
    resource_ids: set[str] = set(advisor_by_resource.keys())
    for finding in open_findings:
        rid = norm_arm_id(finding.resource_id)
        if rid:
            findings_by_resource[rid].append(finding)
            resource_ids.add(rid)

    snapshots = {
        norm_arm_id(s.resource_id): s
        for s in db.query(ResourceSnapshot).filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
        ).all()
        if norm_arm_id(s.resource_id)
    }

    profiles = {
        norm_arm_id(p.resource_id): p
        for p in db.query(WorkloadProfile).filter(WorkloadProfile.subscription_id == sub).all()
        if norm_arm_id(p.resource_id)
    }

    facts_map = load_cached_resource_facts(db, sub)

    created = 0
    updated = 0
    skipped = 0
    by_type: dict[str, int] = defaultdict(int)

    existing_actions = {
        norm_arm_id(row.resource_id): row
        for row in db.query(OptimizationAction)
        .filter(OptimizationAction.subscription_id == sub)
        .all()
        if norm_arm_id(row.resource_id)
    }

    for rid in sorted(resource_ids):
        snap = snapshots.get(rid)
        profile = profiles.get(rid)
        workload_fallback = profile_resource(db, snap, facts_map.get(rid) or {}) if snap and not profile else None
        workload = _workload_dict(profile, workload_fallback)
        dependencies = analyze_dependencies(db, sub, rid, snapshots_by_id=snapshots)
        trends = analyze_resource_trends(db, sub, rid)

        decision = _decide_for_resource(
            resource_id=rid,
            advisor_rows=advisor_by_resource.get(rid, []),
            findings=findings_by_resource.get(rid, []),
            snapshot=snap,
            facts=facts_map.get(rid) or {},
            workload=workload,
            dependencies=dependencies,
            trends=trends,
        )
        if not decision:
            skipped += 1
            continue

        existing = existing_actions.get(rid)

        payload = {
            "resource_type": decision["resource_type"],
            "resource_name": decision["resource_name"],
            "action_type": decision["action_type"],
            "action_reason": decision["action_reason"],
            "confidence": decision["confidence"],
            "performance_risk": decision["performance_risk"],
            "estimated_monthly_savings": decision["estimated_monthly_savings"],
            "recommendation_tier": decision["recommendation_tier"],
            "overall_score": decision["overall_score"],
            "advisor_finding": json_field(decision["advisor_finding"] or {}, default="{}"),
            "cost_evidence": json_field(decision["cost_evidence"], default="{}"),
            "utilization_evidence": json_field(decision["utilization_evidence"], default="{}"),
            "decision_rules_applied": json_field(decision["decision_rules_applied"], default="[]"),
            "updated_at": utc_now(),
        }

        if existing:
            if existing.workflow_status in {"approved", "executed", "rejected", "deferred"} and not force_refresh:
                skipped += 1
                continue
            for key, value in payload.items():
                setattr(existing, key, value)
            if existing.workflow_status == "rejected" and force_refresh:
                existing.workflow_status = "proposed"
            updated += 1
            action_row = existing
        else:
            action_row = OptimizationAction(
                id=str(uuid.uuid4()),
                subscription_id=sub,
                resource_id=rid,
                workflow_status="proposed",
                workflow_history_json="[]",
                **payload,
            )
            db.add(action_row)
            created += 1

        by_type[decision["action_type"]] += 1

        advisor_rec_id = decision.get("advisor_recommendation_id")
        if advisor_rec_id:
            for finding in findings_by_resource.get(rid, []):
                finding.advisor_recommendation_id = advisor_rec_id
                finding.linked_action_id = action_row.id

    db.commit()
    log.info(
        "decision_engine.done",
        subscription_id=sub,
        created=created,
        updated=updated,
        skipped=skipped,
    )
    return {
        "status": "ok",
        "subscription_id": sub,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "by_action_type": dict(by_type),
        "total_actions": created + updated,
    }

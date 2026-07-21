"""Deep-dive advanced engine analysis for a single resource."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.advanced_analysis_insights import build_advanced_insights
from app.advanced_scoring import serialize_scorecard
from app.finding_quality import filter_valuable_findings, serialize_finding_summary
from app.metrics_loader import load_cached_resource_facts
from app.models import OptimizationAction, OptimizationFinding, OptimizationScoring, ResourceSnapshot, WorkloadProfile
from app.optimizer.dependency_analyzer import analyze_dependencies
from app.optimizer.trend_analyzer import analyze_resource_trends
from app.optimizer.workload_profiler import profile_resource


def _norm_rid(value: str | None) -> str:
    return (value or "").strip().lower()


def _today() -> str:
    return date.today().isoformat()


_UTILIZATION_FACT_KEYS: dict[str, tuple[str, ...]] = {
    "compute/vm": ("avg_cpu_pct", "max_cpu_pct", "avg_memory_pct", "max_memory_pct"),
    "compute/vmss": ("avg_cpu_pct", "max_cpu_pct", "avg_memory_pct", "max_memory_pct"),
    "compute/disk": (
        "disk_iops_utilization_pct",
        "disk_throughput_utilization_pct",
        "disk_queue_depth",
        "disk_read_bps",
        "disk_write_bps",
    ),
    "database/redis": ("usedmemorypercentage", "serverload", "operationsPerSecond", "cachehitrate"),
    "storage/account": ("storage_pct", "used_capacity_bytes"),
    "containers/aks": ("avg_cpu_pct", "max_cpu_pct", "avg_memory_pct", "max_memory_pct"),
}


def _utilization_evidence_from_facts(facts: dict[str, Any], canonical_type: str) -> dict[str, Any]:
    ctype = (canonical_type or "").strip().lower()
    keys = _UTILIZATION_FACT_KEYS.get(ctype, _UTILIZATION_FACT_KEYS["compute/vm"])
    evidence: dict[str, Any] = {}
    for key in keys:
        val = facts.get(key)
        if val is not None:
            evidence[key] = val
    evidence["has_monitor_data"] = any(
        facts.get(k) is not None for k in keys
    )
    return evidence


def get_resource_advanced_analysis(
    db: Session,
    subscription_id: str,
    resource_id: str,
    *,
    profile: str = "full",
) -> dict[str, Any]:
    sub = subscription_id.strip().lower()
    rid = _norm_rid(resource_id)
    response_profile = (profile or "full").strip().lower()
    slim = response_profile == "drawer"

    snap = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.resource_id == rid,
        )
        .first()
    )

    workload_row = (
        db.query(WorkloadProfile)
        .filter(
            WorkloadProfile.subscription_id == sub,
            WorkloadProfile.resource_id == rid,
        )
        .first()
    )

    scoring = None
    if not slim:
        scoring = (
            db.query(OptimizationScoring)
            .filter(
                OptimizationScoring.subscription_id == sub,
                OptimizationScoring.resource_id == rid,
                OptimizationScoring.evaluation_date == _today(),
            )
            .first()
        )
        if not scoring:
            scoring = (
                db.query(OptimizationScoring)
                .filter(
                    OptimizationScoring.subscription_id == sub,
                    OptimizationScoring.resource_id == rid,
                )
                .order_by(OptimizationScoring.evaluation_date.desc())
                .first()
            )

    action = None
    if not slim:
        action = (
            db.query(OptimizationAction)
            .filter(
                OptimizationAction.subscription_id == sub,
                OptimizationAction.resource_id == rid,
            )
            .first()
        )

    open_findings = []
    if not slim:
        open_findings = (
            db.query(OptimizationFinding)
            .filter(
                OptimizationFinding.subscription_id == sub,
                OptimizationFinding.resource_id == rid,
                OptimizationFinding.status.in_(["open", "acknowledged"]),
            )
            .all()
        )
    actionable_findings = []
    if not slim:
        actionable_findings = [
            serialize_finding_summary(f)
            for f in filter_valuable_findings(open_findings, limit=5)
        ]

    dependencies = analyze_dependencies(db, sub, rid)
    trends = analyze_resource_trends(db, sub, rid)
    facts_map = load_cached_resource_facts(db, sub)
    facts = facts_map.get(rid) or {}
    canonical_type = (snap.resource_type if snap else None) or ""
    utilization_evidence = _utilization_evidence_from_facts(facts, canonical_type)

    workload = None
    if workload_row:
        workload = {
            "workload_type": workload_row.workload_type,
            "burstiness_score": workload_row.burstiness_score,
            "peak_hour_factor": workload_row.peak_hour_factor,
            "utilization_trend": workload_row.utilization_trend,
            "utilization_variance_30d": workload_row.utilization_variance_30d,
            "detected_seasonality": bool(workload_row.detected_seasonality),
            "seasonal_peak_percentage": workload_row.seasonal_peak_percentage,
            "classifier_class": workload_row.classifier_class,
            "synced_at": workload_row.synced_at.isoformat() if workload_row.synced_at else None,
        }
    elif snap:
        fields = profile_resource(db, snap, facts)
        workload = {
            "workload_type": fields.get("workload_type"),
            "burstiness_score": fields.get("burstiness_score"),
            "peak_hour_factor": fields.get("peak_hour_factor"),
            "utilization_trend": fields.get("utilization_trend"),
            "utilization_variance_30d": fields.get("utilization_variance_30d"),
            "detected_seasonality": bool(fields.get("detected_seasonality")),
            "seasonal_peak_percentage": fields.get("seasonal_peak_percentage"),
            "classifier_class": fields.get("classifier_class"),
            "synced_at": None,
            "computed_on_demand": True,
        }

    insights = build_advanced_insights(
        workload=workload,
        dependencies=dependencies,
        trends=trends,
        utilization_evidence=utilization_evidence,
    )

    scorecard = serialize_scorecard(scoring, slim=slim) if scoring and not slim else None

    if slim:
        from app.drawer_payload import slim_analysis_payload

        return slim_analysis_payload({
            "insights": insights,
            "trends": trends,
        })

    return {
        "subscription_id": sub,
        "resource_id": rid,
        "resource_name": snap.resource_name if snap else None,
        "resource_type": snap.resource_type if snap else None,
        "monthly_cost_usd": float(snap.monthly_cost_billing or snap.monthly_cost_usd or 0) if snap else None,
        "workload_profile": workload,
        "utilization_evidence": utilization_evidence,
        "insights": insights,
        "scorecard": scorecard,
        "dependencies": dependencies,
        "trends": trends,
        "optimization_action": {
            "id": action.id,
            "action_type": action.action_type,
            "workflow_status": action.workflow_status,
            "recommendation_tier": action.recommendation_tier,
            "overall_score": action.overall_score,
            "estimated_monthly_savings": action.estimated_monthly_savings,
        } if action else None,
        "actionable_findings": actionable_findings,
        "mode": "advisory",
    }

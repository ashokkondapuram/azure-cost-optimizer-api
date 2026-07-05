"""Deep-dive advanced engine analysis for a single resource."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

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


def get_resource_advanced_analysis(
    db: Session,
    subscription_id: str,
    resource_id: str,
) -> dict[str, Any]:
    sub = subscription_id.strip().lower()
    rid = _norm_rid(resource_id)

    snap = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.resource_id == rid,
        )
        .first()
    )

    profile = (
        db.query(WorkloadProfile)
        .filter(
            WorkloadProfile.subscription_id == sub,
            WorkloadProfile.resource_id == rid,
        )
        .first()
    )

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

    action = (
        db.query(OptimizationAction)
        .filter(
            OptimizationAction.subscription_id == sub,
            OptimizationAction.resource_id == rid,
        )
        .first()
    )

    open_findings = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.resource_id == rid,
            OptimizationFinding.status.in_(["open", "acknowledged"]),
        )
        .all()
    )
    actionable_findings = [
        serialize_finding_summary(f)
        for f in filter_valuable_findings(open_findings, limit=5)
    ]

    dependencies = analyze_dependencies(db, sub, rid)
    trends = analyze_resource_trends(db, sub, rid)

    workload = None
    if profile:
        workload = {
            "workload_type": profile.workload_type,
            "burstiness_score": profile.burstiness_score,
            "peak_hour_factor": profile.peak_hour_factor,
            "utilization_trend": profile.utilization_trend,
            "utilization_variance_30d": profile.utilization_variance_30d,
            "detected_seasonality": bool(profile.detected_seasonality),
            "seasonal_peak_percentage": profile.seasonal_peak_percentage,
            "classifier_class": profile.classifier_class,
            "synced_at": profile.synced_at.isoformat() if profile.synced_at else None,
        }
    elif snap:
        facts_map = load_cached_resource_facts(db, sub)
        fields = profile_resource(db, snap, facts_map.get(rid) or {})
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

    return {
        "subscription_id": sub,
        "resource_id": rid,
        "resource_name": snap.resource_name if snap else None,
        "resource_type": snap.resource_type if snap else None,
        "monthly_cost_usd": float(snap.monthly_cost_usd or 0) if snap else None,
        "workload_profile": workload,
        "scorecard": serialize_scorecard(scoring) if scoring else None,
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

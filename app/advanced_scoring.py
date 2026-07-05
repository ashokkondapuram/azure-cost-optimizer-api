"""Orchestrate profiling, scoring, and persistence for the advanced engine."""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.finding_quality import is_valuable_finding
from app.metrics_loader import load_cached_resource_facts
from app.models import (
    AdvisorRecommendation,
    OptimizationAction,
    OptimizationFinding,
    OptimizationScoring,
    ResourceSnapshot,
    WorkloadProfile,
)
from app.optimizer.advanced_engine import score_resource
from app.optimizer.dependency_analyzer import analyze_dependencies, enrich_dependency_criticality
from app.optimizer.trend_analyzer import analyze_resource_trends
from app.optimizer.workload_profiler import profile_resource, upsert_workload_profiles
from app.utils import norm_arm_id, parse_tags_json, today_iso, utc_now

log = structlog.get_logger()


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


def _index_advisor(db: Session, sub: str) -> dict[str, list[AdvisorRecommendation]]:
    rows = (
        db.query(AdvisorRecommendation)
        .filter(
            AdvisorRecommendation.subscription_id == sub,
            AdvisorRecommendation.status == "Active",
        )
        .all()
    )
    out: dict[str, list[AdvisorRecommendation]] = defaultdict(list)
    for row in rows:
        rid = norm_arm_id(row.resource_id)
        if rid:
            out[rid].append(row)
    return out


def _index_findings(db: Session, sub: str) -> dict[str, list[OptimizationFinding]]:
    rows = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status.in_(["open", "acknowledged"]),
        )
        .all()
    )
    out: dict[str, list[OptimizationFinding]] = defaultdict(list)
    for row in rows:
        rid = norm_arm_id(row.resource_id)
        if rid:
            out[rid].append(row)
    return out


def score_subscription(
    db: Session,
    subscription_id: str,
    *,
    force_rescore: bool = False,
) -> dict[str, Any]:
    """Profile workloads, score resources, persist optimization_scoring rows."""
    sub = subscription_id.strip().lower()
    eval_date = today_iso()

    profile_counts = upsert_workload_profiles(db, sub)
    enrich_dependency_criticality(db, sub)

    facts_map = load_cached_resource_facts(db, sub)
    snapshots = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
        )
        .all()
    )
    snapshots_by_id = {norm_arm_id(s.resource_id): s for s in snapshots}

    profiles = {
        norm_arm_id(p.resource_id): p
        for p in db.query(WorkloadProfile).filter(WorkloadProfile.subscription_id == sub).all()
    }
    advisor_by_rid = _index_advisor(db, sub)
    findings_by_rid = _index_findings(db, sub)

    created = 0
    updated = 0
    skipped = 0
    tier_counts: dict[str, int] = defaultdict(int)

    for snap in snapshots:
        rid = norm_arm_id(snap.resource_id)
        if not rid:
            continue

        advisor_rows = advisor_by_rid.get(rid, [])
        finding_rows = findings_by_rid.get(rid, [])

        cost_advisor = [a for a in advisor_rows if (a.category or "").lower() == "cost"]
        perf_advisor = [a for a in advisor_rows if (a.category or "").lower() in {"performance", "highavailability"}]
        valuable_findings = [f for f in finding_rows if is_valuable_finding(f)]
        advisor_savings = sum(a.potential_savings_monthly or 0 for a in cost_advisor)
        finding_savings = sum(f.estimated_savings_usd or 0 for f in valuable_findings)
        rule_ids = {f.rule_id for f in valuable_findings if f.rule_id}

        profile = profiles.get(rid)
        workload_fallback = profile_resource(db, snap, facts_map.get(rid) or {}) if not profile else None
        workload = _workload_dict(profile, workload_fallback)
        deps = analyze_dependencies(db, sub, rid, snapshots_by_id=snapshots_by_id)
        trends = analyze_resource_trends(db, sub, rid)
        tags = parse_tags_json(snap.tags_json)

        scorecard = score_resource(
            resource_id=rid,
            resource_name=snap.resource_name,
            resource_type=snap.resource_type or "unknown",
            monthly_cost=float(snap.monthly_cost_usd or 0),
            tags=tags,
            facts=facts_map.get(rid) or {},
            workload=workload,
            dependencies=deps,
            trends=trends,
            advisor_savings=advisor_savings,
            finding_savings=finding_savings,
            rule_ids=rule_ids,
            has_cost_advisor=bool(cost_advisor),
            has_perf_advisor=bool(perf_advisor),
        )

        tier_counts[scorecard["recommendation_tier"]] += 1

        existing = (
            db.query(OptimizationScoring)
            .filter(
                OptimizationScoring.subscription_id == sub,
                OptimizationScoring.resource_id == rid,
                OptimizationScoring.evaluation_date == eval_date,
            )
            .first()
        )

        payload = {
            "resource_name": snap.resource_name,
            "resource_type": snap.resource_type,
            "cost_savings_monthly": scorecard["cost_savings_monthly"],
            "cost_savings_confidence": scorecard["cost_savings_confidence"],
            "cost_payback_months": scorecard["cost_payback_months"],
            "performance_risk_score": scorecard["performance_risk_score"],
            "dependency_blast_radius": scorecard["dependency_blast_radius"],
            "dependency_criticality_max": scorecard["dependency_criticality_max"],
            "sla_constraint_risk": scorecard["sla_constraint_risk"],
            "implementation_effort": scorecard["implementation_effort"],
            "automation_available": scorecard["automation_available"],
            "workload_stability_score": scorecard["workload_stability_score"],
            "seasonal_impact_on_recommendation": scorecard["seasonal_impact_on_recommendation"],
            "business_priority_score": scorecard["business_priority_score"],
            "business_criticality": scorecard["business_criticality"],
            "cost_dimension_score": scorecard["cost_dimension_score"],
            "safety_dimension_score": scorecard["safety_dimension_score"],
            "effort_dimension_score": scorecard["effort_dimension_score"],
            "workload_dimension_score": scorecard["workload_dimension_score"],
            "business_dimension_score": scorecard["business_dimension_score"],
            "overall_recommendation_score": scorecard["overall_recommendation_score"],
            "recommendation_tier": scorecard["recommendation_tier"],
            "primary_action": scorecard["primary_action"],
            "action_confidence": scorecard["action_confidence"],
            "scoring_evidence_json": scorecard["scoring_evidence"],
            "synced_at": utc_now(),
        }

        if existing:
            if not force_rescore and existing.recommendation_tier == "blocked":
                skipped += 1
                continue
            for key, value in payload.items():
                setattr(existing, key, value)
            updated += 1
        else:
            db.add(OptimizationScoring(
                id=str(uuid.uuid4()),
                subscription_id=sub,
                resource_id=rid,
                evaluation_date=eval_date,
                **payload,
            ))
            created += 1

        action = (
            db.query(OptimizationAction)
            .filter(
                OptimizationAction.subscription_id == sub,
                OptimizationAction.resource_id == rid,
            )
            .first()
        )
        if action and action.workflow_status == "proposed":
            action.recommendation_tier = scorecard["recommendation_tier"]
            action.overall_score = scorecard["overall_recommendation_score"]

    db.commit()
    result = {
        "status": "ok",
        "subscription_id": sub,
        "evaluation_date": eval_date,
        "profiles": profile_counts,
        "scoring": {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "total": created + updated,
            "by_tier": dict(tier_counts),
        },
        "mode": "advisory",
    }
    log.info("advanced_engine.score_done", subscription_id=sub, **result["scoring"])
    return result


def serialize_scorecard(row: OptimizationScoring) -> dict[str, Any]:
    evidence = row.scoring_evidence_json
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except json.JSONDecodeError:
            evidence = {}
    return {
        "id": row.id,
        "resource_id": row.resource_id,
        "resource_name": row.resource_name,
        "resource_type": row.resource_type,
        "subscription_id": row.subscription_id,
        "evaluation_date": row.evaluation_date,
        "cost_savings_monthly": row.cost_savings_monthly,
        "cost_savings_confidence": row.cost_savings_confidence,
        "performance_risk_score": row.performance_risk_score,
        "dependency_blast_radius": row.dependency_blast_radius,
        "dependency_criticality_max": row.dependency_criticality_max,
        "implementation_effort": row.implementation_effort,
        "workload_stability_score": row.workload_stability_score,
        "business_criticality": row.business_criticality,
        "dimensions": {
            "cost": row.cost_dimension_score,
            "safety": row.safety_dimension_score,
            "effort": row.effort_dimension_score,
            "workload": row.workload_dimension_score,
            "business": row.business_dimension_score,
        },
        "overall_recommendation_score": row.overall_recommendation_score,
        "recommendation_tier": row.recommendation_tier,
        "primary_action": row.primary_action,
        "action_confidence": row.action_confidence,
        "evidence": evidence,
        "synced_at": row.synced_at.isoformat() if row.synced_at else None,
    }


def _resolve_evaluation_date(
    db: Session,
    subscription_id: str,
    evaluation_date: str | None = None,
) -> str:
    sub = subscription_id.strip().lower()
    eval_date = evaluation_date or today_iso()
    has_rows = (
        db.query(OptimizationScoring.id)
        .filter(
            OptimizationScoring.subscription_id == sub,
            OptimizationScoring.evaluation_date == eval_date,
        )
        .first()
    )
    if has_rows:
        return eval_date
    latest = (
        db.query(OptimizationScoring.evaluation_date)
        .filter(OptimizationScoring.subscription_id == sub)
        .order_by(OptimizationScoring.evaluation_date.desc())
        .first()
    )
    return latest[0] if latest else eval_date


def list_scoreboard(
    db: Session,
    subscription_id: str,
    *,
    tier: str | None = None,
    resource_type: str | None = None,
    min_score: float | None = None,
    evaluation_date: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    sub = subscription_id.strip().lower()
    eval_date = _resolve_evaluation_date(db, sub, evaluation_date)

    q = db.query(OptimizationScoring).filter(
        OptimizationScoring.subscription_id == sub,
        OptimizationScoring.evaluation_date == eval_date,
    )
    if tier:
        q = q.filter(OptimizationScoring.recommendation_tier == tier.strip().lower())
    if resource_type:
        q = q.filter(OptimizationScoring.resource_type == resource_type)
    if min_score is not None:
        q = q.filter(OptimizationScoring.overall_recommendation_score >= min_score)

    total = q.count()
    rows = (
        q.order_by(
            OptimizationScoring.overall_recommendation_score.desc(),
            OptimizationScoring.cost_savings_monthly.desc(),
        )
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
        .all()
    )

    tier_summary: dict[str, int] = defaultdict(int)
    for row in db.query(OptimizationScoring).filter(
        OptimizationScoring.subscription_id == sub,
        OptimizationScoring.evaluation_date == eval_date,
    ).all():
        tier_summary[row.recommendation_tier or "unknown"] += 1

    return {
        "subscription_id": sub,
        "evaluation_date": eval_date,
        "count": len(rows),
        "total": total,
        "offset": offset,
        "limit": limit,
        "tier_summary": dict(tier_summary),
        "total_estimated_monthly_savings": round(
            sum(r.cost_savings_monthly or 0 for r in rows), 2,
        ),
        "items": [serialize_scorecard(r) for r in rows],
        "mode": "advisory",
    }

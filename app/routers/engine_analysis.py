"""Engine Analysis Router

Combines Azure Advisor recommendations + Resource Analysis findings with the
Advanced Scoring engine to produce a single, enriched analysis response.

Endpoints
---------
GET  /engine/analysis/{subscription_id}/combined
     Full combined analysis: advisor + resource findings + advanced scores
GET  /engine/analysis/{subscription_id}/advisor-summary
     Advisor-only summary (cost, performance, HA, security)
GET  /engine/analysis/{subscription_id}/resource-summary
     Resource snapshot findings summary
GET  /engine/analysis/{subscription_id}/advanced-scores
     Paginated advanced scoring scoreboard
POST /engine/analysis/{subscription_id}/run
     Trigger a fresh scoring pass (advisor sync → resource analysis → advanced engine)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.user_auth import require_viewer

router = APIRouter(prefix="/engine/analysis", tags=["Engine Analysis"])


def _get_db_and_auth(db: Session = Depends(get_db), _=Depends(require_viewer)):
    return db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _advisor_summary(db: Session, sub: str) -> dict[str, Any]:
    """Return a per-category summary of active Advisor recommendations."""
    from collections import defaultdict
    from app.models import AdvisorRecommendation

    rows = (
        db.query(AdvisorRecommendation)
        .filter(
            AdvisorRecommendation.subscription_id == sub,
            AdvisorRecommendation.status == "Active",
        )
        .all()
    )
    by_category: dict[str, list[dict]] = defaultdict(list)
    total_savings = 0.0
    for r in rows:
        cat = (r.category or "unknown").lower()
        savings = float(r.potential_savings_monthly or 0)
        total_savings += savings
        by_category[cat].append({
            "id": r.id,
            "resource_id": r.resource_id,
            "impact": r.impact,
            "short_description": r.short_description,
            "potential_savings_monthly": savings,
            "recommendation_type": r.recommendation_type,
        })
    return {
        "total": len(rows),
        "total_potential_savings_monthly": round(total_savings, 2),
        "by_category": {
            cat: {"count": len(items), "items": items}
            for cat, items in by_category.items()
        },
    }


def _resource_findings_summary(db: Session, sub: str) -> dict[str, Any]:
    """Return open/acknowledged findings summary with top savings."""
    from collections import defaultdict
    from app.models import OptimizationFinding

    rows = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status.in_(["open", "acknowledged"]),
        )
        .all()
    )
    by_severity: dict[str, int] = defaultdict(int)
    by_rule: dict[str, int] = defaultdict(int)
    total_savings = 0.0
    for f in rows:
        by_severity[(f.severity or "unknown").lower()] += 1
        by_rule[(f.rule_id or "unknown")] += 1
        total_savings += float(f.estimated_savings_usd or 0)

    top_rules = sorted(by_rule.items(), key=lambda x: x[1], reverse=True)[:10]
    return {
        "total": len(rows),
        "total_estimated_savings_monthly": round(total_savings, 2),
        "by_severity": dict(by_severity),
        "top_rules": [{
            "rule_id": rule_id,
            "count": count
        } for rule_id, count in top_rules],
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/{subscription_id}/advisor-summary")
def advisor_summary(
    subscription_id: str,
    db: Session = Depends(_get_db_and_auth),
) -> dict[str, Any]:
    """Azure Advisor active recommendations summarised by category."""
    return _advisor_summary(db, subscription_id.strip().lower())


@router.get("/{subscription_id}/resource-summary")
def resource_summary(
    subscription_id: str,
    db: Session = Depends(_get_db_and_auth),
) -> dict[str, Any]:
    """Open resource analysis findings summarised by severity and rule."""
    return _resource_findings_summary(db, subscription_id.strip().lower())


@router.get("/{subscription_id}/advanced-scores")
def advanced_scores(
    subscription_id: str,
    tier: str | None = Query(None, description="Filter by recommendation tier"),
    resource_type: str | None = Query(None),
    min_score: float | None = Query(None),
    exclude_maintenance_hold: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(_get_db_and_auth),
) -> dict[str, Any]:
    """Paginated advanced scoring scoreboard."""
    from app.advanced_scoring import list_scoreboard
    return list_scoreboard(
        db,
        subscription_id,
        tier=tier,
        resource_type=resource_type,
        min_score=min_score,
        exclude_maintenance_hold=exclude_maintenance_hold,
        limit=limit,
        offset=offset,
    )


@router.get("/{subscription_id}/combined")
def combined_analysis(
    subscription_id: str,
    tier: str | None = Query(None),
    resource_type: str | None = Query(None),
    min_score: float | None = Query(None),
    exclude_maintenance_hold: bool = Query(True),
    top_n: int = Query(20, ge=1, le=200),
    db: Session = Depends(_get_db_and_auth),
) -> dict[str, Any]:
    """Full combined engine analysis:

    - Azure Advisor per-category summary
    - Resource findings severity/rule breakdown
    - Advanced scoring scoreboard (top N, merged with advisor savings)
    - Cross-reference: resources appearing in both advisor AND findings
    """
    from app.advanced_scoring import list_scoreboard
    from app.models import AdvisorRecommendation, OptimizationFinding
    from app.utils import norm_arm_id

    sub = subscription_id.strip().lower()

    advisor = _advisor_summary(db, sub)
    findings = _resource_findings_summary(db, sub)
    scoreboard = list_scoreboard(
        db, sub,
        tier=tier,
        resource_type=resource_type,
        min_score=min_score,
        exclude_maintenance_hold=exclude_maintenance_hold,
        limit=top_n,
    )

    # Build cross-reference index: resources with BOTH advisor and findings
    advisor_rids = {
        norm_arm_id(r.resource_id)
        for r in db.query(AdvisorRecommendation)
        .filter(
            AdvisorRecommendation.subscription_id == sub,
            AdvisorRecommendation.status == "Active",
        ).all()
        if r.resource_id
    }
    finding_rids = {
        norm_arm_id(f.resource_id)
        for f in db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status.in_(["open", "acknowledged"]),
        ).all()
        if f.resource_id
    }
    cross_ref_rids = advisor_rids & finding_rids

    # Enrich scoreboard items with advisor & finding flags
    for item in scoreboard["items"]:
        rid = norm_arm_id(item.get("resource_id") or "")
        item["has_advisor_recommendation"] = rid in advisor_rids
        item["has_open_finding"] = rid in finding_rids
        item["high_priority"] = rid in cross_ref_rids

    return {
        "subscription_id": sub,
        "advisor": advisor,
        "resource_findings": findings,
        "advanced_scoring": scoreboard,
        "cross_reference": {
            "resources_in_both_advisor_and_findings": len(cross_ref_rids),
            "resource_ids": sorted(cross_ref_rids)[:50],
        },
        "combined_estimated_monthly_savings": round(
            advisor["total_potential_savings_monthly"]
            + findings["total_estimated_savings_monthly"],
            2,
        ),
    }


@router.post("/{subscription_id}/run")
def run_engine(
    subscription_id: str,
    force_rescore: bool = Query(False),
    include_maintenance: bool = Query(True),
    sync_advisor: bool = Query(True),
    db: Session = Depends(_get_db_and_auth),
) -> dict[str, Any]:
    """Trigger a complete engine pass:
    1. Optionally sync Azure Advisor recommendations.
    2. Run advanced scoring (with maintenance awareness).
    Returns a combined status payload.
    """
    from app.advanced_scoring import score_subscription

    sub = subscription_id.strip().lower()
    steps: dict[str, Any] = {}

    if sync_advisor:
        try:
            from app.advisor_sync import sync_advisor_recommendations
            advisor_result = sync_advisor_recommendations(db, sub)
            steps["advisor_sync"] = advisor_result
        except Exception as exc:
            steps["advisor_sync"] = {"status": "error", "error": str(exc)}

    try:
        scoring_result = score_subscription(
            db, sub,
            force_rescore=force_rescore,
            include_maintenance=include_maintenance,
        )
        steps["advanced_scoring"] = scoring_result
    except Exception as exc:
        steps["advanced_scoring"] = {"status": "error", "error": str(exc)}

    return {
        "subscription_id": sub,
        "status": "ok",
        "steps": steps,
    }

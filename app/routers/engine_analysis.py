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
POST /engine/analysis/{subscription_id}/ai-recommendations
     Azure OpenAI recommendations synthesized from stored findings
POST /engine/analysis/{subscription_id}/run
     Trigger a fresh scoring pass (advisor sync → resource analysis → advanced engine)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.savings_aggregation import aggregate_subscription_savings
from app.user_auth import require_authenticated_user

router = APIRouter(prefix="/engine/analysis", tags=["Engine Analysis"])


def _auth_dep(request: Request):
    return require_authenticated_user(request)


def _get_db_and_auth(db: Session = Depends(get_db), _=Depends(_auth_dep)):
    return db


def _resolve_billing_currency(db: Session, sub: str) -> str:
    from app.models import CostByServiceSnapshot
    row = (
        db.query(CostByServiceSnapshot.billing_currency)
        .filter(CostByServiceSnapshot.subscription_id == sub)
        .first()
    )
    return (row[0] if row else None) or "CAD"


def _finding_meta_by_resource(db: Session, sub: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    from app.models import OptimizationFinding
    from app.utils import norm_arm_id

    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5}
    severity_by_rid: dict[str, str] = {}
    rules_by_rid: dict[str, list[str]] = {}
    rows = (
        db.query(OptimizationFinding.resource_id, OptimizationFinding.severity, OptimizationFinding.rule_id)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status.in_(["open", "acknowledged"]),
        )
        .all()
    )
    for rid, severity, rule_id in rows:
        norm = norm_arm_id(rid or "")
        if not norm:
            continue
        sev = (severity or "unknown").lower()
        prev = severity_by_rid.get(norm)
        if not prev or severity_rank.get(sev, 9) < severity_rank.get(prev, 9):
            severity_by_rid[norm] = sev
        if rule_id:
            rules_by_rid.setdefault(norm, [])
            if rule_id not in rules_by_rid[norm]:
                rules_by_rid[norm].append(rule_id)
    return severity_by_rid, rules_by_rid


def _enrich_scoreboard_item(
    item: dict[str, Any],
    *,
    advisor_rids: set,
    finding_rids: set,
    severity_by_rid: dict[str, str],
    rules_by_rid: dict[str, list[str]],
) -> dict[str, Any]:
    from app.utils import norm_arm_id

    rid = norm_arm_id(item.get("resource_id") or "")
    enriched = dict(item)
    enriched["composite_score"] = item.get("overall_recommendation_score")
    enriched["tier"] = item.get("recommendation_tier")
    enriched["estimated_savings_usd"] = item.get("cost_savings_monthly")
    enriched["has_advisor_recommendation"] = rid in advisor_rids
    enriched["has_open_finding"] = rid in finding_rids
    enriched["high_priority"] = rid in (advisor_rids & finding_rids)
    enriched["finding_severity"] = severity_by_rid.get(rid)
    enriched["open_finding_rules"] = rules_by_rid.get(rid, [])
    return enriched


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
            "recommendation_id": r.recommendation_id,
            "resource_id": r.resource_id,
            "impact": r.impact,
            "summary": r.summary,
            "short_description": r.summary,
            "description": r.description,
            "potential_savings_monthly": savings,
            "category": r.category,
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
    severity_by_rid, rules_by_rid = _finding_meta_by_resource(db, sub)

    for i, item in enumerate(scoreboard["items"]):
        scoreboard["items"][i] = _enrich_scoreboard_item(
            item,
            advisor_rids=advisor_rids,
            finding_rids=finding_rids,
            severity_by_rid=severity_by_rid,
            rules_by_rid=rules_by_rid,
        )

    unified = aggregate_subscription_savings(db, sub)

    return {
        "subscription_id": sub,
        "billing_currency": _resolve_billing_currency(db, sub),
        "advisor": advisor,
        "resource_findings": findings,
        "advanced_scoring": scoreboard,
        "cross_reference": {
            "resources_in_both_advisor_and_findings": len(cross_ref_rids),
            "resource_ids": sorted(cross_ref_rids)[:50],
        },
        "unified_savings": unified,
        "combined_estimated_monthly_savings": unified["unified_estimated_monthly_savings"],
    }


@router.post("/{subscription_id}/ai-recommendations")
def ai_recommendations(
    subscription_id: str,
    force_refresh: bool = Query(False, description="Bypass in-process cache and call Azure OpenAI again"),
    max_findings: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(_get_db_and_auth),
) -> dict[str, Any]:
    """Generate subscription-level recommendations via Azure OpenAI from stored findings."""
    from app.ai_subscription_recommendations import generate_subscription_ai_recommendations

    return generate_subscription_ai_recommendations(
        db,
        subscription_id.strip().lower(),
        force_refresh=force_refresh,
        max_findings=max_findings,
    )


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

    has_error = any(
        isinstance(step, dict) and step.get("status") == "error"
        for step in steps.values()
    )

    return {
        "subscription_id": sub,
        "status": "error" if has_error else "ok",
        "steps": steps,
    }

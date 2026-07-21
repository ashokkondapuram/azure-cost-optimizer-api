"""Global health score — cross-subscription aggregated health and cost dashboard."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OptimizationFinding, CostSyncRun, ResourceSnapshot

router = APIRouter(prefix="/global-health", tags=["Global Health"])

_SEVERITY_WEIGHTS = {"critical": 8, "high": 4, "medium": 2, "low": 1}


def _normalize(sub: str) -> str:
    return (sub or "").strip().lower()


def _health_score_for_sub(findings: list) -> float:
    """0–100 health score: fewer open high-severity findings = higher score."""
    open_findings = [
        f for f in findings
        if (f.status or "").lower() in ("open", "active", "")
    ]
    if not open_findings:
        return 100.0
    weight = sum(_SEVERITY_WEIGHTS.get((f.severity or "medium").lower(), 2) for f in open_findings)
    return max(0.0, round(100.0 - weight * 1.5, 1))


@router.get("/subscriptions")
def list_all_subscriptions(
    db: Session = Depends(get_db),
) -> dict:
    """List all subscriptions known to the system with their last cost sync date."""
    subs = (
        db.query(CostSyncRun.subscription_id, func.max(CostSyncRun.synced_at).label("last_synced"))
        .group_by(CostSyncRun.subscription_id)
        .all()
    )
    return {
        "subscriptions": [
            {
                "subscription_id": s.subscription_id,
                "last_cost_sync": s.last_synced.isoformat() if s.last_synced else None,
            }
            for s in subs
        ],
        "count": len(subs),
    }


@router.get("/score")
def global_health_score(
    subscription_ids: list[str] = Query(..., description="One or more subscription IDs to aggregate"),
    db: Session = Depends(get_db),
) -> dict:
    """Compute a cross-subscription health score and surface top findings."""
    subs = [_normalize(s) for s in subscription_ids]

    all_findings = (
        db.query(OptimizationFinding)
        .filter(OptimizationFinding.subscription_id.in_(subs))
        .all()
    )

    per_sub: dict[str, dict] = {}
    for sub in subs:
        sub_findings = [f for f in all_findings if (f.subscription_id or "").lower() == sub]
        score = _health_score_for_sub(sub_findings)
        open_count = sum(1 for f in sub_findings if (f.status or "").lower() in ("open", "active", ""))
        critical_count = sum(
            1 for f in sub_findings
            if (f.severity or "").lower() == "critical"
            and (f.status or "").lower() in ("open", "active", "")
        )
        # Get latest MTD cost
        run = (
            db.query(CostSyncRun)
            .filter(CostSyncRun.subscription_id == sub)
            .order_by(CostSyncRun.synced_at.desc())
            .first()
        )
        per_sub[sub] = {
            "subscription_id": sub,
            "health_score": score,
            "rating": "A" if score >= 90 else ("B" if score >= 75 else ("C" if score >= 60 else "D")),
            "open_findings": open_count,
            "critical_findings": critical_count,
            "mtd_cost": round(float(run.total_billing or 0), 2) if run else None,
            "billing_currency": run.billing_currency if run else None,
            "last_cost_sync": run.synced_at.isoformat() if run and run.synced_at else None,
        }

    scores = [v["health_score"] for v in per_sub.values()]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    total_cost = sum(v["mtd_cost"] or 0 for v in per_sub.values())
    total_open = sum(v["open_findings"] for v in per_sub.values())

    return {
        "subscriptions_evaluated": len(subs),
        "aggregate_health_score": avg_score,
        "aggregate_rating": "A" if avg_score >= 90 else ("B" if avg_score >= 75 else ("C" if avg_score >= 60 else "D")),
        "total_mtd_cost": round(total_cost, 2),
        "total_open_findings": total_open,
        "per_subscription": list(per_sub.values()),
        "source": "database",
    }


@router.get("/top-findings")
def global_top_findings(
    subscription_ids: list[str] = Query(..., description="Subscription IDs to aggregate"),
    severity: str | None = Query(None, description="Filter by severity"),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """Surface the highest-severity open findings across all specified subscriptions."""
    subs = [_normalize(s) for s in subscription_ids]

    query = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id.in_(subs),
            OptimizationFinding.status.in_(["open", "active", None, ""]),
        )
    )
    if severity:
        query = query.filter(OptimizationFinding.severity == severity.lower())

    findings = query.all()
    findings.sort(
        key=lambda f: (_SEVERITY_WEIGHTS.get((f.severity or "low").lower(), 1) * -1),
    )

    return {
        "total_open_findings": len(findings),
        "findings": [
            {
                "subscription_id": f.subscription_id,
                "finding_id": f.id,
                "rule_id": f.rule_id,
                "resource_id": f.resource_id,
                "title": f.title,
                "severity": f.severity,
                "estimated_savings_usd": float(getattr(f, "estimated_savings_usd") or 0),
            }
            for f in findings[:limit]
        ],
        "source": "database",
    }

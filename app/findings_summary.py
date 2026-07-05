"""Aggregated optimization finding counts for dashboards and filter tabs."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db_types import json_text_like
from app.models import OptimizationFinding
from app.analysis_persist import dedupe_open_findings_for_display
from app.recommendation_execution import implemented_findings_for_subscription

# Rightsizing rules remain cost optimization even when retail savings are not quantified.
COST_OPTIMIZATION_RULE_IDS = frozenset({
    "VM_SKU_SIZING_EXTENDED",
    "VM_RIGHTSIZE_FAMILY",
    "VM_UNDERUTILIZED_EXTENDED",
    "VM_OVERSIZE",
    "VM_UNDERUTILIZED",
    "REDIS_RIGHTSIZE_EXTENDED",
})

RIGHTSIZING_EVIDENCE = or_(
    json_text_like(OptimizationFinding.evidence_json, '%"sizing_action": "cross_family"%'),
    json_text_like(OptimizationFinding.evidence_json, '%"sizing_action": "downgrade"%'),
)


def _normalize_sub(subscription_id: str | None) -> str | None:
    if not subscription_id:
        return None
    return subscription_id.strip().lower()


def build_findings_summary(db: Session, subscription_id: str | None = None) -> dict[str, Any]:
    """Return counts by status, severity, category, and savings type."""
    filt: list = []
    sub = _normalize_sub(subscription_id)
    if sub:
        filt.append(func.lower(OptimizationFinding.subscription_id) == sub)

    def _q():
        q = db.query(OptimizationFinding)
        if filt:
            q = q.filter(*filt)
        return q

    total = _q().count() or 0  # raw rows in DB (includes superseded resolved history)

    by_status_raw = dict(
        db.query(OptimizationFinding.status, func.count(OptimizationFinding.id))
        .filter(*filt)
        .group_by(OptimizationFinding.status)
        .all()
    )
    by_severity = dict(
        db.query(OptimizationFinding.severity, func.count(OptimizationFinding.id))
        .filter(*filt)
        .group_by(OptimizationFinding.severity)
        .all()
    )
    by_category = dict(
        db.query(OptimizationFinding.category, func.count(OptimizationFinding.id))
        .filter(*filt)
        .group_by(OptimizationFinding.category)
        .all()
    )

    open_filt = [*filt, OptimizationFinding.status == "open"]
    open_rows = (
        db.query(OptimizationFinding)
        .filter(*open_filt)
        .all()
    )
    deduped_open = dedupe_open_findings_for_display(open_rows)
    open_count = len(deduped_open)

    acknowledged_count = int(by_status_raw.get("acknowledged") or 0)
    ignored_count = int(by_status_raw.get("ignored") or 0)
    implemented_count = len(implemented_findings_for_subscription(db, sub or "")) if sub else 0
    by_status = {
        "open": open_count,
        "acknowledged": acknowledged_count,
        "implemented": implemented_count,
        "ignored": ignored_count,
    }
    total_display = open_count + acknowledged_count + implemented_count + ignored_count

    total_savings = round(
        sum(float(f.estimated_savings_usd or 0) for f in deduped_open),
        2,
    )

    with_savings_count = (
        db.query(func.count(OptimizationFinding.id))
        .filter(*filt, OptimizationFinding.estimated_savings_usd > 0)
        .scalar()
        or 0
    )
    cost_optimization_count = (
        db.query(func.count(OptimizationFinding.id))
        .filter(
            *filt,
            or_(
                OptimizationFinding.estimated_savings_usd > 0,
                OptimizationFinding.rule_id.in_(COST_OPTIMIZATION_RULE_IDS),
                RIGHTSIZING_EVIDENCE,
            ),
        )
        .scalar()
        or 0
    )
    governance_count = (
        db.query(func.count(OptimizationFinding.id))
        .filter(
            *filt,
            or_(
                OptimizationFinding.estimated_savings_usd.is_(None),
                OptimizationFinding.estimated_savings_usd <= 0,
            ),
            ~OptimizationFinding.rule_id.in_(COST_OPTIMIZATION_RULE_IDS),
            ~RIGHTSIZING_EVIDENCE,
        )
        .scalar()
        or 0
    )

    return {
        "total_findings": int(total_display),
        "open_findings": int(open_count),
        "total_estimated_savings_usd": round(float(total_savings), 2),
        "by_status": {str(k or "unknown"): int(v) for k, v in by_status.items()},
        "by_severity": {str(k or "unknown"): int(v) for k, v in by_severity.items()},
        "by_category": {str(k or "unknown"): int(v) for k, v in by_category.items()},
        "governance_findings": int(governance_count),
        "with_savings_findings": int(with_savings_count),
        "cost_optimization_findings": int(cost_optimization_count),
    }

"""Optimization Timeline — ordered history of optimization runs and key findings.

Returns a chronological list of OptimizationRun entries with their top
findings so the frontend can render a timeline view.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import OptimizationFinding, OptimizationRun


def get_optimization_timeline(
    db: Session,
    subscription_id: str | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    q = (
        db.query(OptimizationRun)
        .order_by(OptimizationRun.created_at.desc())
        .limit(limit)
    )
    if subscription_id:
        q = q.filter(OptimizationRun.subscription_id == subscription_id)
    runs = q.all()

    events: list[dict] = []
    for run in runs:
        # Fetch the top-3 highest-savings findings for this run.
        top_findings = (
            db.query(OptimizationFinding)
            .filter(OptimizationFinding.run_id == run.id)
            .order_by(OptimizationFinding.estimated_monthly_savings.desc())
            .limit(3)
            .all()
        )

        events.append(
            {
                "run_id": str(run.id),
                "subscription_id": run.subscription_id,
                "status": run.status,
                "finding_count": run.finding_count,
                "total_savings_usd": round(
                    sum(
                        float(f.estimated_monthly_savings or 0)
                        for f in top_findings
                    ),
                    2,
                ),
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "top_findings": [
                    {
                        "id": str(f.id),
                        "title": f.title,
                        "resource_name": f.resource_name,
                        "severity": f.severity,
                        "savings_usd": float(f.estimated_monthly_savings or 0),
                    }
                    for f in top_findings
                ],
            }
        )

    return {
        "total_runs": len(runs),
        "events": events,
    }

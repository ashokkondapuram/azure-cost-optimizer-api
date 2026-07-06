"""Optimization Timeline — return optimization run history as an ordered
timeline for the frontend timeline page.

Reads ``OptimizationRun`` records grouped by calendar day so the UI can
render a sparkline / timeline chart of analysis cadence and finding counts.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_optimization_timeline(
    db: Session,
    subscription_id: str | None = None,
    lookback_days: int = 60,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Return paginated optimization runs and a daily summary series."""
    sub_clause = "AND subscription_id = :sub" if subscription_id else ""

    # Recent individual runs for the detail table.
    runs_sql = text(
        f"""
        SELECT
            id,
            subscription_id,
            status,
            finding_count,
            total_estimated_savings,
            engine_version,
            profile,
            created_at,
            completed_at
        FROM optimization_runs
        WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '{lookback_days} days'
        {sub_clause}
        ORDER BY created_at DESC
        LIMIT :lim OFFSET :off
        """
    )
    count_sql = text(
        f"""
        SELECT COUNT(*)
        FROM optimization_runs
        WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '{lookback_days} days'
        {sub_clause}
        """
    )
    # Daily aggregation for the sparkline.
    daily_sql = text(
        f"""
        SELECT
            DATE(created_at)      AS day,
            COUNT(*)              AS run_count,
            SUM(finding_count)    AS findings,
            MAX(total_estimated_savings) AS max_savings
        FROM optimization_runs
        WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '{lookback_days} days'
        {sub_clause}
        GROUP BY DATE(created_at)
        ORDER BY day
        """
    )

    params: dict[str, Any] = {
        "lim": page_size,
        "off": (page - 1) * page_size,
    }
    if subscription_id:
        params["sub"] = subscription_id

    try:
        run_rows = db.execute(runs_sql, params).fetchall()
        total_count = db.execute(count_sql, {k: v for k, v in params.items() if k != "lim" and k != "off"}).scalar() or 0
        daily_rows = db.execute(daily_sql, {k: v for k, v in params.items() if k not in {"lim", "off"}}).fetchall()
    except Exception:
        run_rows, total_count, daily_rows = [], 0, []

    def _run(r: Any) -> dict:
        return {
            "id": str(r[0]),
            "subscription_id": r[1],
            "status": r[2],
            "finding_count": r[3] or 0,
            "total_estimated_savings": float(r[4] or 0),
            "engine_version": r[5],
            "profile": r[6],
            "created_at": r[7].isoformat() if r[7] else None,
            "completed_at": r[8].isoformat() if r[8] else None,
        }

    daily_series = [
        {
            "day": str(d[0]),
            "run_count": int(d[1]),
            "findings": int(d[2] or 0),
            "max_savings": float(d[3] or 0),
        }
        for d in daily_rows
    ]

    return {
        "subscription_id": subscription_id,
        "lookback_days": lookback_days,
        "runs": [_run(r) for r in run_rows],
        "daily_series": daily_series,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total_count,
        },
    }

"""Optimization Timeline — return optimization run history as an ordered
timeline for the frontend timeline page.

Reads ``OptimizationRun`` records grouped by calendar day so the UI can
render a sparkline / timeline chart of analysis cadence and finding counts.

Column mapping (from models.py OptimizationRun):
  analyzed_at          ← timestamp of the run
  total_findings       ← number of findings produced
  total_savings_usd    ← aggregate estimated savings
  profile              ← engine profile used
  engine_version       ← engine version string

Date arithmetic uses a pre-computed ISO-8601 cutoff string so the SQL
is portable across SQLite (dev) and PostgreSQL (prod).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
    sub_clause = "AND subscription_id = :sub" if subscription_id else ""

    runs_sql = text(
        f"""
        SELECT
            id,
            subscription_id,
            total_findings,
            total_savings_usd,
            engine_version,
            profile,
            analyzed_at
        FROM optimization_runs
        WHERE analyzed_at >= :cutoff
        {sub_clause}
        ORDER BY analyzed_at DESC
        LIMIT :lim OFFSET :off
        """
    )
    count_sql = text(
        f"""
        SELECT COUNT(*)
        FROM optimization_runs
        WHERE analyzed_at >= :cutoff
        {sub_clause}
        """
    )
    daily_sql = text(
        f"""
        SELECT
            DATE(analyzed_at)        AS day,
            COUNT(*)                 AS run_count,
            SUM(total_findings)      AS findings,
            MAX(total_savings_usd)   AS max_savings
        FROM optimization_runs
        WHERE analyzed_at >= :cutoff
        {sub_clause}
        GROUP BY DATE(analyzed_at)
        ORDER BY day
        """
    )

    base_params: dict[str, Any] = {"cutoff": cutoff}
    if subscription_id:
        base_params["sub"] = subscription_id

    page_params = {**base_params, "lim": page_size, "off": (page - 1) * page_size}

    try:
        run_rows = db.execute(runs_sql, page_params).fetchall()
        total_count = db.execute(count_sql, base_params).scalar() or 0
        daily_rows = db.execute(daily_sql, base_params).fetchall()
    except Exception:
        run_rows, total_count, daily_rows = [], 0, []

    def _run(r: Any) -> dict:
        return {
            "id": str(r[0]),
            "subscription_id": r[1],
            "total_findings": r[2] or 0,
            "total_savings_usd": float(r[3] or 0),
            "engine_version": r[4],
            "profile": r[5],
            "analyzed_at": r[6].isoformat() if r[6] else None,
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

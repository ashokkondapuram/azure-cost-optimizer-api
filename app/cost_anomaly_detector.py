"""Cost Anomaly Detector — identify spikes in daily cost data.

Uses a simple z-score approach over the synced ``cost_snapshots`` rows:
if a day's spend deviates more than ``threshold`` standard deviations
from the rolling mean it is flagged as an anomaly.

Date arithmetic uses strftime/date() so the query is portable across
SQLite (dev) and PostgreSQL (prod).  For Postgres the
"YYYY-MM-DD" cast also works because cost_date is stored as a text
column in ISO-8601 format.
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULT_ZSCORE_THRESHOLD = 2.0
DEFAULT_LOOKBACK_DAYS = 30


def detect_cost_anomalies(
    db: Session,
    subscription_id: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    zscore_threshold: float = DEFAULT_ZSCORE_THRESHOLD,
) -> dict[str, Any]:
    """Return daily cost series and flagged anomalies."""
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()  # YYYY-MM-DD
    sub_clause = "AND subscription_id = :sub" if subscription_id else ""

    sql = text(
        f"""
        SELECT cost_date, SUM(cost_usd) AS total_cost
        FROM   cost_snapshots
        WHERE  cost_date >= :cutoff
          AND  granularity = 'Daily'
        {sub_clause}
        GROUP  BY cost_date
        ORDER  BY cost_date
        """
    )
    params: dict[str, Any] = {"cutoff": cutoff}
    if subscription_id:
        params["sub"] = subscription_id

    try:
        rows = db.execute(sql, params).fetchall()
    except Exception:
        rows = []

    series = [{"date": str(r[0]), "cost": float(r[1])} for r in rows]

    anomalies: list[dict] = []
    if len(series) >= 5:
        costs = [s["cost"] for s in series]
        mean = statistics.mean(costs)
        try:
            stdev = statistics.stdev(costs)
        except statistics.StatisticsError:
            stdev = 0.0

        for s in series:
            z = abs(s["cost"] - mean) / stdev if stdev > 0 else 0.0
            if z >= zscore_threshold:
                anomalies.append(
                    {
                        "date": s["date"],
                        "cost": s["cost"],
                        "zscore": round(z, 2),
                        "mean": round(mean, 2),
                        "deviation_pct": round(100 * (s["cost"] - mean) / mean, 1)
                        if mean
                        else 0.0,
                    }
                )

    return {
        "lookback_days": lookback_days,
        "zscore_threshold": zscore_threshold,
        "series": series,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }

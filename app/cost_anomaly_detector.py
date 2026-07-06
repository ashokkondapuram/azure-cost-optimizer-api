"""Cost Anomaly Detector — identify spikes in daily cost data.

Uses a simple z-score approach over the synced daily cost rows:
if a day's spend deviates more than `threshold` standard deviations
from the rolling mean it is flagged as an anomaly.
"""
from __future__ import annotations

import statistics
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
    sub_clause = "AND subscription_id = :sub" if subscription_id else ""
    sql = text(
        f"""
        SELECT date, SUM(cost) AS total_cost
        FROM   cost_daily
        WHERE  date >= CURRENT_DATE - INTERVAL '{lookback_days} days'
        {sub_clause}
        GROUP  BY date
        ORDER  BY date
        """
    )
    params: dict = {}
    if subscription_id:
        params["sub"] = subscription_id

    try:
        rows = db.execute(sql, params).fetchall()
    except Exception:
        # Table may not exist yet (fresh install).
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

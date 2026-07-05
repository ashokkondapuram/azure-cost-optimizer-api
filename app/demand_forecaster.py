"""Demand forecasting from utilization history (3-B)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.utilization_history import utilization_trend


def forecast_metric(
    db: Session,
    resource_id: str,
    metric_name: str,
    *,
    subscription_id: str | None = None,
    weeks_ahead: int = 4,
    min_points: int = 4,
) -> dict[str, Any]:
    """
    Linear trend forecast on weekly utilization snapshots.

    Returns trend label, slope, projection, and whether downsize is safe.
    """
    trend = utilization_trend(
        db,
        resource_id,
        metric_name,
        subscription_id=subscription_id,
        min_points=min_points,
    )
    if trend.get("insufficient_history"):
        return {
            "trend": "insufficient_data",
            "slope_per_week": None,
            f"projected_{weeks_ahead}w": None,
            "sample_count": trend.get("sample_count", 0),
            "downsize_allowed": True,
        }

    slope = float(trend.get("growth_rate_per_week") or 0)
    current = trend.get("current_value")
    projected = trend.get("projected_4w")
    if weeks_ahead != 4 and current is not None:
        projected = float(current) + slope * weeks_ahead

    label = trend.get("slope", "stable")
    return {
        "trend": label,
        "slope_per_week": round(slope, 3),
        f"projected_{weeks_ahead}w": projected,
        "sample_count": trend.get("sample_count"),
        "volatility": trend.get("volatility"),
        "downsize_allowed": label != "growing",
        "current_value": current,
    }


def batch_forecasts(
    db: Session,
    subscription_id: str,
    resource_ids: list[str],
    *,
    metrics: list[str] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """{resource_id: {metric_name: forecast}}."""
    metric_names = metrics or ["avg_cpu_pct", "avg_disk_used_pct"]
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for rid in resource_ids:
        norm = (rid or "").lower()
        if not norm:
            continue
        out[norm] = {
            m: forecast_metric(db, norm, m, subscription_id=subscription_id)
            for m in metric_names
        }
    return out

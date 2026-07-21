"""Utilization trend helpers — history table removed; use enrichment + Monitor fallback."""
from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.focus_mapping import normalize_arm_id
from app.resource_utilization import MONITOR_FACT_KEYS

log = structlog.get_logger(__name__)

DEFAULT_PERIOD_DAYS = 7
RETENTION_DAYS = 180
MIN_TREND_POINTS = 4
SLOPE_GROWING_THRESHOLD = 0.5
SLOPE_SHRINKING_THRESHOLD = -0.5

PERSIST_METRIC_KEYS = frozenset(k for k in MONITOR_FACT_KEYS if k not in {
    "data_source",
})


def collect_resource_ids_from_buckets(buckets: dict[str, list]) -> list[str]:
    """Collect normalized ARM resource IDs from engine inventory buckets."""
    ids: list[str] = []
    seen: set[str] = set()
    for items in (buckets or {}).values():
        for item in items or []:
            rid = normalize_arm_id(item.get("id") or "").lower()
            if rid and rid not in seen:
                seen.add(rid)
                ids.append(rid)
    return ids


def persist_utilization_snapshot(
    db: Session,
    subscription_id: str,
    buckets: dict[str, list],
    *,
    resource_facts: dict[str, dict[str, float]] | None = None,
    period_days: int = DEFAULT_PERIOD_DAYS,
    snapshot_date: str | None = None,
) -> int:
    """Deprecated — utilization history table removed; metrics live in enrichment."""
    return 0


def prune_utilization_history(
    db: Session,
    *,
    subscription_id: str | None = None,
    retention_days: int = RETENTION_DAYS,
) -> int:
    return 0


def utilization_series(
    db: Session,
    resource_id: str,
    metric_name: str,
    *,
    subscription_id: str | None = None,
    limit: int = 90,
) -> list[dict[str, Any]]:
    return []


def utilization_series_with_monitor_fallback(
    db: Session,
    resource_id: str,
    metric_name: str,
    *,
    subscription_id: str | None = None,
    timespan: str = "P7D",
    limit: int = 90,
    min_points: int = 2,
) -> tuple[list[dict[str, Any]], str]:
    """Return chart points from Azure Monitor when enrichment has no time series."""
    from app.monitor_metrics import fetch_monitor_fact_timeseries

    monitor_points = fetch_monitor_fact_timeseries(
        db,
        resource_id,
        metric_name,
        timespan=timespan,
    )
    if limit > 0 and len(monitor_points) > limit:
        monitor_points = monitor_points[-limit:]
    if monitor_points:
        return monitor_points, "monitor"
    return [], "none"


def _insufficient_trend(sample_count: int = 0) -> dict[str, Any]:
    return {
        "slope": "unknown",
        "growth_rate_per_week": None,
        "volatility": None,
        "projected_4w": None,
        "sample_count": sample_count,
        "insufficient_history": True,
        "current_value": None,
    }


def utilization_trend(
    db: Session,
    resource_id: str,
    metric_name: str,
    *,
    min_points: int = MIN_TREND_POINTS,
    subscription_id: str | None = None,
) -> dict[str, Any]:
    """Trend from stored weekly snapshots — table removed; returns insufficient history."""
    return _insufficient_trend()


def batch_utilization_trends(
    db: Session,
    subscription_id: str,
    resource_ids: list[str],
    *,
    metrics: list[str] | None = None,
    min_points: int = MIN_TREND_POINTS,
) -> dict[str, dict[str, dict[str, Any]]]:
    metric_names = metrics or ["avg_cpu_pct"]
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for rid in resource_ids:
        norm = normalize_arm_id(rid).lower()
        if not norm:
            continue
        out[norm] = {metric: _insufficient_trend() for metric in metric_names}
    return out


def downsize_allowed_by_trend(trend: dict[str, Any] | None) -> bool:
    if not trend or trend.get("insufficient_history"):
        return True
    return trend.get("slope") != "growing"


def storage_capacity_warning(
    trend: dict[str, Any] | None,
    *,
    current_pct: float | None,
    threshold_pct: float = 80.0,
    horizon_days: int = 30,
) -> dict[str, Any] | None:
    if not trend or trend.get("insufficient_history") or current_pct is None:
        return None
    weekly_growth = trend.get("growth_rate_per_week")
    if weekly_growth is None:
        return None
    daily_growth = weekly_growth / 7.0
    projected_pct = current_pct + daily_growth * horizon_days
    if projected_pct < threshold_pct:
        return None
    days_to_threshold = None
    if daily_growth > 0:
        days_to_threshold = max(1, int((threshold_pct - current_pct) / daily_growth))
    return {
        "current_pct": current_pct,
        "projected_pct": round(projected_pct, 1),
        "threshold_pct": threshold_pct,
        "days_to_threshold": days_to_threshold,
        "slope": trend.get("slope"),
    }

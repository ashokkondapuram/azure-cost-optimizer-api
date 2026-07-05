"""Persist and query resource utilization snapshots for trend analysis (T2-A)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.focus_mapping import normalize_arm_id
from app.models import ResourceUtilizationHistory
from app.resource_utilization import MONITOR_FACT_KEYS

log = structlog.get_logger(__name__)

DEFAULT_PERIOD_DAYS = 7
RETENTION_DAYS = 180
MIN_TREND_POINTS = 4
SLOPE_GROWING_THRESHOLD = 0.5
SLOPE_SHRINKING_THRESHOLD = -0.5

# Numeric monitor facts worth persisting each analysis run.
PERSIST_METRIC_KEYS = frozenset(k for k in MONITOR_FACT_KEYS if k not in {
    "data_source",
})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot_date(now: datetime | None = None) -> str:
    return (now or _utc_now()).strftime("%Y-%m-%d")


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


def _facts_for_resource(
    resource: dict[str, Any],
    resource_facts: dict[str, dict[str, float]] | None,
) -> dict[str, float]:
    rid = normalize_arm_id(resource.get("id") or "").lower()
    facts: dict[str, float] = {}
    for key, raw in (resource.get("_technical_facts") or {}).items():
        if key in PERSIST_METRIC_KEYS and isinstance(raw, (int, float)):
            facts[key] = float(raw)
    for key, raw in (resource_facts or {}).get(rid, {}).items():
        if key in PERSIST_METRIC_KEYS and isinstance(raw, (int, float)):
            facts[key] = float(raw)
    return facts


def _metric_values(metric_name: str, facts: dict[str, float]) -> tuple[float | None, float | None, float | None]:
    """Map fact keys to (avg, max, min) for a persisted row."""
    if metric_name not in facts:
        return None, None, None
    value = float(facts[metric_name])
    if metric_name.startswith("max_"):
        return None, value, None
    if metric_name.startswith("min_"):
        return None, None, value
    return value, None, None


def persist_utilization_snapshot(
    db: Session,
    subscription_id: str,
    buckets: dict[str, list],
    *,
    resource_facts: dict[str, dict[str, float]] | None = None,
    period_days: int = DEFAULT_PERIOD_DAYS,
    snapshot_date: str | None = None,
) -> int:
    """
    Upsert one utilization row per resource/metric for the current snapshot date.
    Returns the number of rows written.
    """
    sub = subscription_id.lower()
    today = snapshot_date or _snapshot_date()
    now = _utc_now()
    written = 0

    for items in (buckets or {}).values():
        for resource in items or []:
            rid = normalize_arm_id(resource.get("id") or "").lower()
            if not rid:
                continue
            facts = _facts_for_resource(resource, resource_facts)
            if not facts:
                continue
            for metric_name, _ in facts.items():
                value_avg, value_max, value_min = _metric_values(metric_name, facts)
                if value_avg is None and value_max is None and value_min is None:
                    continue
                existing = (
                    db.query(ResourceUtilizationHistory)
                    .filter(
                        ResourceUtilizationHistory.subscription_id == sub,
                        ResourceUtilizationHistory.resource_id == rid,
                        ResourceUtilizationHistory.metric_name == metric_name,
                        ResourceUtilizationHistory.snapshot_date == today,
                    )
                    .first()
                )
                if existing:
                    existing.recorded_at = now
                    existing.value_avg = value_avg
                    existing.value_max = value_max
                    existing.value_min = value_min
                    existing.period_days = period_days
                else:
                    db.add(ResourceUtilizationHistory(
                        id=str(uuid.uuid4()),
                        subscription_id=sub,
                        resource_id=rid,
                        metric_name=metric_name,
                        snapshot_date=today,
                        recorded_at=now,
                        value_avg=value_avg,
                        value_max=value_max,
                        value_min=value_min,
                        period_days=period_days,
                    ))
                written += 1

    if written:
        prune_utilization_history(db, subscription_id=sub, retention_days=RETENTION_DAYS)
    return written


def prune_utilization_history(
    db: Session,
    *,
    subscription_id: str | None = None,
    retention_days: int = RETENTION_DAYS,
) -> int:
    """Delete utilization history rows older than retention window."""
    cutoff = (_utc_now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    query = db.query(ResourceUtilizationHistory).filter(
        ResourceUtilizationHistory.snapshot_date < cutoff,
    )
    if subscription_id:
        query = query.filter(ResourceUtilizationHistory.subscription_id == subscription_id.lower())
    deleted = query.delete(synchronize_session=False)
    if deleted:
        log.info("utilization_history_pruned", deleted=deleted, cutoff=cutoff)
    return deleted


def _series_values(rows: list[ResourceUtilizationHistory]) -> list[float]:
    values: list[float] = []
    for row in rows:
        if row.value_avg is not None:
            values.append(float(row.value_avg))
        elif row.value_max is not None:
            values.append(float(row.value_max))
    return values


def _linear_slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den


def _classify_slope(slope: float) -> str:
    if slope > SLOPE_GROWING_THRESHOLD:
        return "growing"
    if slope < SLOPE_SHRINKING_THRESHOLD:
        return "shrinking"
    return "stable"


def utilization_trend(
    db: Session,
    resource_id: str,
    metric_name: str,
    *,
    min_points: int = MIN_TREND_POINTS,
    subscription_id: str | None = None,
) -> dict[str, Any]:
    """
    Return utilization trend for a resource metric using stored weekly snapshots.

    Keys: slope, growth_rate_per_week, volatility, projected_4w, sample_count,
    insufficient_history, current_value.
    """
    rid = normalize_arm_id(resource_id).lower()
    query = (
        db.query(ResourceUtilizationHistory)
        .filter(
            ResourceUtilizationHistory.resource_id == rid,
            ResourceUtilizationHistory.metric_name == metric_name,
        )
        .order_by(ResourceUtilizationHistory.snapshot_date.asc())
    )
    if subscription_id:
        query = query.filter(ResourceUtilizationHistory.subscription_id == subscription_id.lower())
    rows = query.all()
    values = _series_values(rows)
    if len(values) < min_points:
        return {
            "slope": "unknown",
            "growth_rate_per_week": None,
            "volatility": None,
            "projected_4w": None,
            "sample_count": len(values),
            "insufficient_history": True,
            "current_value": values[-1] if values else None,
        }

    slope = _linear_slope(values)
    mean_val = sum(values) / len(values)
    if mean_val > 0:
        variance = sum((v - mean_val) ** 2 for v in values) / len(values)
        volatility = (variance ** 0.5) / mean_val
    else:
        volatility = 0.0
    projected = values[-1] + slope * 4

    return {
        "slope": _classify_slope(slope),
        "growth_rate_per_week": round(slope, 3),
        "volatility": round(volatility, 3),
        "projected_4w": round(projected, 2),
        "sample_count": len(values),
        "insufficient_history": False,
        "current_value": values[-1],
    }


def batch_utilization_trends(
    db: Session,
    subscription_id: str,
    resource_ids: list[str],
    *,
    metrics: list[str] | None = None,
    min_points: int = MIN_TREND_POINTS,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Load utilization trends for many resources: {resource_id: {metric: trend}}."""
    metric_names = metrics or ["avg_cpu_pct"]
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for rid in resource_ids:
        norm = normalize_arm_id(rid).lower()
        if not norm:
            continue
        out[norm] = {
            metric: utilization_trend(
                db, norm, metric, min_points=min_points, subscription_id=subscription_id,
            )
            for metric in metric_names
        }
    return out


def downsize_allowed_by_trend(trend: dict[str, Any] | None) -> bool:
    """Block VM downsize when utilization is trending upward with enough history."""
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
    """
    Return a capacity warning when projected storage crosses threshold within horizon.
    Uses weekly slope scaled to daily growth (approximate).
    """
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

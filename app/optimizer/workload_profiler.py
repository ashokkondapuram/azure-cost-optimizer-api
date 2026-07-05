"""Persist workload profiles from classifier + utilization history."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.metrics_loader import load_cached_resource_facts
from app.models import ResourceSnapshot, ResourceUtilizationHistory, WorkloadProfile
from app.optimizer.workload_classifier import WorkloadClass, classify_workload
from app.utilization_history import utilization_trend
from app.utils import norm_arm_id, parse_tags_json, utc_now

_CLASSIFIER_TO_WORKLOAD_TYPE: dict[str, str] = {
    "zombie": "steady",
    "idle": "steady",
    "batch": "bursty",
    "interactive": "interactive",
    "database": "steady",
    "analytics": "steady",
}


def _coefficient_of_variation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean <= 0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return (variance ** 0.5) / mean


def _history_values(
    db: Session,
    subscription_id: str,
    resource_id: str,
    metric_name: str = "avg_cpu_pct",
    *,
    limit: int = 8,
) -> list[float]:
    rows = (
        db.query(ResourceUtilizationHistory)
        .filter(
            ResourceUtilizationHistory.subscription_id == subscription_id,
            ResourceUtilizationHistory.resource_id == resource_id,
            ResourceUtilizationHistory.metric_name == metric_name,
        )
        .order_by(ResourceUtilizationHistory.snapshot_date.desc())
        .limit(limit)
        .all()
    )
    values: list[float] = []
    for row in reversed(rows):
        if row.value_avg is not None:
            values.append(float(row.value_avg))
        elif row.value_max is not None:
            values.append(float(row.value_max))
    return values


def _detect_seasonality(values: list[float]) -> tuple[bool, float | None]:
    """Lightweight seasonality proxy: alternating week-over-week swings."""
    if len(values) < 4:
        return False, None
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    sign_changes = sum(
        1 for i in range(1, len(deltas))
        if deltas[i] * deltas[i - 1] < 0
    )
    detected = sign_changes >= max(2, len(deltas) // 2)
    peak = max(values) if values else 0.0
    mean = sum(values) / len(values) if values else 0.0
    peak_pct = round((peak / mean - 1) * 100, 2) if mean > 0 else None
    if peak_pct is not None and peak_pct < 0:
        peak_pct = 0.0
    return detected, peak_pct


def profile_resource(
    db: Session,
    snapshot: ResourceSnapshot,
    facts: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Build workload profile fields for one resource."""
    rid = norm_arm_id(snapshot.resource_id)
    sub = norm_arm_id(snapshot.subscription_id)
    facts = facts or {}
    tags = parse_tags_json(snapshot.tags_json if isinstance(snapshot.tags_json, str) else None)

    resource_dict = {
        "id": snapshot.resource_id,
        "tags": tags,
        "type": snapshot.resource_type,
    }
    classifier_class: WorkloadClass = classify_workload(
        resource_dict,
        facts,
        resource_type=snapshot.resource_type or "",
    )
    workload_type = _CLASSIFIER_TO_WORKLOAD_TYPE.get(classifier_class, "interactive")

    avg_cpu = float(facts.get("avg_cpu_pct") or 0)
    max_cpu = float(facts.get("max_cpu_pct") or avg_cpu)
    burstiness = min(100.0, ((max_cpu - avg_cpu) / max(avg_cpu, 1.0)) * 25.0)
    peak_factor = round(max_cpu / max(avg_cpu, 1.0), 2) if avg_cpu > 0 else 1.0

    hist = _history_values(db, sub, rid)
    var_7d = _coefficient_of_variation(hist[-2:]) * 100 if len(hist) >= 2 else None
    var_30d = _coefficient_of_variation(hist) * 100 if hist else None
    cov = var_30d

    cpu_trend = utilization_trend(db, rid, "avg_cpu_pct", subscription_id=sub, min_points=2)
    utilization_trend_label = cpu_trend.get("slope") or "unknown"
    if utilization_trend_label == "growing":
        utilization_trend_label = "increasing"
    elif utilization_trend_label == "shrinking":
        utilization_trend_label = "decreasing"
    elif utilization_trend_label == "stable":
        utilization_trend_label = "stable"
    else:
        utilization_trend_label = "unknown"

    seasonality, seasonal_peak = _detect_seasonality(hist)

    if burstiness > 40 or peak_factor > 2.0:
        workload_type = "bursty"
    elif burstiness < 20 and peak_factor < 1.5:
        workload_type = "steady"

    return {
        "resource_id": rid,
        "subscription_id": sub,
        "workload_type": workload_type,
        "burstiness_score": round(burstiness, 2),
        "peak_hour_factor": peak_factor,
        "utilization_trend": utilization_trend_label,
        "utilization_variance_7d": round(var_7d, 2) if var_7d is not None else None,
        "utilization_variance_30d": round(var_30d, 2) if var_30d is not None else None,
        "utilization_coefficient_variance": round(cov, 2) if cov is not None else None,
        "detected_seasonality": seasonality,
        "seasonal_peak_percentage": seasonal_peak,
        "classifier_class": classifier_class,
    }


def upsert_workload_profiles(
    db: Session,
    subscription_id: str,
    *,
    facts_map: dict[str, dict[str, float]] | None = None,
) -> dict[str, int]:
    """Profile all active resources and persist workload_profiles rows."""
    sub = subscription_id.strip().lower()
    facts_map = facts_map or load_cached_resource_facts(db, sub)
    snapshots = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
        )
        .all()
    )

    created = 0
    updated = 0
    now = utc_now()

    for snap in snapshots:
        rid = norm_arm_id(snap.resource_id)
        if not rid:
            continue
        fields = profile_resource(db, snap, facts_map.get(rid) or {})
        existing = (
            db.query(WorkloadProfile)
            .filter(
                WorkloadProfile.subscription_id == sub,
                WorkloadProfile.resource_id == rid,
            )
            .first()
        )
        if existing:
            for key, value in fields.items():
                if key not in {"resource_id", "subscription_id"}:
                    setattr(existing, key, value)
            existing.synced_at = now
            updated += 1
        else:
            db.add(WorkloadProfile(
                id=str(uuid.uuid4()),
                synced_at=now,
                **fields,
            ))
            created += 1

    db.commit()
    return {"created": created, "updated": updated, "total": created + updated}

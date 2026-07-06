"""Cost anomaly detection — flag daily spend spikes vs. rolling baseline."""
from __future__ import annotations

from datetime import date, timedelta
from statistics import mean, stdev
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CostDailyByServiceSnapshot

router = APIRouter(prefix="/anomalies", tags=["Cost Anomalies"])

_DEFAULT_WINDOW_DAYS = 30
_DEFAULT_THRESHOLD_SIGMA = 2.0
_DEFAULT_LOOKBACK_DAYS = 7


def _daily_totals(
    db: Session,
    subscription_id: str,
    start: date,
    end: date,
) -> list[dict]:
    """Return daily aggregated cost rows for the given subscription/date range."""
    sub = subscription_id.strip().lower()
    rows = (
        db.query(
            CostDailyByServiceSnapshot.cost_date,
            func.sum(CostDailyByServiceSnapshot.cost_billing).label("total"),
            func.max(CostDailyByServiceSnapshot.billing_currency).label("currency"),
        )
        .filter(
            CostDailyByServiceSnapshot.subscription_id == sub,
            CostDailyByServiceSnapshot.cost_date >= start.isoformat(),
            CostDailyByServiceSnapshot.cost_date <= end.isoformat(),
            CostDailyByServiceSnapshot.service_name != "__subscription__",
        )
        .group_by(CostDailyByServiceSnapshot.cost_date)
        .order_by(CostDailyByServiceSnapshot.cost_date)
        .all()
    )
    return [
        {"date": r.cost_date, "total": round(float(r.total or 0), 2), "currency": r.currency or "CAD"}
        for r in rows
    ]


def _detect_anomalies(
    daily: list[dict],
    window: int,
    threshold_sigma: float,
    lookback: int,
) -> list[dict[str, Any]]:
    """Z-score anomaly detection over a rolling baseline window."""
    anomalies: list[dict] = []
    for i in range(window, len(daily)):
        baseline = [d["total"] for d in daily[max(0, i - window):i]]
        if len(baseline) < 3:
            continue
        mu = mean(baseline)
        sigma = stdev(baseline)
        day = daily[i]
        if sigma == 0:
            continue
        z = (day["total"] - mu) / sigma
        if abs(z) >= threshold_sigma:
            direction = "spike" if z > 0 else "drop"
            anomalies.append({
                "date": day["date"],
                "actual_cost": day["total"],
                "baseline_mean": round(mu, 2),
                "baseline_stddev": round(sigma, 2),
                "z_score": round(z, 3),
                "direction": direction,
                "currency": day["currency"],
                "severity": "high" if abs(z) >= threshold_sigma * 1.5 else "medium",
            })
    return sorted(anomalies, key=lambda x: x["date"], reverse=True)[:lookback * 3]


@router.get("/daily/{subscription_id}")
def get_cost_anomalies(
    subscription_id: str,
    window_days: int = Query(_DEFAULT_WINDOW_DAYS, ge=7, le=90, description="Rolling baseline window in days"),
    threshold_sigma: float = Query(_DEFAULT_THRESHOLD_SIGMA, ge=1.0, le=5.0, description="Z-score threshold for anomaly"),
    lookback_days: int = Query(_DEFAULT_LOOKBACK_DAYS, ge=1, le=30, description="Days to inspect for anomalies"),
    db: Session = Depends(get_db),
) -> dict:
    """Detect daily spend anomalies using rolling Z-score over the baseline window."""
    end = date.today()
    start = end - timedelta(days=window_days + lookback_days)
    daily = _daily_totals(db, subscription_id, start, end)
    if not daily:
        return {"anomalies": [], "message": "No daily cost data found. Run a cost sync first.", "source": "database"}

    anomalies = _detect_anomalies(daily, window_days, threshold_sigma, lookback_days)
    currency = daily[-1]["currency"] if daily else "CAD"
    return {
        "subscription_id": subscription_id,
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
        "window_days": window_days,
        "threshold_sigma": threshold_sigma,
        "lookback_days": lookback_days,
        "billing_currency": currency,
        "source": "database",
    }


@router.get("/service/{subscription_id}")
def get_service_anomalies(
    subscription_id: str,
    window_days: int = Query(21, ge=7, le=60),
    threshold_sigma: float = Query(2.5, ge=1.0, le=5.0),
    db: Session = Depends(get_db),
) -> dict:
    """Detect per-service spend anomalies for the past 7 days vs. the rolling window."""
    sub = subscription_id.strip().lower()
    end = date.today()
    start = end - timedelta(days=window_days + 7)

    rows = (
        db.query(
            CostDailyByServiceSnapshot.cost_date,
            CostDailyByServiceSnapshot.service_name,
            CostDailyByServiceSnapshot.cost_billing,
            CostDailyByServiceSnapshot.billing_currency,
        )
        .filter(
            CostDailyByServiceSnapshot.subscription_id == sub,
            CostDailyByServiceSnapshot.cost_date >= start.isoformat(),
            CostDailyByServiceSnapshot.cost_date <= end.isoformat(),
            CostDailyByServiceSnapshot.service_name != "__subscription__",
        )
        .order_by(CostDailyByServiceSnapshot.cost_date)
        .all()
    )

    by_service: dict[str, list[dict]] = {}
    for r in rows:
        by_service.setdefault(r.service_name, []).append({
            "date": r.cost_date,
            "total": float(r.cost_billing or 0),
            "currency": r.billing_currency or "CAD",
        })

    all_anomalies: list[dict] = []
    for service, daily in by_service.items():
        found = _detect_anomalies(daily, window_days, threshold_sigma, 7)
        for a in found:
            all_anomalies.append({**a, "service_name": service})

    all_anomalies.sort(key=lambda x: abs(x["z_score"]), reverse=True)
    return {
        "subscription_id": subscription_id,
        "service_anomalies": all_anomalies[:50],
        "anomaly_count": len(all_anomalies),
        "window_days": window_days,
        "threshold_sigma": threshold_sigma,
        "source": "database",
    }

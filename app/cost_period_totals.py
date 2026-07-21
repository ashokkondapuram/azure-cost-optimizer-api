"""Persist authoritative Azure Cost Management subscription totals for all cost presets."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session

from app.cost_timeframes import SYNCED_PERIOD_TIMEFRAMES
from app.models import CostPeriodTotalSnapshot

log = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_sub(subscription_id: str) -> str:
    return (subscription_id or "").strip().lower()


def upsert_period_total(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    period_start: str,
    period_end: str,
    pretax_total: float,
    cost_usd_total: float,
    billing_currency: str,
) -> CostPeriodTotalSnapshot:
    """Insert or update the latest subscription total for a cost preset."""
    sub = _normalize_sub(subscription_id)
    tf = (timeframe or "").strip()
    existing = (
        db.query(CostPeriodTotalSnapshot)
        .filter(
            CostPeriodTotalSnapshot.subscription_id == sub,
            CostPeriodTotalSnapshot.timeframe == tf,
        )
        .first()
    )
    if existing:
        existing.period_start = period_start
        existing.period_end = period_end
        existing.pretax_total = round(float(pretax_total or 0.0), 2)
        existing.cost_usd_total = round(float(cost_usd_total or 0.0), 2)
        existing.billing_currency = billing_currency or "CAD"
        existing.synced_at = _now()
        return existing

    row = CostPeriodTotalSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        timeframe=tf,
        period_start=period_start,
        period_end=period_end,
        pretax_total=round(float(pretax_total or 0.0), 2),
        cost_usd_total=round(float(cost_usd_total or 0.0), 2),
        billing_currency=billing_currency or "CAD",
    )
    db.add(row)
    return row


def period_total_from_db(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
) -> dict | None:
    """Return the stored subscription total when the synced window matches the request."""
    sub = _normalize_sub(subscription_id)
    tf = (timeframe or "").strip()
    if tf == "Custom":
        return None
    row = (
        db.query(CostPeriodTotalSnapshot)
        .filter(
            CostPeriodTotalSnapshot.subscription_id == sub,
            CostPeriodTotalSnapshot.timeframe == tf,
        )
        .first()
    )
    if not row:
        return None
    if period_start and (row.period_start or "")[:10] != period_start[:10]:
        return None
    if period_end:
        stored_end = (row.period_end or "")[:10]
        req_end = period_end[:10]
        # Allow slightly stale same-month totals (e.g. sync ran yesterday) instead of zeroing the dashboard.
        if stored_end and stored_end < req_end and stored_end[:7] != req_end[:7]:
            return None
    if not row.pretax_total and not row.cost_usd_total:
        return None
    return {
        "pretax_total": round(float(row.pretax_total or 0.0), 2),
        "cost_usd_total": round(float(row.cost_usd_total or 0.0), 2),
        "billing_currency": row.billing_currency or "CAD",
        "period_start": row.period_start,
        "period_end": row.period_end,
        "mtd_start": row.period_start,
        "mtd_end": row.period_end,
        "synced_at": row.synced_at.isoformat() if row.synced_at else None,
        "total_source": "azure_subscription_query",
        "source": "database",
        "timeframe": tf,
    }


def latest_ytd_from_db(db: Session, subscription_id: str) -> dict | None:
    """Shortcut for dashboard YTD from the hourly Cost Management sync."""
    from datetime import date
    from app.cost_timeframes import period_for_timeframe

    period = period_for_timeframe("ThisYear")
    return period_total_from_db(
        db,
        subscription_id,
        "ThisYear",
        period_start=period["period_start"],
        period_end=period["period_end"],
    )


def list_period_totals_from_db(db: Session, subscription_id: str) -> list[dict]:
    """All synced period totals for a subscription (newest sync first per timeframe)."""
    sub = _normalize_sub(subscription_id)
    rows = (
        db.query(CostPeriodTotalSnapshot)
        .filter(CostPeriodTotalSnapshot.subscription_id == sub)
        .order_by(CostPeriodTotalSnapshot.timeframe)
        .all()
    )
    return [
        {
            "timeframe": row.timeframe,
            "pretax_total": round(float(row.pretax_total or 0.0), 2),
            "cost_usd_total": round(float(row.cost_usd_total or 0.0), 2),
            "billing_currency": row.billing_currency or "CAD",
            "period_start": row.period_start,
            "period_end": row.period_end,
            "synced_at": row.synced_at.isoformat() if row.synced_at else None,
        }
        for row in rows
    ]

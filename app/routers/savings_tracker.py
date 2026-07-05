"""Savings realisation tracker — compare current MTD costs against prior months."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CostByServiceSnapshot, CostSyncRun

router = APIRouter(prefix="/savings", tags=["Savings Tracker"])


def _normalize(sub: str) -> str:
    return (sub or "").strip().lower()


def _prior_month(month: str) -> str | None:
    try:
        year, mon = int(month[:4]), int(month[5:7])
    except (ValueError, IndexError):
        return None
    if mon <= 1:
        return f"{year - 1}-12"
    return f"{year}-{mon - 1:02d}"


def _service_totals(db: Session, sub: str, month: str) -> dict[str, float]:
    rows = (
        db.query(CostByServiceSnapshot.service_name, CostByServiceSnapshot.cost_billing)
        .filter(
            CostByServiceSnapshot.subscription_id == sub,
            CostByServiceSnapshot.month == month,
        )
        .all()
    )
    return {r.service_name: float(r.cost_billing or 0) for r in rows}


def _subscription_total(db: Session, sub: str, month: str) -> float:
    run = (
        db.query(CostSyncRun)
        .filter(CostSyncRun.subscription_id == sub, CostSyncRun.month == month)
        .order_by(CostSyncRun.synced_at.desc())
        .first()
    )
    if run and run.total_billing:
        return float(run.total_billing)
    rows = _service_totals(db, sub, month)
    return sum(rows.values())


@router.get("/month-over-month/{subscription_id}")
def month_over_month_savings(
    subscription_id: str,
    months_back: int = Query(3, ge=1, le=12, description="Number of prior months to compare"),
    db: Session = Depends(get_db),
) -> dict:
    """Compute month-over-month spend changes showing realised savings or overruns."""
    sub = _normalize(subscription_id)
    current_month = date.today().strftime("%Y-%m")

    # Build list of months: current + N prior
    months: list[str] = [current_month]
    m = current_month
    for _ in range(months_back):
        p = _prior_month(m)
        if not p:
            break
        months.append(p)
        m = p
    months.reverse()  # oldest first

    currency_row = (
        db.query(CostByServiceSnapshot.billing_currency)
        .filter(CostByServiceSnapshot.subscription_id == sub)
        .first()
    )
    currency = (currency_row[0] if currency_row else None) or "CAD"

    timeline: list[dict] = []
    for month in months:
        total = _subscription_total(db, sub, month)
        timeline.append({"month": month, "total_spend": round(total, 2), "currency": currency})

    # Compute deltas between consecutive months
    comparisons: list[dict] = []
    for i in range(1, len(timeline)):
        prev = timeline[i - 1]
        curr = timeline[i]
        delta = round(curr["total_spend"] - prev["total_spend"], 2)
        pct = round((delta / prev["total_spend"]) * 100, 1) if prev["total_spend"] > 0 else 0.0
        comparisons.append({
            "from_month": prev["month"],
            "to_month": curr["month"],
            "from_spend": prev["total_spend"],
            "to_spend": curr["total_spend"],
            "delta": delta,
            "delta_pct": pct,
            "status": "savings" if delta < 0 else ("overspend" if delta > 0 else "flat"),
            "currency": currency,
        })

    total_delta = round(timeline[-1]["total_spend"] - timeline[0]["total_spend"], 2) if len(timeline) >= 2 else 0.0
    return {
        "subscription_id": subscription_id,
        "billing_currency": currency,
        "timeline": timeline,
        "comparisons": comparisons,
        "net_delta_vs_oldest": total_delta,
        "net_status": "savings" if total_delta < 0 else ("overspend" if total_delta > 0 else "flat"),
        "source": "database",
    }


@router.get("/service-breakdown/{subscription_id}")
def service_savings_breakdown(
    subscription_id: str,
    base_month: str = Query(..., description="Baseline month (YYYY-MM)"),
    compare_month: str = Query(..., description="Comparison month (YYYY-MM)"),
    db: Session = Depends(get_db),
) -> dict:
    """Compare service-level spend between two months to show per-service savings or overruns."""
    sub = _normalize(subscription_id)
    base = _service_totals(db, sub, base_month)
    compare = _service_totals(db, sub, compare_month)

    currency_row = (
        db.query(CostByServiceSnapshot.billing_currency)
        .filter(CostByServiceSnapshot.subscription_id == sub)
        .first()
    )
    currency = (currency_row[0] if currency_row else None) or "CAD"

    services = sorted(set(base) | set(compare))
    rows: list[dict] = []
    for svc in services:
        base_cost = base.get(svc, 0.0)
        compare_cost = compare.get(svc, 0.0)
        delta = round(compare_cost - base_cost, 2)
        pct = round((delta / base_cost) * 100, 1) if base_cost > 0 else None
        rows.append({
            "service_name": svc,
            "base_month_cost": round(base_cost, 2),
            "compare_month_cost": round(compare_cost, 2),
            "delta": delta,
            "delta_pct": pct,
            "status": "savings" if delta < 0 else ("overspend" if delta > 0 else "flat"),
            "currency": currency,
        })
    rows.sort(key=lambda x: abs(x["delta"]), reverse=True)

    return {
        "subscription_id": subscription_id,
        "base_month": base_month,
        "compare_month": compare_month,
        "billing_currency": currency,
        "services": rows,
        "total_savings": round(sum(r["delta"] for r in rows if r["delta"] < 0), 2),
        "total_overspend": round(sum(r["delta"] for r in rows if r["delta"] > 0), 2),
        "source": "database",
    }

"""
Costs router — DB-first reads.

All cost data is read from the local DB (populated by /resources/sync).
Falls back to live Azure Cost Management API only if DB is empty.
"""

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import CostSnapshot, CostByServiceSnapshot, BudgetSnapshot
from ..auth import get_token

log = logging.getLogger(__name__)
router = APIRouter(prefix="/costs", tags=["costs"])


@router.get("/by-service")
def cost_by_service(
    subscription_id: str = Query(...),
    month: str = Query(None, description="YYYY-MM, defaults to current month"),
    db: Session = Depends(get_db),
    token: str  = Depends(get_token),
):
    m = month or date.today().strftime("%Y-%m")
    rows = (
        db.query(CostByServiceSnapshot)
        .filter(
            CostByServiceSnapshot.subscription_id == subscription_id,
            CostByServiceSnapshot.month == m,
        )
        .order_by(CostByServiceSnapshot.cost_usd.desc())
        .all()
    )
    if rows:
        # Return in the same shape the frontend already parses
        return {
            "properties": {
                "columns": [{"name": "ServiceName"}, {"name": "PreTaxCost"}],
                "rows": [[r.service_name, r.cost_usd] for r in rows],
            }
        }
    # Fall back to live
    try:
        from ..azure_cost import AzureCostClient
        client = AzureCostClient(token, subscription_id)
        return client.get_cost_by_service()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/budgets")
def list_budgets(
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
    token: str  = Depends(get_token),
):
    rows = (
        db.query(BudgetSnapshot)
        .filter(BudgetSnapshot.subscription_id == subscription_id)
        .all()
    )
    if rows:
        return [{
            "id":           r.id,
            "name":         r.budget_name,
            "amount":       r.amount,
            "timeGrain":    r.time_grain,
            "currentSpend": r.current_spend,
            "forecastSpend": r.forecast_spend,
            "currency":     r.currency,
            "syncedAt":     r.synced_at.isoformat() if r.synced_at else None,
        } for r in rows]
    # Fall back
    try:
        from ..azure_cost import AzureCostClient
        client = AzureCostClient(token, subscription_id)
        return client.get_budgets()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/trend")
def cost_trend(
    subscription_id: str = Query(...),
    days: int = Query(30),
    db: Session = Depends(get_db),
):
    """Daily cost trend from DB for the last N days."""
    since = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = (
        db.query(
            CostSnapshot.cost_date,
            func.sum(CostSnapshot.cost_usd).label("total"),
        )
        .filter(
            CostSnapshot.subscription_id == subscription_id,
            CostSnapshot.cost_date >= since,
            CostSnapshot.granularity == "Daily",
        )
        .group_by(CostSnapshot.cost_date)
        .order_by(CostSnapshot.cost_date)
        .all()
    )
    return [{"date": r.cost_date, "cost": round(r.total, 2)} for r in rows]

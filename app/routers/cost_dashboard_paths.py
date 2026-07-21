"""Legacy /cost/* paths used by the dashboard — served by the cost service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.cost_db import daily_cost_response_from_db, empty_daily_cost_response
from app.dashboard import get_top_spend
from app.database import get_db
from app.validators import ensure_subscription_known

router = APIRouter(prefix="/cost", tags=["Cost Management"])


def _scoped_subscription(db: Session, subscription_id: str) -> str:
    return ensure_subscription_known(db, subscription_id)


@router.get("/topspend", summary="Top resources by month-to-date cost")
def cost_topspend(
    subscription_id: str = Query(...),
    limit: int = Query(10, ge=1, le=100),
    timeframe: str = Query("MonthToDate"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_top_spend(db, subscription_id, limit=limit, timeframe=timeframe)


@router.get("/daily", summary="Daily cost series")
def cost_daily(
    subscription_id: str = Query(...),
    timeframe: str = Query("MonthToDate"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    db_data = daily_cost_response_from_db(db, subscription_id, timeframe)
    return db_data if db_data else empty_daily_cost_response()

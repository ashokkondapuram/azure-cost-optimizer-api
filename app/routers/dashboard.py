"""Dashboard router — /dashboard, /advisor, /alerts prefixes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.cost_db import daily_cost_response_from_db, empty_daily_cost_response
from app.dashboard import (
    get_dashboard_overview,
    get_resource_detail,
    get_sync_status,
    get_top_spend,
    list_advisor_recommendations,
    list_budgets_from_db,
    list_monitor_alert_resources,
    list_underutil_outliers,
)
from app.database import get_db
from app.validators import ensure_subscription_known

router = APIRouter(tags=["Dashboard"])


def _scoped_subscription(db: Session, subscription_id: str) -> str:
    return ensure_subscription_known(db, subscription_id)


@router.get("/dashboard/overview", summary="Full dashboard payload")
def dashboard_overview(
    subscription_id: str = Query(...),
    timeframe: str = Query("MonthToDate"),
    resource_types: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    from app.resource_type_catalog import parse_resource_types_param
    subscription_id = _scoped_subscription(db, subscription_id)
    types = parse_resource_types_param(resource_types)
    return get_dashboard_overview(db, subscription_id, timeframe=timeframe, resource_types=types)


@router.get("/sync/status", summary="Last sync status per data type")
def dashboard_sync_status(
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_sync_status(db, subscription_id)


@router.get("/cost/topspend", summary="Top resources by month-to-date cost")
def dashboard_cost_topspend(
    subscription_id: str = Query(...),
    limit: int = Query(10, ge=1, le=100),
    timeframe: str = Query("MonthToDate"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_top_spend(db, subscription_id, limit=limit, timeframe=timeframe)


@router.get("/cost/daily", summary="Daily cost series")
def dashboard_cost_daily(
    subscription_id: str = Query(...),
    timeframe: str = Query("MonthToDate"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    db_data = daily_cost_response_from_db(db, subscription_id, timeframe)
    return db_data if db_data else empty_daily_cost_response()


@router.get("/advisor", summary="Cost optimization recommendations (database)")
def dashboard_advisor(
    subscription_id: str = Query(...),
    limit: int = Query(50, ge=1, le=500),
    min_savings: float = Query(0.0, ge=0),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return list_advisor_recommendations(db, subscription_id, limit=limit, min_savings=min_savings)


@router.get("/alerts", summary="Synced metric alert rules")
def dashboard_monitor_alerts(
    subscription_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return list_monitor_alert_resources(db, subscription_id, limit=limit)


@router.get("/outliers/underutil", summary="Top underutilized resources from open findings")
def dashboard_underutil_outliers(
    subscription_id: str = Query(...),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return list_underutil_outliers(db, subscription_id, limit=limit)


@router.get("/budgets", summary="Budgets with current spend (database)")
def dashboard_budgets(
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    from app.budget_service import list_budgets_unified

    subscription_id = _scoped_subscription(db, subscription_id)
    payload = list_budgets_unified(db, subscription_id)
    return payload["budgets"]


@router.get("/resources/detail", summary="Single resource detail by ARM ID (database)")
def dashboard_resource_detail(
    subscription_id: str = Query(...),
    resource_id: str = Query(..., description="Full ARM resource ID"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    detail = get_resource_detail(db, subscription_id, resource_id)
    if not detail:
        raise HTTPException(404, "Resource not found in synced inventory")
    return detail

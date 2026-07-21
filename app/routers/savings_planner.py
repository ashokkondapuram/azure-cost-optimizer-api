"""Savings planner — model commitment scenarios from live Azure spend."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth import get_token
from app.database import get_db
from app.savings_planner_core import build_savings_estimate, sync_savings_planner
from app.user_auth import require_authenticated_user

router = APIRouter(prefix="/savings-planner", tags=["Savings Planner"])


def _auth_dep(request: Request):
    return require_authenticated_user(request)


def _get_db_and_auth(db: Session = Depends(get_db), _=Depends(_auth_dep)):
    return db


def _optional_arm_headers(db: Session) -> dict[str, str] | None:
    try:
        return {"Authorization": f"Bearer {get_token(db)}"}
    except Exception:
        return None


@router.get("/estimate/{subscription_id}")
def savings_planner_estimate(
    subscription_id: str,
    lookback_days: int = Query(30, ge=7, le=90, description="Days of cost data to sum into baseline"),
    categories: str | None = Query(
        None,
        description="Comma-separated category ids to include (vms, aks, sql, storage, appsvcs, other)",
    ),
    include_live_azure: bool = Query(True, description="Query live Azure Cost Management and inventory"),
    db: Session = Depends(_get_db_and_auth),
) -> dict:
    """Return monthly baseline spend by category and savings plan / RI scenarios."""
    selected = [c.strip() for c in (categories or "").split(",") if c.strip()] or None
    headers = _optional_arm_headers(db) if include_live_azure else None
    return build_savings_estimate(
        db,
        subscription_id,
        lookback_days=lookback_days,
        selected_categories=selected,
        headers=headers,
        include_live_azure=include_live_azure,
    )


@router.post("/sync/{subscription_id}")
def savings_planner_sync(
    subscription_id: str,
    lookback_days: int = Query(30, ge=7, le=90),
    categories: str | None = Query(None),
    trigger_advisor_generate: bool = Query(False),
    db: Session = Depends(_get_db_and_auth),
) -> dict:
    """Sync Azure Advisor and refresh live cost + commitment inventory."""
    selected = [c.strip() for c in (categories or "").split(",") if c.strip()] or None
    token = get_token(db)
    return sync_savings_planner(
        db,
        subscription_id,
        token,
        lookback_days=lookback_days,
        selected_categories=selected,
        trigger_advisor_generate=trigger_advisor_generate,
    )

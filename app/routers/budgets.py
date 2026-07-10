"""Budget tracking — define budget thresholds and check current spend against them."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.cost_db import cost_summary_from_db

router = APIRouter(prefix="/budgets", tags=["Budgets"])

# In-memory budget store (replace with DB model in production)
_BUDGETS: dict[str, dict[str, Any]] = {}


class BudgetCreate(BaseModel):
    subscription_id: str
    name: str = Field(..., min_length=1, max_length=128)
    monthly_limit: float = Field(..., gt=0)
    currency: str = Field(default="CAD", max_length=10)
    alert_thresholds: list[float] = Field(
        default=[50.0, 80.0, 100.0],
        description="Alert at these percentage thresholds of the monthly limit",
    )


class BudgetUpdate(BaseModel):
    monthly_limit: float | None = Field(None, gt=0)
    alert_thresholds: list[float] | None = None


def _budget_key(subscription_id: str, name: str) -> str:
    return f"{subscription_id.lower()}::{name.lower()}"


def _evaluate_budget(budget: dict, current_spend: float) -> dict:
    limit = budget["monthly_limit"]
    pct = round((current_spend / limit) * 100, 1) if limit > 0 else 0.0
    triggered = [t for t in budget.get("alert_thresholds", []) if pct >= t]
    status = "ok"
    if pct >= 100:
        status = "exceeded"
    elif pct >= (budget.get("alert_thresholds") or [80])[-1]:
        status = "critical"
    elif triggered:
        status = "warning"
    return {
        **budget,
        "current_spend": round(current_spend, 2),
        "spend_percentage": pct,
        "remaining": round(max(0, limit - current_spend), 2),
        "status": status,
        "triggered_thresholds": triggered,
    }


@router.post("/", status_code=201)
def create_budget(payload: BudgetCreate) -> dict:
    """Create or replace a monthly budget for a subscription."""
    key = _budget_key(payload.subscription_id, payload.name)
    budget = {
        "id": key,
        "subscription_id": payload.subscription_id.lower(),
        "name": payload.name,
        "monthly_limit": payload.monthly_limit,
        "currency": payload.currency,
        "alert_thresholds": sorted(set(payload.alert_thresholds)),
        "created_at": date.today().isoformat(),
    }
    _BUDGETS[key] = budget
    return {"message": "Budget created", "budget": budget}


@router.get("/{subscription_id}")
def list_budgets(
    subscription_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """List all budgets for a subscription with current spend evaluation."""
    sub = subscription_id.lower()
    matching = {k: v for k, v in _BUDGETS.items() if v["subscription_id"] == sub}
    if not matching:
        return {"budgets": [], "message": "No budgets configured. POST /budgets/ to create one."}

    summary = cost_summary_from_db(db, subscription_id, timeframe="MonthToDate")
    current_spend = float((summary or {}).get("pretax_total") or 0)
    currency = (summary or {}).get("billing_currency", "CAD")

    evaluated = [_evaluate_budget(b, current_spend) for b in matching.values()]
    return {
        "subscription_id": subscription_id,
        "billing_currency": currency,
        "current_mtd_spend": round(current_spend, 2),
        "budgets": evaluated,
        "source": "database",
    }


@router.get("/{subscription_id}/{name}/status")
def get_budget_status(
    subscription_id: str,
    name: str,
    db: Session = Depends(get_db),
) -> dict:
    """Get current spend vs. a specific named budget."""
    key = _budget_key(subscription_id, name)
    budget = _BUDGETS.get(key)
    if not budget:
        raise HTTPException(status_code=404, detail=f"Budget '{name}' not found for subscription.")

    summary = cost_summary_from_db(db, subscription_id, timeframe="MonthToDate")
    current_spend = float((summary or {}).get("pretax_total") or 0)
    return _evaluate_budget(budget, current_spend)


@router.patch("/{subscription_id}/{name}")
def update_budget(subscription_id: str, name: str, payload: BudgetUpdate) -> dict:
    """Update an existing budget's limit or alert thresholds."""
    key = _budget_key(subscription_id, name)
    budget = _BUDGETS.get(key)
    if not budget:
        raise HTTPException(status_code=404, detail=f"Budget '{name}' not found.")
    if payload.monthly_limit is not None:
        budget["monthly_limit"] = payload.monthly_limit
    if payload.alert_thresholds is not None:
        budget["alert_thresholds"] = sorted(set(payload.alert_thresholds))
    _BUDGETS[key] = budget
    return {"message": "Budget updated", "budget": budget}


@router.delete("/{subscription_id}/{name}", status_code=204, response_class=Response)
def delete_budget(subscription_id: str, name: str):
    """Delete a budget."""
    key = _budget_key(subscription_id, name)
    if key not in _BUDGETS:
        raise HTTPException(status_code=404, detail=f"Budget '{name}' not found.")
    del _BUDGETS[key]
    return Response(status_code=204)

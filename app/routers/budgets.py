"""Budget tracking — define budget thresholds and check current spend against them."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.budget_custom_store import (
    create_custom_budget,
    delete_custom_budget,
    evaluate_budget,
    get_custom_budget,
    update_custom_budget,
)
from app.budget_service import list_budgets_unified
from app.cost_db import cost_summary_from_db
from app.database import get_db

router = APIRouter(prefix="/budgets", tags=["Budgets"])


class BudgetCreate(BaseModel):
    subscription_id: str
    name: str = Field(..., min_length=1, max_length=128)
    monthly_limit: float = Field(..., gt=0)
    currency: str = Field(default="CAD", max_length=10)
    scope: str = Field(default="subscription", max_length=32)
    period: str = Field(default="monthly", max_length=16)
    alert_thresholds: list[float] = Field(
        default=[50.0, 80.0, 100.0],
        description="Alert at these percentage thresholds of the monthly limit",
    )


class BudgetUpdate(BaseModel):
    monthly_limit: float | None = Field(None, gt=0)
    alert_thresholds: list[float] | None = None
    scope: str | None = None
    period: str | None = None


@router.post("/", status_code=201)
def create_budget(payload: BudgetCreate, db: Session = Depends(get_db)) -> dict:
    """Create or replace a custom monthly budget for a subscription."""
    budget = create_custom_budget(db, payload.model_dump())
    db.commit()
    return {"message": "Budget created", "budget": budget}


@router.get("/{subscription_id}")
def list_budgets(
    subscription_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """List Azure-synced and custom budgets with current spend evaluation."""
    return list_budgets_unified(db, subscription_id)


@router.get("/{subscription_id}/{name}/status")
def get_budget_status(
    subscription_id: str,
    name: str,
    db: Session = Depends(get_db),
) -> dict:
    """Get current spend vs. a specific named custom budget."""
    budget = get_custom_budget(db, subscription_id, name)
    if not budget:
        raise HTTPException(status_code=404, detail=f"Budget '{name}' not found for subscription.")

    summary = cost_summary_from_db(db, subscription_id, timeframe="MonthToDate")
    current_spend = float((summary or {}).get("pretax_total") or 0)
    return evaluate_budget(budget, current_spend)


@router.patch("/{subscription_id}/{name}")
def update_budget(
    subscription_id: str,
    name: str,
    payload: BudgetUpdate,
    db: Session = Depends(get_db),
) -> dict:
    """Update an existing custom budget."""
    budget = update_custom_budget(
        db,
        subscription_id,
        name,
        payload.model_dump(exclude_unset=True),
    )
    if not budget:
        raise HTTPException(status_code=404, detail=f"Budget '{name}' not found.")
    db.commit()
    return {"message": "Budget updated", "budget": budget}


@router.delete("/{subscription_id}/{name}", status_code=204, response_class=Response)
def delete_budget(subscription_id: str, name: str, db: Session = Depends(get_db)):
    """Delete a custom budget."""
    if not delete_custom_budget(db, subscription_id, name):
        raise HTTPException(status_code=404, detail=f"Budget '{name}' not found.")
    db.commit()
    return Response(status_code=204)

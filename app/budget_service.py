"""Unified budget listing — Azure snapshots + custom app budgets."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.budget_custom_store import evaluate_budget, list_custom_budgets
from app.cost_db import cost_summary_from_db


def _period_from_grain(grain: str | None) -> str:
    token = (grain or "Monthly").strip().lower()
    if token.startswith("quarter"):
        return "quarterly"
    if token.startswith("annual"):
        return "annually"
    return "monthly"


def _status_from_pct(pct: float, threshold: float = 80.0) -> str:
    if pct >= 100:
        return "exceeded"
    if pct >= threshold:
        return "alert"
    if pct >= max(threshold - 20, 50):
        return "warning"
    return "ok"


def _normalize_azure_budget(row: dict[str, Any]) -> dict[str, Any]:
    amount = float(row.get("amount") or 0)
    spent = float(row.get("currentSpend") or 0)
    threshold = 80
    pct = round((spent / amount) * 100, 1) if amount > 0 else 0.0
    period = _period_from_grain(row.get("timeGrain"))
    return {
        "id": row.get("id") or row.get("name"),
        "name": row.get("name") or "Budget",
        "scope": "subscription",
        "amount": amount,
        "spent": spent,
        "currentSpend": spent,
        "forecastSpend": float(row.get("forecastSpend") or 0),
        "period": period,
        "timeGrain": row.get("timeGrain") or "Monthly",
        "threshold": threshold,
        "currency": row.get("currency") or "CAD",
        "source": "azure",
        "status": _status_from_pct(pct, threshold),
        "spend_percentage": pct,
        "syncedAt": row.get("syncedAt"),
    }


def _normalize_custom_budget(budget: dict[str, Any], current_spend: float) -> dict[str, Any]:
    evaluated = evaluate_budget(budget, current_spend)
    amount = float(evaluated.get("monthly_limit") or 0)
    spent = float(evaluated.get("current_spend") or 0)
    thresholds = evaluated.get("alert_thresholds") or [80]
    threshold = int(thresholds[-1]) if thresholds else 80
    status_map = {
        "exceeded": "exceeded",
        "critical": "alert",
        "warning": "warning",
        "ok": "ok",
    }
    return {
        "id": evaluated.get("id") or evaluated.get("name"),
        "name": evaluated.get("name") or "Budget",
        "scope": evaluated.get("scope") or "subscription",
        "amount": amount,
        "spent": spent,
        "currentSpend": spent,
        "forecastSpend": None,
        "period": evaluated.get("period") or "monthly",
        "timeGrain": "Monthly",
        "threshold": threshold,
        "currency": evaluated.get("currency") or "CAD",
        "source": "custom",
        "status": status_map.get(evaluated.get("status"), "ok"),
        "spend_percentage": evaluated.get("spend_percentage"),
        "syncedAt": None,
        "alert_thresholds": thresholds,
    }


def list_budgets_unified(db: Session, subscription_id: str) -> dict[str, Any]:
    """Return normalized budgets from DB snapshots and custom store."""
    from app.dashboard.api import list_budgets_from_db

    summary = cost_summary_from_db(db, subscription_id, timeframe="MonthToDate")
    mtd_spend = float((summary or {}).get("pretax_total") or 0)
    currency = (summary or {}).get("billing_currency") or "CAD"

    azure_rows = list_budgets_from_db(db, subscription_id)
    budgets = [_normalize_azure_budget(row) for row in azure_rows]

    for raw in list_custom_budgets(db, subscription_id):
        budgets.append(_normalize_custom_budget(raw, mtd_spend))

    budgets.sort(key=lambda row: (-(row.get("spend_percentage") or 0), row.get("name") or ""))

    return {
        "subscription_id": subscription_id,
        "billing_currency": currency,
        "current_mtd_spend": round(mtd_spend, 2),
        "budgets": budgets,
        "source": "database",
    }

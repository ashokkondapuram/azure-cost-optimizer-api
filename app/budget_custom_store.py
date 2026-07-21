"""Persisted custom budget store (app-defined thresholds)."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import CustomBudget


def budget_key(subscription_id: str, name: str) -> str:
    return f"{subscription_id.lower()}::{name.lower()}"


def _row_to_dict(row: CustomBudget) -> dict[str, Any]:
    try:
        thresholds = json.loads(row.alert_thresholds_json or "[80.0]")
    except json.JSONDecodeError:
        thresholds = [80.0]
    if not isinstance(thresholds, list):
        thresholds = [80.0]
    return {
        "id": row.id,
        "subscription_id": row.subscription_id,
        "name": row.name,
        "scope": row.scope or "subscription",
        "monthly_limit": float(row.monthly_limit or 0),
        "currency": row.currency or "CAD",
        "period": row.period or "monthly",
        "alert_thresholds": [float(t) for t in thresholds],
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def evaluate_budget(budget: dict[str, Any], current_spend: float) -> dict[str, Any]:
    limit = float(budget.get("monthly_limit") or 0)
    pct = round((current_spend / limit) * 100, 1) if limit > 0 else 0.0
    thresholds = budget.get("alert_thresholds") or [80.0]
    triggered = [t for t in thresholds if pct >= t]
    status = "ok"
    if pct >= 100:
        status = "exceeded"
    elif pct >= (thresholds[-1] if thresholds else 80):
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


def create_custom_budget(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    key = budget_key(payload["subscription_id"], payload["name"])
    sub = payload["subscription_id"].lower()
    thresholds = sorted(set(payload.get("alert_thresholds") or [80.0]))
    existing = db.get(CustomBudget, key)
    if existing:
        existing.scope = payload.get("scope") or "subscription"
        existing.monthly_limit = float(payload["monthly_limit"])
        existing.currency = payload.get("currency") or "CAD"
        existing.period = payload.get("period") or "monthly"
        existing.alert_thresholds_json = json.dumps(thresholds)
        row = existing
    else:
        row = CustomBudget(
            id=key,
            subscription_id=sub,
            name=payload["name"],
            scope=payload.get("scope") or "subscription",
            monthly_limit=float(payload["monthly_limit"]),
            currency=payload.get("currency") or "CAD",
            period=payload.get("period") or "monthly",
            alert_thresholds_json=json.dumps(thresholds),
        )
        db.add(row)
    db.flush()
    return _row_to_dict(row)


def list_custom_budgets(db: Session, subscription_id: str) -> list[dict[str, Any]]:
    sub = subscription_id.lower()
    rows = (
        db.query(CustomBudget)
        .filter(CustomBudget.subscription_id == sub)
        .order_by(CustomBudget.name)
        .all()
    )
    return [_row_to_dict(row) for row in rows]


def get_custom_budget(db: Session, subscription_id: str, name: str) -> dict[str, Any] | None:
    row = db.get(CustomBudget, budget_key(subscription_id, name))
    return _row_to_dict(row) if row else None


def update_custom_budget(
    db: Session,
    subscription_id: str,
    name: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    row = db.get(CustomBudget, budget_key(subscription_id, name))
    if not row:
        return None
    if updates.get("monthly_limit") is not None:
        row.monthly_limit = float(updates["monthly_limit"])
    if updates.get("alert_thresholds") is not None:
        row.alert_thresholds_json = json.dumps(sorted(set(updates["alert_thresholds"])))
    if updates.get("scope"):
        row.scope = updates["scope"]
    if updates.get("period"):
        row.period = updates["period"]
    db.flush()
    return _row_to_dict(row)


def delete_custom_budget(db: Session, subscription_id: str, name: str) -> bool:
    row = db.get(CustomBudget, budget_key(subscription_id, name))
    if not row:
        return False
    db.delete(row)
    db.flush()
    return True

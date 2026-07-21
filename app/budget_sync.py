"""Sync Azure Consumption budgets into budget_snapshots."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.models import BudgetSnapshot

log = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _budget_name(raw: dict[str, Any]) -> str:
    name = str(raw.get("name") or "").strip()
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    props = raw.get("properties") if isinstance(raw.get("properties"), dict) else {}
    return name or str(props.get("category") or "budget")


def _amount_value(value: Any) -> float:
    if isinstance(value, dict):
        return float(value.get("amount") or value.get("value") or 0)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_azure_budget(raw: dict[str, Any], subscription_id: str) -> dict[str, Any]:
    props = raw.get("properties") if isinstance(raw.get("properties"), dict) else {}
    name = _budget_name(raw)
    amount = _amount_value(props.get("amount"))
    current = _amount_value(props.get("currentSpend"))
    forecast = _amount_value(props.get("forecastSpend") or props.get("forecast"))
    currency = str(props.get("currency") or props.get("billingCurrency") or "CAD")
    return {
        "id": f"{subscription_id}::azure::{name.lower()}",
        "subscription_id": subscription_id,
        "budget_name": name,
        "amount": amount,
        "time_grain": str(props.get("timeGrain") or "Monthly"),
        "current_spend": current,
        "forecast_spend": forecast,
        "currency": currency,
    }


def sync_budget_snapshots(subscription_id: str, db: Session, token: str) -> int:
    """Fetch Azure budgets and replace cached rows for the subscription."""
    from app.azure_cost import AzureCostClient

    sub = subscription_id.strip().lower()
    client = AzureCostClient(db, token)
    raw_items = client.list_budgets(sub) or []
    parsed = [_parse_azure_budget(item, sub) for item in raw_items if isinstance(item, dict)]

    db.query(BudgetSnapshot).filter(BudgetSnapshot.subscription_id == sub).delete(
        synchronize_session=False,
    )

    now = _now()
    for row in parsed:
        db.add(
            BudgetSnapshot(
                id=row["id"],
                subscription_id=sub,
                budget_name=row["budget_name"],
                amount=row["amount"],
                time_grain=row["time_grain"],
                current_spend=row["current_spend"],
                forecast_spend=row["forecast_spend"],
                currency=row["currency"],
                synced_at=now,
            )
        )

    if not parsed:
        log.info("budget_sync.empty", subscription_id=sub)
        return 0

    log.info("budget_sync.complete", subscription_id=sub, count=len(parsed))
    return len(parsed)

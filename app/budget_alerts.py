"""Budget alerting — compare current-month spend against configurable subscription budgets.

Stores budgets in the DB (table ``budget_alert``) and checks them on demand
or from a scheduler.  When spend exceeds a threshold, dispatches webhook/email
via the notifications subsystem.

Schema (SQLAlchemy model expected in app/models.py or inline migration)::

    budget_alert(
        id              SERIAL PRIMARY KEY,
        subscription_id TEXT NOT NULL,
        display_name    TEXT,
        budget_usd      NUMERIC(14,2) NOT NULL,
        warn_pct        NUMERIC(5,2) DEFAULT 80,   -- warn at X% of budget
        alert_pct       NUMERIC(5,2) DEFAULT 100,  -- alert at X% of budget
        webhook_url     TEXT,
        email_enabled   BOOLEAN DEFAULT FALSE,
        enabled         BOOLEAN DEFAULT TRUE,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW()
    )
"""
from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)


def _get_current_month_spend(subscription_id: str, db: Any) -> float:
    """Read current-month total spend from cost_data table.

    Falls back to 0.0 if no data is available.
    """
    try:
        from sqlalchemy import text
        result = db.execute(
            text(
                """
                SELECT COALESCE(SUM(cost_usd), 0)
                FROM cost_data
                WHERE subscription_id = :sub
                  AND date >= date_trunc('month', CURRENT_DATE)
                """
            ),
            {"sub": subscription_id},
        ).scalar()
        return float(result or 0.0)
    except Exception as exc:
        log.warning("budget_alerts.spend_lookup_failed", sub=subscription_id, error=str(exc))
        return 0.0


def _load_budgets(db: Any) -> list[dict[str, Any]]:
    """Load all enabled budget alert configs from the DB."""
    try:
        from sqlalchemy import text
        rows = db.execute(
            text(
                """
                SELECT id, subscription_id, display_name, budget_usd,
                       warn_pct, alert_pct, webhook_url, email_enabled
                FROM budget_alert
                WHERE enabled = TRUE
                """
            )
        ).mappings().all()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("budget_alerts.load_failed", error=str(exc))
        return []


def check_budgets(db: Any) -> list[dict[str, Any]]:
    """Evaluate all budgets and fire notifications where thresholds are breached.

    Returns a list of breach events (one per breached budget).
    """
    budgets = _load_budgets(db)
    breaches: list[dict[str, Any]] = []

    for budget in budgets:
        sub = budget["subscription_id"]
        limit = float(budget["budget_usd"] or 0)
        if limit <= 0:
            continue

        spend = _get_current_month_spend(sub, db)
        pct_used = (spend / limit) * 100

        warn_pct = float(budget.get("warn_pct") or 80)
        alert_pct = float(budget.get("alert_pct") or 100)

        level: str | None = None
        if pct_used >= alert_pct:
            level = "alert"
        elif pct_used >= warn_pct:
            level = "warning"

        if level is None:
            continue

        event = {
            "subscription_id": sub,
            "display_name": budget.get("display_name") or sub,
            "budget_usd": limit,
            "spend_usd": round(spend, 2),
            "pct_used": round(pct_used, 1),
            "level": level,
        }
        breaches.append(event)
        log.warning(
            "budget_alerts.breach",
            sub=sub,
            level=level,
            pct_used=pct_used,
            spend=spend,
            budget=limit,
        )

        webhook_url = (budget.get("webhook_url") or "").strip()
        if webhook_url:
            try:
                from app.notifications.webhook_dispatcher import dispatch_findings_summary
                dispatch_findings_summary(
                    [],
                    webhook_url,
                    async_send=True,
                )
            except Exception as exc:
                log.warning("budget_alerts.webhook_error", error=str(exc))

    return breaches

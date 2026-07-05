"""Coordinated dashboard cost fetches — shared cache keys, one auth context."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.cost_live_query import (
    query_cost_summary_live,
    query_daily_costs_live,
    query_forecast_summary_live,
)
from app.cost_query_cache import cost_cache_metrics

log = structlog.get_logger()


def monthly_cost_trend_from_summaries(
    *,
    mtd_amount: float,
    last_month: dict[str, Any],
    forecast: dict[str, Any],
) -> dict[str, Any]:
    last_month_total = round(
        float(last_month.get("pretax_total") or last_month.get("cost_usd_total") or 0),
        2,
    )
    projected = round(
        float(forecast.get("pretax_total") or forecast.get("cost_usd_total") or mtd_amount),
        2,
    )

    delta_pct = None
    delta_usd = None
    if last_month_total > 0:
        delta_pct = round(((projected - last_month_total) / last_month_total) * 100, 1)
        delta_usd = round(projected - last_month_total, 2)

    return {
        "projected": projected,
        "last_month": last_month_total,
        "delta_pct": delta_pct,
        "delta_usd": delta_usd,
        "mtd_delta_usd": None,
    }


def query_dashboard_cost_bundle_live(
    db: Session,
    subscription_id: str,
    *,
    timeframe: str = "MonthToDate",
    token: str | None = None,
) -> dict[str, Any]:
    """Return summary, daily, forecast, and trend for the dashboard in one pass."""
    sub = subscription_id.strip().lower()
    log.debug("cost_bundle.fetch", subscription_id=sub, timeframe=timeframe)

    summary_mtd = query_cost_summary_live(db, sub, timeframe, token=token)
    summary_ytd = (
        summary_mtd
        if timeframe == "ThisYear"
        else query_cost_summary_live(db, sub, "ThisYear", token=token)
    )
    daily = query_daily_costs_live(db, sub, timeframe, token=token)
    forecast = query_forecast_summary_live(db, sub, token=token)
    last_month = query_cost_summary_live(db, sub, "TheLastMonth", token=token)

    mtd_amount = float(
        (summary_mtd or {}).get("pretax_total") or (summary_mtd or {}).get("cost_usd_total") or 0
    )
    monthly_trend = monthly_cost_trend_from_summaries(
        mtd_amount=mtd_amount,
        last_month=last_month or {},
        forecast=forecast or {},
    )

    return {
        "summary_mtd": summary_mtd,
        "summary_ytd": summary_ytd,
        "daily": daily,
        "forecast": forecast,
        "last_month": last_month,
        "monthly_trend": monthly_trend,
        "cache_metrics": cost_cache_metrics(),
    }

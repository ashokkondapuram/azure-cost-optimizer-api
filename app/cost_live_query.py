"""Live Azure Cost Management queries for arbitrary date ranges."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.azure_cost import AzureCostClient, CostExportReadError, summarize_cost_response
from app.cost_query_cache import cached_cost_live_query
from app.cost_timeframes import azure_timeframe_payload, period_for_timeframe
from app.http_client import arm_patient_sync

log = structlog.get_logger()


def _scope(subscription_id: str) -> str:
    return f"/subscriptions/{subscription_id.strip().lower()}"


def _with_period(payload: dict[str, Any], timeframe: str, **range_kw) -> dict[str, Any]:
    period = period_for_timeframe(timeframe, **range_kw)
    return {**payload, **period, "timeframe": timeframe}


def query_daily_costs_live(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    token: str | None = None,
) -> dict | None:
    sub = subscription_id.strip().lower()
    return cached_cost_live_query(
        sub,
        "daily",
        timeframe,
        lambda: _query_daily_costs_live_uncached(
            db, sub, timeframe, from_date=from_date, to_date=to_date, token=token,
        ),
        from_date=from_date,
        to_date=to_date,
    )


def _query_daily_costs_live_uncached(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    token: str | None = None,
) -> dict | None:
    from app.auth import arm_auth_context

    sub = subscription_id.strip().lower()
    try:
        with arm_auth_context(db=db, token=token):
            client = AzureCostClient(db=db, token=token)
            with arm_patient_sync():
                tf_payload = azure_timeframe_payload(timeframe, from_date=from_date, to_date=to_date)
                resp = client.query_cost_daily_subscription(
                    sub,
                    timeframe=tf_payload.get("timeframe", "MonthToDate"),
                    **(
                        {"from_date": tf_payload["timePeriod"]["from"], "to_date": tf_payload["timePeriod"]["to"]}
                        if tf_payload.get("timePeriod")
                        else {}
                    ),
                )
    except CostExportReadError as exc:
        log.warning("cost_live.daily_failed", subscription_id=sub, error=str(exc))
        return None
    except Exception as exc:
        log.warning("cost_live.daily_failed", subscription_id=sub, error=str(exc)[:200])
        return None

    from app.azure_cost import daily_subscription_rows_from_response

    rows = daily_subscription_rows_from_response(resp)
    if not rows:
        return None
    currency = resp.get("billing_currency") or rows[0].get("currency") or "CAD"
    out_rows = [
        [round(float(r.get("cost") or 0), 4), round(float(r.get("cost_usd") or 0), 4), "", r.get("date"), currency]
        for r in rows
        if r.get("date")
    ]
    return _with_period(
        {
            "properties": {
                "columns": [
                    {"name": "PreTaxCost"}, {"name": "CostUSD"},
                    {"name": "ResourceGroup"}, {"name": "UsageDate"}, {"name": "Currency"},
                ],
                "rows": out_rows,
            },
            "billing_currency": currency,
            "source": "azure",
        },
        timeframe,
        from_date=from_date,
        to_date=to_date,
    )


def query_cost_by_service_live(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    token: str | None = None,
) -> dict | None:
    sub = subscription_id.strip().lower()
    return cached_cost_live_query(
        sub,
        "by_service",
        timeframe,
        lambda: _query_cost_by_service_live_uncached(
            db, sub, timeframe, from_date=from_date, to_date=to_date, token=token,
        ),
        from_date=from_date,
        to_date=to_date,
    )


def _query_cost_by_service_live_uncached(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    token: str | None = None,
) -> dict | None:
    from app.auth import arm_auth_context

    sub = subscription_id.strip().lower()
    try:
        with arm_auth_context(db=db, token=token):
            client = AzureCostClient(db=db, token=token)
            with arm_patient_sync():
                tf_payload = azure_timeframe_payload(timeframe, from_date=from_date, to_date=to_date)
                resp = client.query_cost_by_service(
                    sub,
                    timeframe=tf_payload.get("timeframe", "MonthToDate"),
                    **(
                        {"from_date": tf_payload["timePeriod"]["from"], "to_date": tf_payload["timePeriod"]["to"]}
                        if tf_payload.get("timePeriod")
                        else {}
                    ),
                )
    except Exception as exc:
        log.warning("cost_live.by_service_failed", subscription_id=sub, error=str(exc)[:200])
        return None

    from app.cost_utils import by_service_properties_from_response

    props = by_service_properties_from_response(resp)
    if not props:
        return None
    currency = resp.get("billing_currency") or "CAD"
    return _with_period(
        {
            "properties": props,
            "billing_currency": currency,
            "source": "azure",
        },
        timeframe,
        from_date=from_date,
        to_date=to_date,
    )


def query_cost_summary_live(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    token: str | None = None,
) -> dict | None:
    sub = subscription_id.strip().lower()
    return cached_cost_live_query(
        sub,
        "summary",
        timeframe,
        lambda: _query_cost_summary_live_uncached(
            db, sub, timeframe, from_date=from_date, to_date=to_date, token=token,
        ),
        from_date=from_date,
        to_date=to_date,
    )


def _query_cost_summary_live_uncached(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    token: str | None = None,
) -> dict | None:
    from app.auth import arm_auth_context

    sub = subscription_id.strip().lower()
    try:
        with arm_auth_context(db=db, token=token):
            client = AzureCostClient(db=db, token=token)
            with arm_patient_sync():
                tf_payload = azure_timeframe_payload(timeframe, from_date=from_date, to_date=to_date)
                resp = client.query_subscription_totals(
                    sub,
                    timeframe=tf_payload.get("timeframe", "MonthToDate"),
                    **(
                        {"from_date": tf_payload["timePeriod"]["from"], "to_date": tf_payload["timePeriod"]["to"]}
                        if tf_payload.get("timePeriod")
                        else {}
                    ),
                )
    except Exception as exc:
        log.warning("cost_live.summary_failed", subscription_id=sub, error=str(exc)[:200])
        return None

    summary = summarize_cost_response(resp)
    if not summary.get("pretax_total") and not summary.get("cost_usd_total"):
        return None
    return _with_period(
        {
            **summary,
            "row_count": 0,
            "total_source": "azure_subscription_query",
            "source": "azure",
        },
        timeframe,
        from_date=from_date,
        to_date=to_date,
    )


def query_cost_by_resource_live(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    token: str | None = None,
) -> dict | None:
    sub = subscription_id.strip().lower()
    return cached_cost_live_query(
        sub,
        "by_resource",
        timeframe,
        lambda: _query_cost_by_resource_live_uncached(db, sub, timeframe, token=token),
    )


def _query_cost_by_resource_live_uncached(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    token: str | None = None,
) -> dict | None:
    from app.auth import arm_auth_context
    from app.cost_utils import by_resource_properties_from_response

    sub = subscription_id.strip().lower()
    try:
        with arm_auth_context(db=db, token=token):
            client = AzureCostClient(db=db, token=token)
            with arm_patient_sync():
                tf_payload = azure_timeframe_payload(timeframe)
                resp = client.query_cost_by_resource(
                    sub,
                    timeframe=tf_payload.get("timeframe", "MonthToDate"),
                )
    except Exception as exc:
        log.warning("cost_live.by_resource_failed", subscription_id=sub, error=str(exc)[:200])
        return None

    props = by_resource_properties_from_response(resp)
    if not props:
        return None
    currency = resp.get("billing_currency") or "CAD"
    return _with_period(
        {
            "properties": props,
            "billing_currency": currency,
            "source": "azure",
        },
        timeframe,
    )


def query_forecast_summary_live(
    db: Session,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    *,
    token: str | None = None,
) -> dict | None:
    sub = subscription_id.strip().lower()
    return cached_cost_live_query(
        sub,
        "forecast",
        timeframe,
        lambda: _query_forecast_summary_live_uncached(db, sub, timeframe, token=token),
    )


def _query_forecast_summary_live_uncached(
    db: Session,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    *,
    token: str | None = None,
) -> dict | None:
    """Month forecast total from Azure Cost Management forecast API."""
    from app.auth import arm_auth_context
    from app.azure_cost import AzureCostClient, normalize_query_response
    from app.cost_utils import summarize_cost_response

    sub = subscription_id.strip().lower()
    try:
        with arm_auth_context(db=db, token=token):
            client = AzureCostClient(db=db, token=token)
            with arm_patient_sync():
                resp = client.query_forecast(sub, timeframe=timeframe)
    except Exception as exc:
        log.warning("cost_live.forecast_failed", subscription_id=sub, error=str(exc)[:200])
        return None

    summary = summarize_cost_response(normalize_query_response(resp))
    if not summary.get("pretax_total") and not summary.get("cost_usd_total"):
        return None
    return {
        **summary,
        "source": "azure",
        "total_source": "azure_forecast",
    }


def _month_start_shift(months_back: int) -> str:
    from datetime import date

    today = date.today()
    year, month = today.year, today.month - months_back
    while month < 1:
        month += 12
        year -= 1
    return date(year, month, 1).isoformat()


def query_monthly_history_live(
    db: Session,
    subscription_id: str,
    *,
    months_back: int = 6,
    token: str | None = None,
) -> dict | None:
    """Monthly actual spend from Azure Cost Management query API."""
    from datetime import date

    sub = subscription_id.strip().lower()
    from_date = _month_start_shift(max(months_back - 1, 0))
    to_date = date.today().isoformat()
    return cached_cost_live_query(
        sub,
        f"monthly_history_{months_back}",
        "Custom",
        lambda: _query_monthly_history_live_uncached(
            db, sub, from_date=from_date, to_date=to_date, token=token,
        ),
        from_date=from_date,
        to_date=to_date,
    )


def _query_monthly_history_live_uncached(
    db: Session,
    subscription_id: str,
    *,
    from_date: str,
    to_date: str,
    token: str | None = None,
) -> dict | None:
    from app.auth import arm_auth_context
    from app.azure_cost import AzureCostClient, monthly_subscription_rows_from_response

    sub = subscription_id.strip().lower()
    try:
        with arm_auth_context(db=db, token=token):
            client = AzureCostClient(db=db, token=token)
            with arm_patient_sync():
                resp = client.query_cost_monthly_subscription(
                    sub, from_date=from_date, to_date=to_date,
                )
    except CostExportReadError as exc:
        log.warning("cost_live.monthly_history_failed", subscription_id=sub, error=str(exc))
        return None
    except Exception as exc:
        log.warning("cost_live.monthly_history_failed", subscription_id=sub, error=str(exc)[:200])
        return None

    rows = monthly_subscription_rows_from_response(resp)
    if not rows:
        return None
    currency = resp.get("billing_currency") or rows[0].get("currency") or "CAD"
    return {
        "timeline": [
            {
                "month": row["month"],
                "total_spend": round(float(row.get("total_spend") or 0), 2),
                "currency": currency,
            }
            for row in rows
        ],
        "billing_currency": currency,
        "source": "azure",
    }


def query_forecast_daily_live(
    db: Session,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    *,
    token: str | None = None,
) -> dict | None:
    sub = subscription_id.strip().lower()
    return cached_cost_live_query(
        sub,
        "forecast_daily",
        timeframe,
        lambda: _query_forecast_daily_live_uncached(db, sub, timeframe, token=token),
    )


def _query_forecast_daily_live_uncached(
    db: Session,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    *,
    token: str | None = None,
) -> dict | None:
    from app.auth import arm_auth_context
    from app.azure_cost import AzureCostClient, daily_subscription_rows_from_response

    sub = subscription_id.strip().lower()
    try:
        with arm_auth_context(db=db, token=token):
            client = AzureCostClient(db=db, token=token)
            with arm_patient_sync():
                resp = client.query_forecast(sub, timeframe=timeframe, granularity="Daily")
    except Exception as exc:
        log.warning("cost_live.forecast_daily_failed", subscription_id=sub, error=str(exc)[:200])
        return None

    if resp.get("error"):
        return None

    rows = daily_subscription_rows_from_response(resp)
    if not rows:
        return None
    currency = resp.get("billing_currency") or rows[0].get("currency") or "CAD"
    return {
        "points": [
            {
                "date": row["date"],
                "cost_billing": round(float(row.get("cost") or 0), 4),
                "cost_usd": round(float(row.get("cost_usd") or 0), 4),
                "currency": currency,
            }
            for row in rows
            if row.get("date")
        ],
        "billing_currency": currency,
        "source": "azure",
        "forecast_source": "azure_cost_management",
    }


def query_cost_explorer_period_live(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    token: str | None = None,
) -> dict | None:
    """Batched live fetch for Cost Explorer (daily + by-service, summary derived)."""
    sub = subscription_id.strip().lower()
    return cached_cost_live_query(
        sub,
        "explorer_period",
        timeframe,
        lambda: _query_cost_explorer_period_live_uncached(
            db, sub, timeframe, from_date=from_date, to_date=to_date, token=token,
        ),
        from_date=from_date,
        to_date=to_date,
    )


def _query_cost_explorer_period_live_uncached(
    db: Session,
    subscription_id: str,
    timeframe: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    token: str | None = None,
) -> dict | None:
    from app.auth import arm_auth_context
    from app.cost_utils import summarize_cost_response

    sub = subscription_id.strip().lower()
    try:
        with arm_auth_context(db=db, token=token):
            client = AzureCostClient(db=db, token=token)
            with arm_patient_sync():
                tf_payload = azure_timeframe_payload(timeframe, from_date=from_date, to_date=to_date)
                period_kw = (
                    {
                        "from_date": tf_payload["timePeriod"]["from"],
                        "to_date": tf_payload["timePeriod"]["to"],
                    }
                    if tf_payload.get("timePeriod")
                    else {}
                )
                tf = tf_payload.get("timeframe", "MonthToDate")
                daily_resp = client.query_cost_daily_subscription(sub, timeframe=tf, **period_kw)
                svc_resp = client.query_cost_by_service(sub, timeframe=tf, **period_kw)
    except CostExportReadError as exc:
        log.warning("cost_live.explorer_period_failed", subscription_id=sub, error=str(exc))
        return None
    except Exception as exc:
        log.warning("cost_live.explorer_period_failed", subscription_id=sub, error=str(exc)[:200])
        return None

    if not daily_resp and not svc_resp:
        return None

    summary = None
    if svc_resp:
        summary = summarize_cost_response(svc_resp)
    elif daily_resp:
        summary = summarize_cost_response(daily_resp)
    if summary:
        summary = {**summary, "source": "azure"}

    currency = (daily_resp or svc_resp or {}).get("billing_currency")
    if not currency and summary:
        currency = summary.get("billing_currency")

    return _with_period(
        {
            "source": "azure",
            "daily": daily_resp,
            "by_service": svc_resp,
            "summary": summary,
            "billing_currency": currency,
        },
        timeframe,
        from_date=from_date,
        to_date=to_date,
    )


def query_demand_forecast_live(
    db: Session,
    subscription_id: str,
    *,
    months_back: int = 6,
    token: str | None = None,
) -> dict[str, Any]:
    """Historical monthly actuals + current-month forecast from Azure Cost Management."""
    from datetime import date

    sub = subscription_id.strip().lower()
    history = query_monthly_history_live(db, sub, months_back=months_back, token=token) or {}
    timeline = list(history.get("timeline") or [])
    currency = history.get("billing_currency") or "CAD"

    forecast_summary = query_forecast_summary_live(db, sub, token=token) or {}
    forecast_daily = query_forecast_daily_live(db, sub, token=token) or {}

    projected = round(
        float(forecast_summary.get("pretax_total") or forecast_summary.get("cost_usd_total") or 0),
        2,
    )
    current_month = date.today().strftime("%Y-%m")
    forecast_rows: list[dict[str, Any]] = []
    if projected > 0:
        forecast_rows.append({
            "month": current_month,
            "predicted_spend": projected,
            "is_forecast": True,
            "source": "azure_forecast",
        })

    last_actual = timeline[-1]["total_spend"] if timeline else None
    delta = round(projected - last_actual, 2) if last_actual is not None and projected else None
    delta_pct = (
        round((delta / last_actual) * 100, 1)
        if delta is not None and last_actual and last_actual > 0
        else None
    )

    return {
        "subscription_id": subscription_id,
        "billing_currency": forecast_summary.get("billing_currency") or currency,
        "timeline": timeline,
        "forecast": forecast_rows,
        "forecast_daily": forecast_daily.get("points") or [],
        "projected_month_end": projected,
        "delta_vs_last_month": delta,
        "delta_pct_vs_last_month": delta_pct,
        "months_back": months_back,
        "forecast_scope": "current_billing_month",
        "source": "azure",
        "forecast_source": "azure_cost_management",
        "history_source": history.get("source") or "azure",
    }

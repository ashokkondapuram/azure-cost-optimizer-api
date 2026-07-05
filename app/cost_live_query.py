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

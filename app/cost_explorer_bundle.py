"""Batched Cost Explorer payload — one round trip for summary, daily, services, and changes."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.cost_resolve import live_range_kw
from app.cost_utils import summarize_cost_response

from app.cost_db import (
    cost_by_service_from_db,
    cost_summary_from_db,
    daily_cost_response_from_db,
    empty_cost_by_service_response,
    empty_daily_cost_response,
    get_latest_cost_changes,
    mtd_period_for_timeframe,
)
from app.cost_explorer_worker import cost_refresh_hours
from app.cost_live_query import query_cost_explorer_period_live

log = structlog.get_logger()


def _empty_summary_for_range(range_kw: dict[str, Any]) -> dict:
    from app.cost_db import empty_cost_summary_response

    return empty_cost_summary_response(
        range_kw.get("timeframe", "MonthToDate"),
        from_date=range_kw.get("from_date"),
        to_date=range_kw.get("to_date"),
    )


def _derive_summary_from_daily(daily_data: dict, *, timeframe: str, range_kw: dict[str, Any]) -> dict | None:
    props = daily_data.get("properties") or {}
    rows = props.get("rows") or []
    if not rows:
        return None
    pretax = 0.0
    usd = 0.0
    currency = daily_data.get("billing_currency") or "CAD"
    for row in rows:
        if not row:
            continue
        pretax += float(row[0] or 0)
        if len(row) > 1:
            usd += float(row[1] or 0)
        if len(row) > 4 and row[4]:
            currency = str(row[4])
    if pretax <= 0 and usd <= 0:
        return None
    period = mtd_period_for_timeframe(
        timeframe,
        from_date=range_kw.get("from_date"),
        to_date=range_kw.get("to_date"),
    )
    return {
        "pretax_total": round(pretax, 2),
        "cost_usd_total": round(usd, 2),
        "billing_currency": currency,
        "row_count": len(rows),
        "total_source": "derived_from_daily",
        "source": daily_data.get("source") or "database",
        **period,
    }


def _derive_summary_from_by_service(by_service_data: dict, *, timeframe: str, range_kw: dict[str, Any]) -> dict | None:
    summary = summarize_cost_response(by_service_data)
    if not summary.get("pretax_total") and not summary.get("cost_usd_total"):
        return None
    period = mtd_period_for_timeframe(
        timeframe,
        from_date=range_kw.get("from_date"),
        to_date=range_kw.get("to_date"),
    )
    props = by_service_data.get("properties") or {}
    return {
        **summary,
        "row_count": len(props.get("rows") or []),
        "total_source": "derived_from_by_service",
        "source": by_service_data.get("source") or "database",
        **period,
    }


def _resolve_period_from_db(
    db: Session,
    *,
    subscription_id: str,
    timeframe: str,
    range_kw: dict[str, Any],
) -> tuple[dict | None, dict | None, dict | None]:
    """Load daily, summary, and by-service from synced database rows only."""
    daily = daily_cost_response_from_db(db, subscription_id, **range_kw)
    summary = cost_summary_from_db(db, subscription_id, **range_kw)
    by_service = cost_by_service_from_db(db, subscription_id, **range_kw)
    if not summary and by_service:
        summary = _derive_summary_from_by_service(by_service, timeframe=timeframe, range_kw=range_kw)
    if not summary and daily:
        summary = _derive_summary_from_daily(daily, timeframe=timeframe, range_kw=range_kw)
    return daily, summary, by_service


def _load_period_from_live(
    db: Session,
    *,
    subscription_id: str,
    timeframe: str,
    range_kw: dict[str, Any],
    live_kw: dict[str, Any],
    token: str | None,
) -> tuple[dict | None, dict | None, dict | None]:
    """Batched live Azure fetch with DB gap-fill (2 Cost Management calls)."""
    batched = query_cost_explorer_period_live(
        db, subscription_id, token=token, **live_kw,
    )
    live_daily = batched.get("daily") if batched else None
    live_by_service = batched.get("by_service") if batched else None
    live_summary = batched.get("summary") if batched else None

    if not live_summary and live_by_service:
        live_summary = _derive_summary_from_by_service(
            live_by_service, timeframe=timeframe, range_kw=range_kw,
        )
    if not live_summary and live_daily:
        live_summary = _derive_summary_from_daily(
            live_daily, timeframe=timeframe, range_kw=range_kw,
        )

    if not (live_daily or live_by_service or live_summary):
        return None, None, None

    daily = live_daily
    summary = live_summary
    by_service = live_by_service
    if not daily or not by_service or not summary:
        db_daily, db_summary, db_by_service = _resolve_period_from_db(
            db,
            subscription_id=subscription_id,
            timeframe=timeframe,
            range_kw=range_kw,
        )
        daily = daily or db_daily
        by_service = by_service or db_by_service
        if not summary:
            summary = db_summary
            if not summary and by_service:
                summary = _derive_summary_from_by_service(
                    by_service, timeframe=timeframe, range_kw=range_kw,
                )
            if not summary and daily:
                summary = _derive_summary_from_daily(
                    daily, timeframe=timeframe, range_kw=range_kw,
                )
    return daily, summary, by_service


def _fetch_period(
    db: Session,
    *,
    subscription_id: str,
    timeframe: str,
    range_kw: dict[str, Any],
    prefer_live: bool,
    token: str | None,
    db_only: bool = False,
) -> tuple[str, dict | None, dict | None, dict | None]:
    """Preference-based resolution: database-first by default; live-first when prefer_live.

    When resource_types is not filtered, one batched live fetch (2 Azure Cost Management
    calls: daily + by-service) supplies explorer sections; summary is derived from
    by-service when absent. Empty live responses are not retried in the same request
    (short-TTL negative cache in cost_query_cache). Database fills any gaps after a
    partial live response; when the database is empty, live Azure is used automatically
    (same as pre-DB-first Cost Explorer).
    """
    if db_only:
        daily, summary, by_service = _resolve_period_from_db(
            db,
            subscription_id=subscription_id,
            timeframe=timeframe,
            range_kw=range_kw,
        )
        if daily or summary or by_service:
            log.info(
                "cost_api.explorer_period",
                subscription_id=subscription_id,
                timeframe=timeframe,
                source="database",
                prefer_live=False,
                has_daily=bool(daily),
                has_summary=bool(summary),
                has_by_service=bool(by_service),
                live_enabled=False,
                batched=False,
                db_only=True,
            )
            return "database", daily, summary, by_service
        log.info(
            "cost_api.explorer_period",
            subscription_id=subscription_id,
            timeframe=timeframe,
            source="database",
            prefer_live=False,
            has_daily=False,
            has_summary=False,
            has_by_service=False,
            live_enabled=False,
            batched=False,
            db_only=True,
        )
        return "database", None, None, None

    live_kw = live_range_kw(range_kw)
    can_query_live = not range_kw.get("resource_types") and bool(token)

    if prefer_live and can_query_live:
        daily, summary, by_service = _load_period_from_live(
            db,
            subscription_id=subscription_id,
            timeframe=timeframe,
            range_kw=range_kw,
            live_kw=live_kw,
            token=token,
        )
        if daily or summary or by_service:
            log.info(
                "cost_api.explorer_period",
                subscription_id=subscription_id,
                timeframe=timeframe,
                source="azure",
                prefer_live=True,
                has_daily=bool(daily),
                has_summary=bool(summary),
                has_by_service=bool(by_service),
                live_enabled=True,
                batched=True,
            )
            return "azure", daily, summary, by_service

    daily, summary, by_service = _resolve_period_from_db(
        db,
        subscription_id=subscription_id,
        timeframe=timeframe,
        range_kw=range_kw,
    )
    if daily or summary or by_service:
        log.info(
            "cost_api.explorer_period",
            subscription_id=subscription_id,
            timeframe=timeframe,
            source="database",
            prefer_live=prefer_live,
            has_daily=bool(daily),
            has_summary=bool(summary),
            has_by_service=bool(by_service),
            live_enabled=can_query_live,
            batched=False,
        )
        return "database", daily, summary, by_service

    if can_query_live:
        daily, summary, by_service = _load_period_from_live(
            db,
            subscription_id=subscription_id,
            timeframe=timeframe,
            range_kw=range_kw,
            live_kw=live_kw,
            token=token,
        )
        if daily or summary or by_service:
            log.info(
                "cost_api.explorer_period",
                subscription_id=subscription_id,
                timeframe=timeframe,
                source="azure",
                prefer_live=False,
                has_daily=bool(daily),
                has_summary=bool(summary),
                has_by_service=bool(by_service),
                live_enabled=True,
                batched=True,
                live_fallback=True,
            )
            return "azure", daily, summary, by_service

    log.info(
        "cost_api.explorer_period",
        subscription_id=subscription_id,
        timeframe=timeframe,
        source="database",
        prefer_live=prefer_live,
        has_daily=False,
        has_summary=False,
        has_by_service=False,
        live_enabled=can_query_live,
        batched=False,
    )
    return "database", None, None, None


def _daily_section(
    subscription_id: str,
    timeframe: str,
    daily_data: dict | None,
    source: str,
) -> dict[str, Any]:
    scope = f"/subscriptions/{subscription_id}"
    if daily_data:
        return {
            "id": None,
            "scope": scope,
            "timeframe": timeframe,
            "granularity": "Daily",
            "data": daily_data,
            "source": source,
        }
    return {
        "id": None,
        "scope": scope,
        "timeframe": timeframe,
        "granularity": "Daily",
        "data": empty_daily_cost_response(),
        "source": "database",
        "sync_required": True,
    }


def _summary_section(
    subscription_id: str,
    timeframe: str,
    summary_data: dict | None,
    source: str,
    range_kw: dict[str, Any],
) -> dict[str, Any]:
    if summary_data:
        return {
            "subscription_id": subscription_id,
            "timeframe": timeframe,
            "api_version": source,
            **summary_data,
        }
    return {
        "subscription_id": subscription_id,
        "timeframe": timeframe,
        "api_version": "database",
        **_empty_summary_for_range(range_kw),
        "sync_required": True,
    }


def _by_service_section(by_service_data: dict | None, source: str) -> dict[str, Any]:
    if by_service_data:
        return {**by_service_data, "source": source}
    return {**empty_cost_by_service_response(), "sync_required": True}


def _cost_sync_meta(db: Session, *, subscription_id: str) -> dict[str, Any]:
    from app.models import CostSyncRun

    row = (
        db.query(CostSyncRun)
        .filter(CostSyncRun.subscription_id == subscription_id.lower())
        .order_by(CostSyncRun.synced_at.desc())
        .first()
    )
    return {
        "last_synced_at": row.synced_at.isoformat() if row and row.synced_at else None,
        "refresh_interval_hours": cost_refresh_hours(),
    }


def _changes_payload(db: Session, *, subscription_id: str) -> dict[str, Any]:
    data = get_latest_cost_changes(db, subscription_id, None)
    if not data:
        period = mtd_period_for_timeframe("MonthToDate")
        return {
            "subscription_id": subscription_id,
            "has_previous": False,
            "services": [],
            **period,
            "source": "database",
        }
    return {"subscription_id": subscription_id, **data}


def build_cost_explorer_bundle(
    db: Session,
    *,
    subscription_id: str,
    timeframe: str,
    range_kw: dict[str, Any],
    prefer_live: bool,
    token: str | None,
    include_changes: bool = True,
    compare_range_kw: dict[str, Any] | None = None,
    compare_timeframe: str | None = None,
    db_only: bool = False,
) -> dict[str, Any]:
    """Return all Cost Explorer sections in one payload."""
    source, daily_data, summary_data, by_service_data = _fetch_period(
        db,
        subscription_id=subscription_id,
        timeframe=timeframe,
        range_kw=range_kw,
        prefer_live=prefer_live,
        token=token,
        db_only=db_only,
    )

    daily = _daily_section(subscription_id, timeframe, daily_data, source)
    summary = _summary_section(subscription_id, timeframe, summary_data, source, range_kw)
    by_service = _by_service_section(by_service_data, source)

    has_any_data = bool(daily_data or summary_data or by_service_data)
    sync_required = source == "database" and not has_any_data

    bundle: dict[str, Any] = {
        "subscription_id": subscription_id,
        "timeframe": timeframe,
        "source": source,
        "sync_required": sync_required,
        "sync": _cost_sync_meta(db, subscription_id=subscription_id),
        "daily": daily,
        "summary": summary,
        "by_service": by_service,
    }

    if include_changes:
        bundle["changes"] = _changes_payload(db, subscription_id=subscription_id)

    if compare_range_kw and compare_timeframe:
        cmp_source, cmp_daily, cmp_summary, _cmp_svc = _fetch_period(
            db,
            subscription_id=subscription_id,
            timeframe=compare_timeframe,
            range_kw=compare_range_kw,
            prefer_live=prefer_live,
            token=token,
            db_only=db_only,
        )
        bundle["compare"] = {
            "timeframe": compare_timeframe,
            "daily": _daily_section(subscription_id, compare_timeframe, cmp_daily, cmp_source),
            "summary": _summary_section(
                subscription_id, compare_timeframe, cmp_summary, cmp_source, compare_range_kw,
            ),
        }

    log.info(
        "cost_api.explorer_bundle",
        subscription_id=subscription_id,
        timeframe=timeframe,
        source=source,
        compare=bool(compare_range_kw),
        prefer_live=prefer_live,
        sync_required=sync_required,
    )
    if sync_required and not prefer_live:
        from app.cost_explorer_worker import request_cost_sync

        request_cost_sync(subscription_id, reason="explorer_bundle_empty")
    elif source == "azure" and not prefer_live:
        from app.cost_explorer_worker import request_cost_sync

        request_cost_sync(subscription_id, reason="explorer_live_fallback")
    return bundle

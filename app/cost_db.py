"""Read cost data persisted from the blob export (per service / resource / day)."""

from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import (
    CostByResourceSnapshot,
    CostByResourceTypeSnapshot,
    CostByServiceSnapshot,
    CostDailyByServiceSnapshot,
    CostSnapshot,
    CostSyncRun,
)
from app.focus_mapping import normalize_arm_id
from app.cost_timeframes import (
    ROLLING_DAILY_TIMEFRAMES as _ROLLING_DAILY_TIMEFRAMES,
    month_for_timeframe as _month_for_timeframe,
    period_for_timeframe,
    resolve_date_range,
)

# Timeframes where substituting a different calendar month would misstate spend.
_PERIOD_SCOPED_TIMEFRAMES = frozenset({
    "MonthToDate",
    "BillingMonthToDate",
    "TheLastMonth",
    "ThisQuarter",
    "LastQuarter",
    "Last3Months",
    "Last6Months",
    "Last12Months",
    "ThisYear",
    "Custom",
}) | _ROLLING_DAILY_TIMEFRAMES
_CALENDAR_MTD_TIMEFRAMES = frozenset({"MonthToDate", "BillingMonthToDate"})
_MONTH_BUCKET_TIMEFRAMES = frozenset({"MonthToDate", "BillingMonthToDate", "TheLastMonth"})
_ROLLING_DAILY_TIMEFRAMES = _ROLLING_DAILY_TIMEFRAMES
_MULTI_MONTH_TIMEFRAMES = frozenset({
    "ThisYear",
    "Last12Months",
    "Last6Months",
    "Last3Months",
    "ThisQuarter",
    "LastQuarter",
})


def _normalize_sub(subscription_id: str) -> str:
    return (subscription_id or "").strip().lower()


def _billing_currency_from_rows(rows, *, attr: str = "billing_currency", fallback: str = "CAD") -> str:
    for row in rows or []:
        val = getattr(row, attr, None)
        if not val and hasattr(row, "currency"):
            val = row.currency
        if val:
            return str(val)
    return fallback


def _subscription_billing_currency_uncached(
    db: Session,
    subscription_id: str,
    *,
    model=CostDailyByServiceSnapshot,
) -> str:
    sub = _normalize_sub(subscription_id)
    row = (
        db.query(model.billing_currency)
        .filter(model.subscription_id == sub, model.billing_currency.isnot(None))
        .first()
    )
    return (row[0] if row else None) or "CAD"


def subscription_billing_currency(
    db: Session,
    subscription_id: str,
    *,
    model=CostDailyByServiceSnapshot,
) -> str:
    """Cached default billing currency for a subscription."""
    from app.perf_cache import cached_cost_map

    sub = _normalize_sub(subscription_id)
    key = f"billing_currency:{sub}:{model.__tablename__}"
    return cached_cost_map(
        key,
        lambda: _subscription_billing_currency_uncached(db, sub, model=model),
    )


def month_for_timeframe(
    timeframe: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
) -> str:
    return _month_for_timeframe(timeframe, from_date=from_date, to_date=to_date)


def _date_range_for_timeframe(
    timeframe: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
) -> tuple[date, date]:
    return resolve_date_range(timeframe, from_date=from_date, to_date=to_date)


def mtd_period_for_timeframe(
    timeframe: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, str]:
    """Inclusive period metadata for API responses."""
    return period_for_timeframe(timeframe, from_date=from_date, to_date=to_date)


def _expanded_resource_types(resource_types: list[str] | None) -> set[str] | None:
    """Expand filter tokens; full catalog selection is treated as no filter."""
    from app.resource_type_catalog import all_canonical_resource_types, expand_resource_type_filter

    expanded = expand_resource_type_filter(resource_types)
    if not expanded:
        return None
    all_catalog = set(all_canonical_resource_types())
    if all_catalog and expanded >= all_catalog:
        return None
    return expanded


def _resource_type_match_filter(canonicals: set[str]):
    """Match cost rows by canonical id and/or ARM provider type."""
    arm_types = _arm_types_for_canonicals(canonicals)
    clauses = []
    if canonicals:
        clauses.append(CostByResourceTypeSnapshot.canonical_resource_type.in_(list(canonicals)))
    if arm_types:
        clauses.append(CostByResourceTypeSnapshot.arm_resource_type.in_(list(arm_types)))
    return or_(*clauses) if clauses else None


def _arm_types_for_canonicals(canonicals: set[str]) -> set[str]:
    from app.resource_type_map import ARM_PROVIDER_TO_INTERNAL

    return {arm for arm, canon in ARM_PROVIDER_TO_INTERNAL.items() if canon in canonicals}


def _arm_resource_types_for_filter(
    db: Session,
    subscription_id: str,
    month: str,
    canonicals: set[str],
) -> set[str]:
    """Resolve canonical filter tokens to ARM provider/types present in cost data."""
    sub = _normalize_sub(subscription_id)
    arm_types = set(_arm_types_for_canonicals(canonicals))
    type_match = _resource_type_match_filter(canonicals)
    if type_match is not None:
        snap_arms = (
            db.query(CostByResourceTypeSnapshot.arm_resource_type)
            .filter(
                CostByResourceTypeSnapshot.subscription_id == sub,
                CostByResourceTypeSnapshot.month == month,
                type_match,
            )
            .distinct()
            .all()
        )
        arm_types |= {(r[0] or "").strip().lower() for r in snap_arms if r[0]}
    return arm_types


def _service_names_for_resource_types(
    db: Session,
    subscription_id: str,
    month: str,
    canonicals: set[str],
) -> set[str]:
    from app.cost_utils import service_label_for_arm_type

    sub = _normalize_sub(subscription_id)
    arm_types = _arm_resource_types_for_filter(db, subscription_id, month, canonicals)
    if not arm_types:
        return set()

    rows = (
        db.query(CostByResourceSnapshot.service_name)
        .filter(
            CostByResourceSnapshot.subscription_id == sub,
            CostByResourceSnapshot.month == month,
            CostByResourceSnapshot.resource_type.in_(list(arm_types)),
        )
        .distinct()
        .all()
    )
    names = {r[0] for r in rows if r[0]}
    if not names:
        names = {service_label_for_arm_type(arm) for arm in arm_types}
        names.discard("")
    return names


def _summary_from_resource_type_snapshots(
    db: Session,
    subscription_id: str,
    month: str,
    canonicals: set[str],
    *,
    timeframe: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict | None:
    sub = _normalize_sub(subscription_id)
    type_match = _resource_type_match_filter(canonicals)
    query = db.query(CostByResourceTypeSnapshot).filter(
        CostByResourceTypeSnapshot.subscription_id == sub,
        CostByResourceTypeSnapshot.month == month,
    )
    if type_match is not None:
        query = query.filter(type_match)
    rows = query.all()
    if not rows:
        return None
    pretax = sum(r.cost_billing or 0.0 for r in rows)
    usd = sum(r.cost_usd or 0.0 for r in rows)
    billing_currency = rows[0].billing_currency or "CAD"
    period_meta = mtd_period_for_timeframe(timeframe, from_date=from_date, to_date=to_date)
    return {
        "pretax_total": round(pretax, 2),
        "cost_usd_total": round(usd, 2),
        "billing_currency": billing_currency,
        "row_count": len(rows),
        "total_source": "resource_type_rows_sum",
        "source": "database",
        "month": month,
        "resource_types": sorted(canonicals),
        **period_meta,
    }


def has_synced_service_costs(
    db: Session,
    subscription_id: str,
    month: str | None = None,
) -> bool:
    sub = _normalize_sub(subscription_id)
    m = month or date.today().strftime("%Y-%m")
    return (
        db.query(CostByServiceSnapshot.id)
        .filter(
            CostByServiceSnapshot.subscription_id == sub,
            CostByServiceSnapshot.month == m,
        )
        .first()
        is not None
    )


def daily_cost_response_from_db(
    db: Session,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    resource_types: list[str] | None = None,
) -> dict | None:
    """Daily subscription spend from cost_daily_by_service (summed across services)."""
    sub = _normalize_sub(subscription_id)
    start, end = _date_range_for_timeframe(timeframe, from_date=from_date, to_date=to_date)
    type_filter = _expanded_resource_types(resource_types)
    service_names: set[str] | None = None
    if type_filter:
        month = month_for_timeframe(timeframe, from_date=from_date, to_date=to_date)
        service_names = _service_names_for_resource_types(db, sub, month, type_filter)
        if not service_names:
            return None

    daily_query = (
        db.query(
            CostDailyByServiceSnapshot.cost_date,
            func.sum(CostDailyByServiceSnapshot.cost_billing).label("pretax"),
            func.sum(CostDailyByServiceSnapshot.cost_usd).label("usd"),
        )
        .filter(
            CostDailyByServiceSnapshot.subscription_id == sub,
            CostDailyByServiceSnapshot.cost_date >= start.isoformat(),
            CostDailyByServiceSnapshot.cost_date <= end.isoformat(),
        )
    )
    if service_names is not None:
        daily_query = daily_query.filter(
            CostDailyByServiceSnapshot.service_name.in_(list(service_names)),
        )
    else:
        has_rollup = (
            db.query(CostDailyByServiceSnapshot.id)
            .filter(
                CostDailyByServiceSnapshot.subscription_id == sub,
                CostDailyByServiceSnapshot.cost_date >= start.isoformat(),
                CostDailyByServiceSnapshot.cost_date <= end.isoformat(),
                CostDailyByServiceSnapshot.service_name == "__subscription__",
            )
            .limit(1)
            .first()
        )
        if has_rollup:
            daily_query = daily_query.filter(
                CostDailyByServiceSnapshot.service_name == "__subscription__",
            )
        else:
            daily_query = daily_query.filter(
                CostDailyByServiceSnapshot.service_name != "__subscription__",
            )
    rows = daily_query.group_by(CostDailyByServiceSnapshot.cost_date).order_by(
        CostDailyByServiceSnapshot.cost_date,
    ).all()
    if not rows:
        # Fallback to RG-level snapshots if daily-by-service not populated yet.
        rg_rows = (
            db.query(CostSnapshot)
            .filter(
                CostSnapshot.subscription_id == sub,
                CostSnapshot.granularity == "Daily",
                CostSnapshot.cost_date >= start.isoformat(),
                CostSnapshot.cost_date <= end.isoformat(),
            )
            .order_by(CostSnapshot.cost_date)
            .all()
        )
        if not rg_rows:
            return None
        by_date: dict[str, dict] = {}
        currency = "CAD"
        for r in rg_rows:
            bucket = by_date.setdefault(r.cost_date, {"pretax": 0.0, "usd": 0.0})
            bucket["pretax"] += r.cost_billing if r.cost_billing is not None else r.cost_usd
            bucket["usd"] += r.cost_usd
            currency = r.currency or currency
        columns = [
            {"name": "PreTaxCost"}, {"name": "CostUSD"},
            {"name": "ResourceGroup"}, {"name": "UsageDate"}, {"name": "Currency"},
        ]
        out_rows = [
            [round(v["pretax"], 4), round(v["usd"], 4), "", d, currency]
            for d, v in sorted(by_date.items())
        ]
        return {
            "properties": {"columns": columns, "rows": out_rows},
            "billing_currency": currency,
            "source": "database",
            **period_for_timeframe(timeframe, from_date=from_date, to_date=to_date),
        }

    currency = subscription_billing_currency(db, sub)
    columns = [
        {"name": "PreTaxCost"}, {"name": "CostUSD"},
        {"name": "ResourceGroup"}, {"name": "UsageDate"}, {"name": "Currency"},
    ]
    out_rows = [
        [round(r.pretax or 0, 4), round(r.usd or 0, 4), "", r.cost_date, currency]
        for r in rows
    ]
    return {
        "properties": {"columns": columns, "rows": out_rows},
        "billing_currency": currency,
        "source": "database",
        **period_for_timeframe(timeframe, from_date=from_date, to_date=to_date),
    }


def _service_breakdown_from_daily(
    db: Session,
    subscription_id: str,
    start: date,
    end: date,
    *,
    service_names: set[str] | None = None,
) -> dict | None:
    sub = _normalize_sub(subscription_id)
    query = (
        db.query(
            CostDailyByServiceSnapshot.service_name,
            func.sum(CostDailyByServiceSnapshot.cost_billing).label("pretax"),
            func.sum(CostDailyByServiceSnapshot.cost_usd).label("usd"),
        )
        .filter(
            CostDailyByServiceSnapshot.subscription_id == sub,
            CostDailyByServiceSnapshot.cost_date >= start.isoformat(),
            CostDailyByServiceSnapshot.cost_date <= end.isoformat(),
            CostDailyByServiceSnapshot.service_name != "__subscription__",
        )
    )
    if service_names is not None:
        query = query.filter(CostDailyByServiceSnapshot.service_name.in_(list(service_names)))
    rows = query.group_by(CostDailyByServiceSnapshot.service_name).order_by(
        func.sum(CostDailyByServiceSnapshot.cost_billing).desc(),
    ).all()
    if not rows:
        return None
    currency = _billing_currency_from_rows(
        rows,
        fallback=subscription_billing_currency(db, sub),
    )
    return {
        "properties": {
            "columns": [
                {"name": "ServiceName"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [
                [r.service_name, round(float(r.pretax or 0), 4), round(float(r.usd or 0), 4), currency]
                for r in rows
            ],
        },
        "billing_currency": currency,
        "source": "database",
    }


def _month_last_day(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def _spans_multiple_months(start: date, end: date) -> bool:
    return (start.year, start.month) != (end.year, end.month)


def _iter_month_slices(start: date, end: date):
    """Yield (YYYY-MM, slice_start, slice_end) for each calendar month in [start, end]."""
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        month_start = date(year, month, 1)
        month_end = _month_last_day(year, month)
        yield f"{year:04d}-{month:02d}", max(start, month_start), min(end, month_end)
        month += 1
        if month > 12:
            month = 1
            year += 1


def _apply_daily_cost_scope(
    query,
    db: Session,
    sub: str,
    start: date,
    end: date,
    *,
    service_names: set[str] | None,
):
    """Prefer subscription rollup rows when present to avoid double-counting."""
    if service_names is not None:
        return query.filter(CostDailyByServiceSnapshot.service_name.in_(list(service_names)))
    has_rollup = (
        db.query(CostDailyByServiceSnapshot.id)
        .filter(
            CostDailyByServiceSnapshot.subscription_id == sub,
            CostDailyByServiceSnapshot.cost_date >= start.isoformat(),
            CostDailyByServiceSnapshot.cost_date <= end.isoformat(),
            CostDailyByServiceSnapshot.service_name == "__subscription__",
        )
        .limit(1)
        .first()
    )
    if has_rollup:
        return query.filter(CostDailyByServiceSnapshot.service_name == "__subscription__")
    return query.filter(CostDailyByServiceSnapshot.service_name != "__subscription__")


def _summary_from_daily(
    db: Session,
    subscription_id: str,
    start: date,
    end: date,
    *,
    service_names: set[str] | None = None,
) -> dict | None:
    sub = _normalize_sub(subscription_id)
    query = (
        db.query(
            func.sum(CostDailyByServiceSnapshot.cost_billing).label("pretax"),
            func.sum(CostDailyByServiceSnapshot.cost_usd).label("usd"),
        )
        .filter(
            CostDailyByServiceSnapshot.subscription_id == sub,
            CostDailyByServiceSnapshot.cost_date >= start.isoformat(),
            CostDailyByServiceSnapshot.cost_date <= end.isoformat(),
        )
    )
    query = _apply_daily_cost_scope(query, db, sub, start, end, service_names=service_names)
    row = query.first()
    if not row or (not row.pretax and not row.usd):
        return None
    currency = subscription_billing_currency(db, sub)
    service_count = (
        db.query(func.count(func.distinct(CostDailyByServiceSnapshot.service_name)))
        .filter(
            CostDailyByServiceSnapshot.subscription_id == sub,
            CostDailyByServiceSnapshot.cost_date >= start.isoformat(),
            CostDailyByServiceSnapshot.cost_date <= end.isoformat(),
            CostDailyByServiceSnapshot.service_name != "__subscription__",
        )
        .scalar()
    ) or 0
    return {
        "pretax_total": round(float(row.pretax or 0), 2),
        "cost_usd_total": round(float(row.usd or 0), 2),
        "billing_currency": currency,
        "row_count": int(service_count),
        "total_source": "daily_rows_sum",
        "source": "database",
    }


def _uses_monthly_service_snapshot(timeframe: str, start: date, end: date) -> bool:
    """Only the prior full calendar month is served from month-keyed service snapshots."""
    return (timeframe or "").strip() == "TheLastMonth"


def get_latest_cost_changes(
    db: Session,
    subscription_id: str,
    month: str | None = None,
) -> dict | None:
    """Service-level MTD increases since the previous Fetch costs run."""
    sub = _normalize_sub(subscription_id)
    m = month or date.today().strftime("%Y-%m")
    run = (
        db.query(CostSyncRun)
        .filter(CostSyncRun.subscription_id == sub, CostSyncRun.month == m)
        .order_by(CostSyncRun.synced_at.desc())
        .first()
    )
    if not run:
        return None
    try:
        services = json.loads(run.changes_json or "[]")
    except json.JSONDecodeError:
        services = []
    return {
        "month": run.month,
        "mtd_start": run.mtd_start,
        "mtd_end": run.mtd_end,
        "synced_at": run.synced_at.isoformat() if run.synced_at else None,
        "previous_synced_at": run.previous_synced_at.isoformat() if run.previous_synced_at else None,
        "has_previous": run.previous_synced_at is not None,
        "total_billing": run.total_billing,
        "total_delta_billing": round(sum(s.get("delta_billing", 0) for s in services), 2),
        "total_delta_usd": round(sum(s.get("delta_usd", 0) for s in services), 2),
        "billing_currency": run.billing_currency or "CAD",
        "services": services,
        "source": "database",
    }


def daily_cost_by_resource_group_from_db(
    db: Session,
    subscription_id: str,
    resource_group: str,
    timeframe: str = "MonthToDate",
    *,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict | None:
    """Daily spend for one resource group from synced cost_snapshots."""
    sub = _normalize_sub(subscription_id)
    start, end = _date_range_for_timeframe(timeframe, from_date=from_date, to_date=to_date)
    rg = (resource_group or "").strip().lower()
    rows = (
        db.query(CostSnapshot)
        .filter(
            CostSnapshot.subscription_id == sub,
            CostSnapshot.granularity == "Daily",
            func.lower(CostSnapshot.resource_group) == rg,
            CostSnapshot.cost_date >= start.isoformat(),
            CostSnapshot.cost_date <= end.isoformat(),
        )
        .order_by(CostSnapshot.cost_date)
        .all()
    )
    if not rows:
        return None
    currency = rows[0].currency or "CAD"
    columns = [
        {"name": "PreTaxCost"}, {"name": "CostUSD"},
        {"name": "ResourceGroup"}, {"name": "UsageDate"}, {"name": "Currency"},
    ]
    out_rows = [
        [
            round(r.cost_billing if r.cost_billing is not None else r.cost_usd, 4),
            round(r.cost_usd, 4),
            resource_group,
            r.cost_date,
            r.currency or currency,
        ]
        for r in rows
    ]
    return {
        "properties": {"columns": columns, "rows": out_rows},
        "billing_currency": currency,
        "source": "database",
    }


def _latest_cost_by_resource_month(db: Session, subscription_id: str) -> str | None:
    sub = _normalize_sub(subscription_id)
    return (
        db.query(func.max(CostByResourceSnapshot.month))
        .filter(CostByResourceSnapshot.subscription_id == sub)
        .scalar()
    )


def _month_has_cost_data(db: Session, subscription_id: str, month: str) -> bool:
    """True when any persisted cost table has rows for this subscription month."""
    sub = _normalize_sub(subscription_id)
    if (
        db.query(CostByServiceSnapshot.id)
        .filter(CostByServiceSnapshot.subscription_id == sub, CostByServiceSnapshot.month == month)
        .first()
    ):
        return True
    if (
        db.query(CostByResourceSnapshot.id)
        .filter(CostByResourceSnapshot.subscription_id == sub, CostByResourceSnapshot.month == month)
        .first()
    ):
        return True
    if (
        db.query(CostByResourceTypeSnapshot.id)
        .filter(CostByResourceTypeSnapshot.subscription_id == sub, CostByResourceTypeSnapshot.month == month)
        .first()
    ):
        return True
    if (
        db.query(CostSyncRun.id)
        .filter(CostSyncRun.subscription_id == sub, CostSyncRun.month == month)
        .first()
    ):
        return True
    return False


def _resolve_cost_month(
    db: Session,
    subscription_id: str,
    timeframe: str,
    month: str | None,
) -> str | None:
    m = month or month_for_timeframe(timeframe)
    if _month_has_cost_data(db, subscription_id, m):
        return m
    if month is not None:
        return None
    if (timeframe or "").strip() in _PERIOD_SCOPED_TIMEFRAMES:
        return None
    return (
        _latest_cost_by_resource_month(db, subscription_id)
        or _latest_synced_month(db, subscription_id)
        or _latest_cost_sync_month(db, subscription_id)
    )


def _resolve_resource_cost_month(
    db: Session,
    subscription_id: str,
    timeframe: str,
    month: str | None,
) -> str | None:
    """Month key for per-resource reads — prefers cost_by_resource rows."""
    sub = _normalize_sub(subscription_id)
    m = month or month_for_timeframe(timeframe)
    if month is not None:
        return m
    if (
        db.query(CostByResourceSnapshot.id)
        .filter(
            CostByResourceSnapshot.subscription_id == sub,
            CostByResourceSnapshot.month == m,
        )
        .first()
    ):
        return m
    if (timeframe or "").strip() in _PERIOD_SCOPED_TIMEFRAMES:
        return None
    latest = _latest_cost_by_resource_month(db, subscription_id)
    if latest:
        return latest
    return _resolve_cost_month(db, subscription_id, timeframe, month)


def resource_cost_map_from_db(
    db: Session,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    month: str | None = None,
) -> dict[str, dict]:
    """MTD per-resource costs keyed by normalized ARM resource ID."""
    sub = _normalize_sub(subscription_id)
    m = _resolve_resource_cost_month(db, subscription_id, timeframe, month)
    if not m:
        return {}
    rows = (
        db.query(CostByResourceSnapshot)
        .filter(
            CostByResourceSnapshot.subscription_id == sub,
            CostByResourceSnapshot.month == m,
        )
        .all()
    )
    if not rows and month is None:
        latest = _latest_cost_by_resource_month(db, subscription_id)
        if latest and latest != m:
            return resource_cost_map_from_db(db, subscription_id, timeframe, month=latest)
    out: dict[str, dict] = {}
    for r in rows:
        rid = normalize_arm_id(r.resource_id)
        if not rid:
            continue
        out[rid] = {
            "pretax": float(r.cost_billing or 0.0),
            "usd": float(r.cost_usd or 0.0),
            "currency": r.billing_currency or "CAD",
            "service_name": r.service_name or "Other",
        }
    return out


def _prior_month(month: str) -> str | None:
    try:
        year_s, mon_s = month.split("-", 1)
        year, mon = int(year_s), int(mon_s)
    except (TypeError, ValueError):
        return None
    if mon <= 1:
        return f"{year - 1}-12"
    return f"{year}-{mon - 1:02d}"


def resource_lifetime_cost_map_from_db(db: Session, subscription_id: str) -> dict[str, dict]:
    """Cumulative billed cost per resource across all synced months."""
    sub = _normalize_sub(subscription_id)
    rows = (
        db.query(
            CostByResourceSnapshot.resource_id,
            func.coalesce(func.sum(CostByResourceSnapshot.cost_billing), 0.0),
            func.coalesce(func.sum(CostByResourceSnapshot.cost_usd), 0.0),
            func.max(CostByResourceSnapshot.billing_currency),
        )
        .filter(CostByResourceSnapshot.subscription_id == sub)
        .group_by(CostByResourceSnapshot.resource_id)
        .all()
    )
    out: dict[str, dict] = {}
    for rid, billing, usd, currency in rows:
        norm = normalize_arm_id(rid)
        if not norm:
            continue
        out[norm] = {
            "pretax": round(float(billing or 0.0), 2),
            "usd": round(float(usd or 0.0), 2),
            "currency": currency or "CAD",
        }
    return out


def resource_cost_mom_delta_map_from_db(db: Session, subscription_id: str) -> dict[str, dict]:
    """Month-over-month billing delta (current MTD month vs prior month)."""
    sub = _normalize_sub(subscription_id)
    month = _resolve_cost_month(db, subscription_id, "MonthToDate", None)
    prior = _prior_month(month) if month else None
    if not month or not prior:
        return {}
    rows = (
        db.query(
            CostByResourceSnapshot.resource_id,
            CostByResourceSnapshot.month,
            func.coalesce(func.sum(CostByResourceSnapshot.cost_billing), 0.0).label("billing"),
            func.max(CostByResourceSnapshot.billing_currency).label("currency"),
        )
        .filter(
            CostByResourceSnapshot.subscription_id == sub,
            CostByResourceSnapshot.month.in_([month, prior]),
        )
        .group_by(CostByResourceSnapshot.resource_id, CostByResourceSnapshot.month)
        .all()
    )
    current: dict[str, tuple[float, str | None]] = {}
    previous: dict[str, float] = {}
    for rid, row_month, billing, currency in rows:
        norm = normalize_arm_id(rid)
        if not norm:
            continue
        if row_month == month:
            current[norm] = (float(billing or 0.0), currency)
        elif row_month == prior:
            previous[norm] = float(billing or 0.0)
    out: dict[str, dict] = {}
    for rid in set(current) | set(previous):
        cur, currency = current.get(rid, (0.0, None))
        prev = previous.get(rid, 0.0)
        delta = round(cur - prev, 2)
        if cur == 0 and prev == 0:
            continue
        out[rid] = {
            "billing_delta": delta,
            "currency": currency or "CAD",
        }
    return out


def resource_cost_overlays_from_db(db: Session, subscription_id: str) -> dict[str, dict]:
    """MTD, lifetime, and MoM cost overlays loaded together for list endpoints."""
    sub = _normalize_sub(subscription_id)
    return {
        "mtd": resource_cost_map_from_db(db, sub),
        "lifetime": resource_lifetime_cost_map_from_db(db, sub),
        "mom": resource_cost_mom_delta_map_from_db(db, sub),
    }


def empty_daily_cost_response(billing_currency: str = "CAD") -> dict:
    return {
        "properties": {
            "columns": [
                {"name": "PreTaxCost"}, {"name": "CostUSD"},
                {"name": "ResourceGroup"}, {"name": "UsageDate"}, {"name": "Currency"},
            ],
            "rows": [],
        },
        "billing_currency": billing_currency,
        "source": "database",
        "sync_required": True,
    }


def empty_cost_by_service_response(billing_currency: str = "CAD") -> dict:
    return {
        "properties": {
            "columns": [
                {"name": "ServiceName"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [],
        },
        "billing_currency": billing_currency,
        "source": "database",
        "sync_required": True,
    }


def empty_cost_by_resource_response(billing_currency: str = "CAD") -> dict:
    return {
        "properties": {
            "columns": [
                {"name": "ResourceId"},
                {"name": "ResourceType"},
                {"name": "ResourceGroup"},
                {"name": "ServiceName"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [],
        },
        "billing_currency": billing_currency,
        "source": "database",
        "sync_required": True,
    }


def empty_cost_summary_response(
    timeframe: str = "MonthToDate",
    *,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    period = mtd_period_for_timeframe(timeframe, from_date=from_date, to_date=to_date)
    return {
        "pretax_total": 0.0,
        "cost_usd_total": 0.0,
        "billing_currency": "CAD",
        "row_count": 0,
        "source": "database",
        "sync_required": True,
        **period,
    }


def _latest_synced_month(db: Session, subscription_id: str) -> str | None:
    sub = _normalize_sub(subscription_id)
    return (
        db.query(func.max(CostByServiceSnapshot.month))
        .filter(CostByServiceSnapshot.subscription_id == sub)
        .scalar()
    )


def _latest_cost_sync_month(db: Session, subscription_id: str) -> str | None:
    sub = _normalize_sub(subscription_id)
    return (
        db.query(func.max(CostSyncRun.month))
        .filter(CostSyncRun.subscription_id == sub)
        .scalar()
    )


def subscription_mtd_from_sync_run(
    db: Session,
    subscription_id: str,
    month: str,
) -> dict | None:
    """Authoritative subscription MTD from the latest Cost Management subscription-total query."""
    sub = _normalize_sub(subscription_id)
    run = (
        db.query(CostSyncRun)
        .filter(
            CostSyncRun.subscription_id == sub,
            CostSyncRun.month == month,
        )
        .order_by(CostSyncRun.synced_at.desc())
        .first()
    )
    if not run:
        return None
    return {
        "pretax_total": round(float(run.total_billing or 0.0), 2),
        "cost_usd_total": round(float(run.total_usd or 0.0), 2),
        "billing_currency": run.billing_currency or "CAD",
        "mtd_start": run.mtd_start,
        "mtd_end": run.mtd_end,
        "synced_at": run.synced_at.isoformat() if run.synced_at else None,
        "total_source": "azure_subscription_query",
        "source": "database",
        "month": month,
    }


def _summary_from_service_month(
    db: Session,
    subscription_id: str,
    month: str,
    *,
    service_names: set[str] | None = None,
) -> dict | None:
    """Sum synced per-service rows for one calendar month (last-resort fallback)."""
    sub = _normalize_sub(subscription_id)
    query = (
        db.query(
            func.sum(CostByServiceSnapshot.cost_billing).label("pretax"),
            func.sum(CostByServiceSnapshot.cost_usd).label("usd"),
        )
        .filter(
            CostByServiceSnapshot.subscription_id == sub,
            CostByServiceSnapshot.month == month,
        )
    )
    if service_names is not None:
        query = query.filter(CostByServiceSnapshot.service_name.in_(list(service_names)))
    row = query.first()
    if not row or (not row.pretax and not row.usd):
        return None
    return {
        "pretax_total": round(float(row.pretax or 0), 2),
        "cost_usd_total": round(float(row.usd or 0), 2),
        "billing_currency": subscription_billing_currency(db, sub, model=CostByServiceSnapshot),
        "total_source": "service_rows_sum",
        "source": "database",
    }


def _sync_run_covers_slice(run: dict, slice_start: date, slice_end: date) -> bool:
    """True when a CostSyncRun period fully covers the requested date slice."""
    run_start = (run.get("mtd_start") or "")[:10]
    run_end = (run.get("mtd_end") or "")[:10]
    if not run_start or not run_end:
        return False
    return run_start <= slice_start.isoformat() and run_end >= slice_end.isoformat()


def _chunk_from_sync_run(run: dict) -> dict:
    return {
        "pretax_total": run["pretax_total"],
        "cost_usd_total": run["cost_usd_total"],
        "billing_currency": run["billing_currency"],
        "total_source": run.get("total_source") or "azure_subscription_query",
        "source": "database",
    }


def _month_cost_chunk(
    db: Session,
    subscription_id: str,
    month_key: str,
    slice_start: date,
    slice_end: date,
    *,
    service_names: set[str] | None = None,
) -> dict | None:
    """Resolve one month's spend: subscription sync run → daily rows → service sum."""
    sub = _normalize_sub(subscription_id)
    run = subscription_mtd_from_sync_run(db, sub, month_key)
    if run and _sync_run_covers_slice(run, slice_start, slice_end):
        return _chunk_from_sync_run(run)
    chunk = _summary_from_daily(
        db, sub, slice_start, slice_end, service_names=service_names,
    )
    if chunk:
        return chunk
    return _summary_from_service_month(
        db, sub, month_key, service_names=service_names,
    )


def _summary_from_multi_month(
    db: Session,
    subscription_id: str,
    start: date,
    end: date,
    *,
    service_names: set[str] | None = None,
    today: date | None = None,
) -> dict | None:
    """Aggregate subscription spend across multiple calendar months."""
    pretax = 0.0
    usd = 0.0
    currency = "CAD"
    parts = 0

    for month_key, slice_start, slice_end in _iter_month_slices(start, end):
        chunk = _month_cost_chunk(
            db,
            subscription_id,
            month_key,
            slice_start,
            slice_end,
            service_names=service_names,
        )
        if not chunk:
            continue
        pretax += float(chunk.get("pretax_total") or 0)
        usd += float(chunk.get("cost_usd_total") or 0)
        currency = chunk.get("billing_currency") or currency
        parts += 1

    if parts == 0:
        return None
    return {
        "pretax_total": round(pretax, 2),
        "cost_usd_total": round(usd, 2),
        "billing_currency": currency,
        "total_source": "multi_month_aggregate",
        "source": "database",
    }


def cost_by_service_from_db(
    db: Session,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    month: str | None = None,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    resource_types: list[str] | None = None,
) -> dict | None:
    """Cost by Azure service for the selected period."""
    sub = _normalize_sub(subscription_id)
    start, end = _date_range_for_timeframe(timeframe, from_date=from_date, to_date=to_date)
    period = period_for_timeframe(timeframe, from_date=from_date, to_date=to_date)
    type_filter = _expanded_resource_types(resource_types)
    m = month or month_for_timeframe(timeframe, from_date=from_date, to_date=to_date)
    service_names = (
        _service_names_for_resource_types(db, sub, m, type_filter)
        if type_filter
        else None
    )

    if not _uses_monthly_service_snapshot(timeframe, start, end):
        daily = _service_breakdown_from_daily(
            db, sub, start, end, service_names=service_names,
        )
        if daily:
            return {**daily, **period, "month": period["month"]}
        if (timeframe or "").strip() not in _MONTH_BUCKET_TIMEFRAMES:
            return None

    if type_filter:
        arm_types = _arm_resource_types_for_filter(db, subscription_id, m, type_filter)
        if not arm_types:
            return None
        grouped = (
            db.query(
                CostByResourceSnapshot.service_name,
                func.sum(CostByResourceSnapshot.cost_billing).label("pretax"),
                func.sum(CostByResourceSnapshot.cost_usd).label("usd"),
            )
            .filter(
                CostByResourceSnapshot.subscription_id == sub,
                CostByResourceSnapshot.month == m,
                CostByResourceSnapshot.resource_type.in_(list(arm_types)),
            )
            .group_by(CostByResourceSnapshot.service_name)
            .order_by(func.sum(CostByResourceSnapshot.cost_billing).desc())
            .all()
        )
        if not grouped:
            return None
        billing_currency = subscription_billing_currency(db, sub, model=CostByResourceSnapshot)
        return {
            "properties": {
                "columns": [
                    {"name": "ServiceName"},
                    {"name": "PreTaxCost"},
                    {"name": "CostUSD"},
                    {"name": "Currency"},
                ],
                "rows": [
                    [
                        r.service_name,
                        round(float(r.pretax or 0), 4),
                        round(float(r.usd or 0), 4),
                        billing_currency,
                    ]
                    for r in grouped
                ],
            },
            "billing_currency": billing_currency,
            "source": "database",
            "month": m,
            "resource_types": sorted(type_filter),
            **period,
        }

    rows = (
        db.query(CostByServiceSnapshot)
        .filter(
            CostByServiceSnapshot.subscription_id == sub,
            CostByServiceSnapshot.month == m,
        )
        .order_by(CostByServiceSnapshot.cost_billing.desc())
        .all()
    )
    if not rows:
        return None
    billing_currency = rows[0].billing_currency or "CAD"
    return {
        "properties": {
            "columns": [
                {"name": "ServiceName"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [
                [
                    r.service_name,
                    r.cost_billing if r.cost_billing is not None else r.cost_usd,
                    r.cost_usd,
                    r.billing_currency or billing_currency,
                ]
                for r in rows
            ],
        },
        "billing_currency": billing_currency,
        "source": "database",
        "month": m,
        **period,
    }


def cost_by_resource_type_from_db(
    db: Session,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    month: str | None = None,
    *,
    resource_types: list[str] | None = None,
) -> dict | None:
    """MTD cost by ARM resource type from cost_by_resource_type."""
    from app.cost_explorer_sync import resource_type_display_name

    tf = (timeframe or "MonthToDate").strip()
    if tf not in _MONTH_BUCKET_TIMEFRAMES:
        return None

    sub = _normalize_sub(subscription_id)
    m = month or month_for_timeframe(timeframe)
    type_filter = _expanded_resource_types(resource_types)
    query = db.query(CostByResourceTypeSnapshot).filter(
        CostByResourceTypeSnapshot.subscription_id == sub,
        CostByResourceTypeSnapshot.month == m,
    )
    if type_filter:
        type_match = _resource_type_match_filter(type_filter)
        if type_match is not None:
            query = query.filter(type_match)
    rows = query.order_by(CostByResourceTypeSnapshot.cost_billing.desc()).all()
    if not rows:
        return None
    billing_currency = rows[0].billing_currency or "CAD"
    return {
        "properties": {
            "columns": [
                {"name": "ResourceType"},
                {"name": "DisplayName"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [
                [
                    r.arm_resource_type,
                    resource_type_display_name(r.arm_resource_type, r.canonical_resource_type),
                    r.cost_billing if r.cost_billing is not None else r.cost_usd,
                    r.cost_usd,
                    r.billing_currency or billing_currency,
                ]
                for r in rows
            ],
        },
        "billing_currency": billing_currency,
        "source": "database",
        "month": m,
    }


def cost_by_resource_from_db(
    db: Session,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    month: str | None = None,
    *,
    resource_types: list[str] | None = None,
) -> dict | None:
    """MTD cost per resource with service name from cost_by_resource."""
    sub = _normalize_sub(subscription_id)
    m = _resolve_resource_cost_month(db, subscription_id, timeframe, month)
    if not m:
        return None
    type_filter = _expanded_resource_types(resource_types)
    query = db.query(CostByResourceSnapshot).filter(
        CostByResourceSnapshot.subscription_id == sub,
        CostByResourceSnapshot.month == m,
    )
    if type_filter:
        arm_types = _arm_resource_types_for_filter(db, subscription_id, m, type_filter)
        if arm_types:
            query = query.filter(CostByResourceSnapshot.resource_type.in_(list(arm_types)))
        else:
            return None
    rows = query.order_by(CostByResourceSnapshot.cost_billing.desc()).all()
    if not rows and month is None:
        latest = _latest_cost_by_resource_month(db, subscription_id)
        if latest and latest != m:
            return cost_by_resource_from_db(
                db, subscription_id, timeframe, month=latest, resource_types=resource_types,
            )
    if not rows:
        return None
    billing_currency = rows[0].billing_currency or "CAD"
    return {
        "properties": {
            "columns": [
                {"name": "ResourceId"},
                {"name": "ResourceType"},
                {"name": "ResourceGroup"},
                {"name": "ServiceName"},
                {"name": "PreTaxCost"},
                {"name": "CostUSD"},
                {"name": "Currency"},
            ],
            "rows": [
                [
                    r.resource_id,
                    r.resource_type or "",
                    r.resource_group or "",
                    r.service_name,
                    r.cost_billing if r.cost_billing is not None else r.cost_usd,
                    r.cost_usd,
                    r.billing_currency or billing_currency,
                ]
                for r in rows
            ],
        },
        "billing_currency": billing_currency,
        "source": "database",
        "month": m,
    }


def cost_summary_from_db(
    db: Session,
    subscription_id: str,
    timeframe: str = "MonthToDate",
    month: str | None = None,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    resource_types: list[str] | None = None,
) -> dict | None:
    """Subscription totals for the selected period."""
    sub = _normalize_sub(subscription_id)
    tf = (timeframe or "MonthToDate").strip()
    start, end = _date_range_for_timeframe(timeframe, from_date=from_date, to_date=to_date)
    period = period_for_timeframe(timeframe, from_date=from_date, to_date=to_date)
    type_filter = _expanded_resource_types(resource_types)
    m = month or month_for_timeframe(timeframe, from_date=from_date, to_date=to_date)
    service_names = (
        _service_names_for_resource_types(db, sub, m, type_filter)
        if type_filter
        else None
    )

    def _with_period(summary: dict, *, month_key: str | None = None) -> dict:
        payload = {**summary, **period, "month": month_key or period["month"]}
        if type_filter:
            payload["resource_types"] = sorted(type_filter)
        return payload

    if type_filter:
        return _summary_from_resource_type_snapshots(
            db, sub, m, type_filter,
            timeframe=timeframe, from_date=from_date, to_date=to_date,
        )

    if tf != "Custom":
        from app.cost_period_totals import period_total_from_db

        stored = period_total_from_db(
            db,
            sub,
            tf,
            period_start=start.isoformat(),
            period_end=end.isoformat(),
        )
        if stored:
            return _with_period(stored)

    if tf in _ROLLING_DAILY_TIMEFRAMES:
        daily_summary = _summary_from_daily(
            db, sub, start, end, service_names=service_names,
        )
        if daily_summary:
            return _with_period(daily_summary)
        return None

    if tf in _MULTI_MONTH_TIMEFRAMES or (
        _spans_multiple_months(start, end) and tf not in _CALENDAR_MTD_TIMEFRAMES
    ):
        multi_summary = _summary_from_multi_month(
            db, sub, start, end, service_names=service_names,
        )
        if multi_summary:
            return _with_period(multi_summary)
        if tf in _MULTI_MONTH_TIMEFRAMES:
            return None

    period_meta = mtd_period_for_timeframe(timeframe, from_date=from_date, to_date=to_date)
    if m != period_meta["month"]:
        period_meta = {**period_meta, "month": m}

    service_rows = (
        db.query(CostByServiceSnapshot)
        .filter(
            CostByServiceSnapshot.subscription_id == sub,
            CostByServiceSnapshot.month == m,
        )
        .all()
    )

    if tf in _CALENDAR_MTD_TIMEFRAMES or tf == "TheLastMonth":
        run_summary = subscription_mtd_from_sync_run(db, sub, m)
        if run_summary:
            mtd_start = run_summary.get("mtd_start") or period_meta.get("mtd_start")
            mtd_end = run_summary.get("mtd_end") or period_meta.get("mtd_end")
            return {
                **run_summary,
                "row_count": len(service_rows),
                "month": m,
                "mtd_start": mtd_start,
                "mtd_end": mtd_end,
                "period_start": mtd_start,
                "period_end": mtd_end,
            }
        daily_summary = _summary_from_daily(
            db, sub, start, end, service_names=service_names,
        )
        if daily_summary:
            return {**daily_summary, **period_meta, "month": m}
        if service_rows:
            pretax = sum(r.cost_billing or 0.0 for r in service_rows)
            usd = sum(r.cost_usd or 0.0 for r in service_rows)
            billing_currency = service_rows[0].billing_currency or "CAD"
            return {
                "pretax_total": round(pretax, 2),
                "cost_usd_total": round(usd, 2),
                "billing_currency": billing_currency,
                "row_count": len(service_rows),
                "total_source": "service_rows_sum",
                "source": "database",
                "month": m,
                **period_meta,
            }
        return None

    daily_summary = _summary_from_daily(
        db, sub, start, end, service_names=service_names,
    )
    if daily_summary:
        return _with_period(daily_summary)
    return None


def daily_service_trend_from_db(
    db: Session,
    subscription_id: str,
    service_name: str,
) -> list[dict]:
    """Daily cost trend for one Azure service."""
    sub = _normalize_sub(subscription_id)
    rows = (
        db.query(CostDailyByServiceSnapshot)
        .filter(
            CostDailyByServiceSnapshot.subscription_id == sub,
            CostDailyByServiceSnapshot.service_name == service_name,
        )
        .order_by(CostDailyByServiceSnapshot.cost_date)
        .all()
    )
    return [
        {
            "date": r.cost_date,
            "pretax": r.cost_billing if r.cost_billing is not None else r.cost_usd,
            "cost_usd": r.cost_usd,
            "currency": r.billing_currency or "CAD",
        }
        for r in rows
    ]


def daily_rate_by_service(
    db: Session,
    subscription_id: str,
    *,
    days: int = 14,
) -> dict[str, list[float]]:
    """Daily cost series per Azure service (oldest-first) for the last N days."""
    from datetime import date, timedelta

    sub = _normalize_sub(subscription_id)
    end = date.today()
    start = end - timedelta(days=max(1, days) - 1)
    rows = (
        db.query(CostDailyByServiceSnapshot)
        .filter(
            CostDailyByServiceSnapshot.subscription_id == sub,
            CostDailyByServiceSnapshot.cost_date >= start.isoformat(),
            CostDailyByServiceSnapshot.cost_date <= end.isoformat(),
            CostDailyByServiceSnapshot.service_name != "__subscription__",
        )
        .order_by(CostDailyByServiceSnapshot.cost_date)
        .all()
    )
    by_service: dict[str, dict[str, float]] = {}
    for row in rows:
        amount = float(row.cost_billing if row.cost_billing is not None else row.cost_usd or 0.0)
        by_service.setdefault(row.service_name, {})[row.cost_date] = amount

    day_keys = [(start + timedelta(days=offset)).isoformat() for offset in range(days)]
    out: dict[str, list[float]] = {}
    for service, daily_map in by_service.items():
        out[service] = [round(float(daily_map.get(day, 0.0)), 4) for day in day_keys]
    return out


def resource_daily_cost_histories(
    db: Session,
    subscription_id: str,
    resource_ids: list[str],
    *,
    days: int = 28,
) -> dict[str, list[float]]:
    """Estimate per-resource daily cost series using service-level trends and resource MTD share."""
    from app.focus_mapping import normalize_arm_id

    sub = _normalize_sub(subscription_id)
    service_daily = daily_rate_by_service(db, sub, days=days)
    if not service_daily:
        return {}

    histories: dict[str, list[float]] = {}
    normalized_rids = {}
    for resource_id in resource_ids:
        rid = normalize_arm_id(resource_id).lower()
        if rid:
            normalized_rids[rid] = resource_id

    if not normalized_rids:
        return histories

    # Batch query all resources, order by month desc
    rows = (
        db.query(CostByResourceSnapshot)
        .filter(
            CostByResourceSnapshot.subscription_id == sub,
            CostByResourceSnapshot.resource_id.in_(list(normalized_rids.keys())),
        )
        .order_by(CostByResourceSnapshot.resource_id, CostByResourceSnapshot.month.desc())
        .all()
    )

    # Build dict, keeping latest month per resource
    resource_dict: dict[str, CostByResourceSnapshot] = {}
    for row in rows:
        if row.resource_id not in resource_dict:
            resource_dict[row.resource_id] = row

    # Process with O(1) lookups
    for rid in normalized_rids.keys():
        row = resource_dict.get(rid)
        if not row or not row.service_name:
            continue
        service_series = service_daily.get(row.service_name) or []
        if len(service_series) < days:
            continue
        service_total = sum(service_series)
        resource_mtd = float(row.cost_billing if row.cost_billing is not None else row.cost_usd or 0.0)
        if service_total <= 0 or resource_mtd <= 0:
            continue
        share = resource_mtd / service_total
        histories[rid] = [round(v * share, 4) for v in service_series]
    return histories

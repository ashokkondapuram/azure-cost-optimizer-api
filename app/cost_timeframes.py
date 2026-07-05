"""Cost explorer timeframe presets and date-range resolution."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Any

# Azure Cost Management native timeframe strings (passed through without custom dates).
# TheLastMonth is an app preset only — Azure rejects it; map via azure_timeframe_payload().
AZURE_NATIVE_TIMEFRAMES: frozenset[str] = frozenset({
    "MonthToDate",
    "BillingMonthToDate",
    "WeekToDate",
})

TIMEFRAME_CATALOG: list[dict[str, Any]] = [
    {"id": "Last7Days", "label": "Last 7 days", "group": "rolling"},
    {"id": "Last30Days", "label": "Last 30 days", "group": "rolling"},
    {"id": "MonthToDate", "label": "This month", "group": "calendar"},
    {"id": "BillingMonthToDate", "label": "Billing month to date", "group": "calendar"},
    {"id": "TheLastMonth", "label": "Last month", "group": "calendar"},
    {"id": "ThisQuarter", "label": "This quarter", "group": "calendar"},
    {"id": "LastQuarter", "label": "Last quarter", "group": "calendar"},
    {"id": "Last3Months", "label": "Last 3 months", "group": "rolling"},
    {"id": "Last6Months", "label": "Last 6 months", "group": "rolling"},
    {"id": "Last12Months", "label": "Last 12 months", "group": "rolling"},
    {"id": "ThisYear", "label": "This year", "group": "calendar"},
    {"id": "Custom", "label": "Custom range", "group": "custom", "requires_dates": True},
]

TIMEFRAME_LABELS: dict[str, str] = {item["id"]: item["label"] for item in TIMEFRAME_CATALOG}


def _parse_iso_date(value: str | None) -> date | None:
    raw = (value or "").strip()[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _quarter_start(d: date) -> date:
    quarter = (d.month - 1) // 3
    return date(d.year, quarter * 3 + 1, 1)


def _quarter_end(d: date) -> date:
    start = _quarter_start(d)
    end_month = start.month + 2
    return date(start.year, end_month, monthrange(start.year, end_month)[1])


def _shift_months(d: date, months: int) -> date:
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def resolve_date_range(
    timeframe: str,
    *,
    from_date: str | date | None = None,
    to_date: str | date | None = None,
    today: date | None = None,
) -> tuple[date, date]:
    """Return inclusive [start, end] dates for a cost timeframe preset."""
    tf = (timeframe or "MonthToDate").strip()
    today = today or date.today()

    if isinstance(from_date, date):
        start = from_date
    else:
        start = _parse_iso_date(from_date)
    if isinstance(to_date, date):
        end = to_date
    else:
        end = _parse_iso_date(to_date)

    if tf == "Custom":
        if not start or not end:
            raise ValueError("from_date and to_date are required for Custom timeframe")
        if end < start:
            start, end = end, start
        return start, end

    if tf == "Last7Days":
        return today - timedelta(days=6), today
    if tf == "Last30Days":
        return today - timedelta(days=29), today
    if tf in {"MonthToDate", "BillingMonthToDate"}:
        return today.replace(day=1), today
    if tf == "TheLastMonth":
        first_this = today.replace(day=1)
        end = first_this - timedelta(days=1)
        return end.replace(day=1), end
    if tf == "WeekToDate":
        return today - timedelta(days=today.weekday()), today
    if tf == "ThisQuarter":
        return _quarter_start(today), today
    if tf == "LastQuarter":
        this_q_start = _quarter_start(today)
        end = this_q_start - timedelta(days=1)
        return _quarter_start(end), end
    if tf == "ThisYear":
        return date(today.year, 1, 1), today
    if tf == "Last3Months":
        return _shift_months(today, -3) + timedelta(days=1), today
    if tf == "Last6Months":
        return _shift_months(today, -6) + timedelta(days=1), today
    if tf == "Last12Months":
        return _shift_months(today, -12) + timedelta(days=1), today

    # Unknown values fall back to month-to-date.
    return today.replace(day=1), today


def month_for_timeframe(
    timeframe: str,
    *,
    from_date: str | date | None = None,
    to_date: str | date | None = None,
    today: date | None = None,
) -> str:
    """Primary YYYY-MM bucket for month-scoped cost tables."""
    start, _end = resolve_date_range(timeframe, from_date=from_date, to_date=to_date, today=today)
    return start.strftime("%Y-%m")


def period_for_timeframe(
    timeframe: str,
    *,
    from_date: str | date | None = None,
    to_date: str | date | None = None,
    today: date | None = None,
) -> dict[str, str]:
    start, end = resolve_date_range(timeframe, from_date=from_date, to_date=to_date, today=today)
    return {
        "month": start.strftime("%Y-%m"),
        "mtd_start": start.isoformat(),
        "mtd_end": end.isoformat(),
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
    }


def timeframe_label(timeframe: str) -> str:
    return TIMEFRAME_LABELS.get((timeframe or "").strip(), timeframe or "Period")


def is_calendar_month_range(start: date, end: date, *, today: date | None = None) -> bool:
    """True when the range is a full calendar month (used for monthly snapshot tables)."""
    today = today or date.today()
    month_start, month_end = _month_bounds(start.year, start.month)
    if start == month_start and end == month_end:
        return True
    if start == today.replace(day=1) and end == today:
        return True
    return False


def azure_timeframe_payload(
    timeframe: str,
    *,
    from_date: str | date | None = None,
    to_date: str | date | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Map app timeframe to Azure Cost Management query body fields."""
    tf = (timeframe or "MonthToDate").strip()
    start, end = resolve_date_range(tf, from_date=from_date, to_date=to_date, today=today)
    if tf in AZURE_NATIVE_TIMEFRAMES:
        return {"timeframe": tf}
    return {
        "timeframe": "Custom",
        "timePeriod": {"from": start.isoformat(), "to": end.isoformat()},
    }


def list_timeframe_catalog() -> list[dict[str, Any]]:
    return [dict(item) for item in TIMEFRAME_CATALOG]

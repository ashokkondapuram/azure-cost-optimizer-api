"""Tests for cost explorer timeframe presets."""

from datetime import date

import pytest

from app.cost_timeframes import (
    azure_timeframe_payload,
    list_timeframe_catalog,
    period_for_timeframe,
    prefers_live_cost_query,
    resolve_date_range,
    timeframe_label,
)


def test_resolve_last_7_days():
    start, end = resolve_date_range("Last7Days", today=date(2026, 6, 30))
    assert start == date(2026, 6, 24)
    assert end == date(2026, 6, 30)


def test_resolve_last_month():
    start, end = resolve_date_range("TheLastMonth", today=date(2026, 6, 15))
    assert start == date(2026, 5, 1)
    assert end == date(2026, 5, 31)


def test_resolve_this_quarter():
    start, end = resolve_date_range("ThisQuarter", today=date(2026, 6, 15))
    assert start == date(2026, 4, 1)
    assert end == date(2026, 6, 15)


def test_resolve_last_quarter():
    start, end = resolve_date_range("LastQuarter", today=date(2026, 6, 15))
    assert start == date(2026, 1, 1)
    assert end == date(2026, 3, 31)


def test_resolve_custom_range():
    start, end = resolve_date_range(
        "Custom",
        from_date="2026-01-10",
        to_date="2026-02-20",
    )
    assert start == date(2026, 1, 10)
    assert end == date(2026, 2, 20)


def test_custom_requires_dates():
    with pytest.raises(ValueError):
        resolve_date_range("Custom")


def test_azure_custom_payload_for_rolling_range():
    payload = azure_timeframe_payload("Last30Days", today=date(2026, 6, 30))
    assert payload["timeframe"] == "Custom"
    assert payload["timePeriod"]["from"] == "2026-06-01"
    assert payload["timePeriod"]["to"] == "2026-06-30"


def test_azure_native_month_to_date():
    payload = azure_timeframe_payload("MonthToDate", today=date(2026, 6, 30))
    assert payload == {"timeframe": "MonthToDate"}


def test_azure_last_month_uses_custom_period():
    payload = azure_timeframe_payload("TheLastMonth", today=date(2026, 6, 15))
    assert payload["timeframe"] == "Custom"
    assert payload["timePeriod"] == {"from": "2026-05-01", "to": "2026-05-31"}

def test_resolve_last_14_days():
    start, end = resolve_date_range("Last14Days", today=date(2026, 6, 30))
    assert start == date(2026, 6, 17)
    assert end == date(2026, 6, 30)


def test_resolve_week_to_date():
    # 2026-06-30 is a Tuesday (weekday 1) -> week starts Monday June 29
    start, end = resolve_date_range("WeekToDate", today=date(2026, 6, 30))
    assert start == date(2026, 6, 29)
    assert end == date(2026, 6, 30)


def test_prefers_live_for_rolling_presets():
    assert prefers_live_cost_query("Last30Days") is False
    assert prefers_live_cost_query("WeekToDate") is False
    assert prefers_live_cost_query("MonthToDate") is False
    assert prefers_live_cost_query("Custom") is True
    assert prefers_live_cost_query("Last7Days", has_resource_type_filter=True) is False


def test_prefers_live_for_calendar_range_presets():
    assert prefers_live_cost_query("ThisYear") is False
    assert prefers_live_cost_query("ThisQuarter") is False
    assert prefers_live_cost_query("Last12Months") is False


def test_synced_period_timeframes_cover_catalog_except_custom():
    from app.cost_timeframes import SYNCED_PERIOD_TIMEFRAMES, TIMEFRAME_CATALOG

    catalog_ids = {item["id"] for item in TIMEFRAME_CATALOG}
    assert set(SYNCED_PERIOD_TIMEFRAMES) == catalog_ids - {"Custom"}


def test_catalog_includes_requested_presets():
    ids = {item["id"] for item in list_timeframe_catalog()}
    assert {
        "Last7Days",
        "Last14Days",
        "Last60Days",
        "Last90Days",
        "WeekToDate",
        "MonthToDate",
        "Custom",
        "Last30Days",
        "ThisQuarter",
        "ThisYear",
        "TheLastMonth",
        "LastQuarter",
        "Last3Months",
        "Last6Months",
        "Last12Months",
    }.issubset(ids)


def test_timeframe_label():
    assert timeframe_label("Last12Months") == "Last 12 months"

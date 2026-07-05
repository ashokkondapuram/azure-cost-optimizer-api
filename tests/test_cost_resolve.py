"""Unit tests for cost DB/live resolution helpers."""

from app.cost_resolve import live_range_kw, resolve_cost_db_then_live


def test_live_range_kw_strips_db_only_filters():
    kw = {
        "timeframe": "MonthToDate",
        "from_date": "2026-06-01",
        "to_date": "2026-06-30",
        "resource_types": ["microsoft.compute/virtualmachines"],
    }
    assert live_range_kw(kw) == {
        "timeframe": "MonthToDate",
        "from_date": "2026-06-01",
        "to_date": "2026-06-30",
    }


def test_resolve_prefers_database():
    data, source = resolve_cost_db_then_live(
        db_call=lambda: {"pretax_total": 10.0, "source": "database"},
        live_call=lambda: {"pretax_total": 99.0, "source": "azure"},
    )
    assert data["pretax_total"] == 10.0
    assert source == "database"


def test_resolve_falls_back_to_live():
    data, source = resolve_cost_db_then_live(
        db_call=lambda: None,
        live_call=lambda: {"pretax_total": 42.0, "source": "azure"},
    )
    assert data["pretax_total"] == 42.0
    assert source == "azure"


def test_resolve_returns_none_when_both_empty():
    data, source = resolve_cost_db_then_live(
        db_call=lambda: None,
        live_call=lambda: None,
    )
    assert data is None
    assert source is None

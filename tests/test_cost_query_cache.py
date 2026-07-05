"""Tests for cost query cache and dashboard cost bundle."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app import cost_query_cache as cache
from app.cost_live_bundle import monthly_cost_trend_from_summaries, query_dashboard_cost_bundle_live


@pytest.fixture(autouse=True)
def reset_cost_cache():
    cache.clear_cost_query_cache()
    with cache._cache_lock:
        cache._metrics.update(
            hits=0, misses=0, api_calls=0, dedup_waits=0, errors=0, errors_429=0,
        )
        cache._inflight.clear()
    yield
    cache.clear_cost_query_cache()


def test_cached_cost_live_query_hit_miss():
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return {"pretax_total": 100.0}

    first = cache.cached_cost_live_query("sub-a", "summary", "MonthToDate", loader)
    second = cache.cached_cost_live_query("sub-a", "summary", "MonthToDate", loader)

    assert first == {"pretax_total": 100.0}
    assert second == first
    assert calls["n"] == 1
    metrics = cache.cost_cache_metrics()
    assert metrics["hits"] == 1
    assert metrics["misses"] == 1
    assert metrics["api_calls"] == 1


def test_cached_cost_live_query_dedup_concurrent():
    gate = threading.Event()
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        gate.set()
        time.sleep(0.3)
        return {"pretax_total": 42.0}

    results: list = []

    def worker():
        results.append(
            cache.cached_cost_live_query("sub-b", "summary", "TheLastMonth", loader)
        )

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    assert gate.wait(timeout=2)
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert len(results) == 2
    assert results[0] == results[1]
    assert calls["n"] == 1
    assert cache.cost_cache_metrics()["dedup_waits"] >= 1


def test_ttl_for_historical_vs_mtd():
    assert cache.ttl_for_query("daily", "TheLastMonth") == cache._HISTORICAL_TTL
    assert cache.ttl_for_query("daily", "MonthToDate") == cache._DAILY_MTD_TTL
    assert cache.ttl_for_query("forecast", "MonthToDate") == cache._FORECAST_TTL


def test_invalidate_subscription_cost_cache():
    cache.cached_cost_live_query(
        "sub-c", "summary", "MonthToDate", lambda: {"pretax_total": 1.0},
    )
    assert cache.cost_cache_metrics()["entries"] == 1
    cache.invalidate_subscription_cost_cache("sub-c")
    assert cache.cost_cache_metrics()["entries"] == 0


def test_monthly_cost_trend_from_summaries():
    trend = monthly_cost_trend_from_summaries(
        mtd_amount=500.0,
        last_month={"pretax_total": 1000.0},
        forecast={"pretax_total": 1200.0},
    )
    assert trend["projected"] == 1200.0
    assert trend["last_month"] == 1000.0
    assert trend["delta_pct"] == 20.0


@patch("app.cost_live_bundle.query_cost_summary_live")
@patch("app.cost_live_bundle.query_daily_costs_live")
@patch("app.cost_live_bundle.query_forecast_summary_live")
def test_dashboard_cost_bundle_live(mock_forecast, mock_daily, mock_summary):
    db = MagicMock()
    mock_summary.side_effect = [
        {"pretax_total": 200.0, "source": "azure"},
        {"pretax_total": 1500.0, "source": "azure"},
        {"pretax_total": 900.0, "source": "azure"},
    ]
    mock_daily.return_value = {"properties": {"columns": [], "rows": []}, "source": "azure"}
    mock_forecast.return_value = {"pretax_total": 1100.0, "source": "azure"}

    bundle = query_dashboard_cost_bundle_live(
        db, "SUB-ABC", timeframe="MonthToDate", token="tok",
    )

    assert bundle["summary_mtd"]["pretax_total"] == 200.0
    assert bundle["summary_ytd"]["pretax_total"] == 1500.0
    assert bundle["last_month"]["pretax_total"] == 900.0
    assert bundle["monthly_trend"]["projected"] == 1100.0
    assert mock_summary.call_count == 3
    mock_daily.assert_called_once()
    mock_forecast.assert_called_once()

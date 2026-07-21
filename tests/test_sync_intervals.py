"""Tests for scheduled sync interval env parsing and worker registration."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.parametrize(
    ("minutes_env", "hours_env", "minutes_value", "hours_value", "expected"),
    [
        (None, None, None, None, 60.0),
        ("45", None, None, None, 45.0),
        (None, "2", None, None, 120.0),
        ("30", "6", None, None, 30.0),
    ],
)
def test_cost_sync_interval_minutes_from_env(
    monkeypatch,
    minutes_env,
    hours_env,
    minutes_value,
    hours_value,
    expected,
):
    monkeypatch.delenv("COST_SYNC_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("COST_REFRESH_HOURS", raising=False)
    monkeypatch.delenv("COST_EXPORT_REFRESH_HOURS", raising=False)
    if minutes_env is not None:
        monkeypatch.setenv("COST_SYNC_INTERVAL_MINUTES", minutes_env)
    if hours_env is not None:
        monkeypatch.setenv("COST_REFRESH_HOURS", hours_env)

    from app.sync_intervals import cost_sync_interval_minutes

    assert cost_sync_interval_minutes() == expected


@pytest.mark.parametrize(
    ("minutes", "hours", "expected"),
    [
        (None, None, 30.0),
        ("15", None, 15.0),
        (None, "1", 60.0),
        ("20", "6", 20.0),
    ],
)
def test_metrics_sync_interval_minutes_from_env(monkeypatch, minutes, hours, expected):
    monkeypatch.delenv("METRICS_SYNC_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("METRICS_SYNC_INTERVAL_HOURS", raising=False)
    if minutes is not None:
        monkeypatch.setenv("METRICS_SYNC_INTERVAL_MINUTES", minutes)
    if hours is not None:
        monkeypatch.setenv("METRICS_SYNC_INTERVAL_HOURS", hours)

    from app.sync_intervals import metrics_sync_interval_minutes

    assert metrics_sync_interval_minutes() == expected


def test_inventory_and_analysis_defaults(monkeypatch):
    monkeypatch.delenv("INVENTORY_SYNC_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("RESOURCE_DISCOVERY_HOURS", raising=False)
    monkeypatch.delenv("ANALYSIS_SYNC_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("SCHEDULED_ANALYSIS_HOURS", raising=False)

    from app.sync_intervals import analysis_sync_interval_minutes, inventory_sync_interval_minutes

    assert inventory_sync_interval_minutes() == 15.0
    assert analysis_sync_interval_minutes() == 10.0


def test_startup_delay_legacy_fallback(monkeypatch):
    monkeypatch.delenv("COST_SYNC_STARTUP_DELAY_SEC", raising=False)
    monkeypatch.setenv("COST_REFRESH_STARTUP_DELAY_SEC", "25")

    from app.sync_intervals import cost_sync_startup_delay_seconds

    assert cost_sync_startup_delay_seconds() == 25.0


@patch("app.metrics_sync_worker.threading.Thread")
def test_metrics_sync_worker_registers_interval(mock_thread, monkeypatch):
    monkeypatch.setenv("METRICS_SYNC_INTERVAL_MINUTES", "30")
    monkeypatch.setenv("METRICS_SYNC_STARTUP_DELAY_SEC", "120")

    import app.metrics_sync_worker as worker

    worker._started = False
    worker.start_metrics_sync_worker()

    mock_thread.assert_called_once()
    assert mock_thread.call_args.kwargs["args"] == (30 * 60.0, 120.0)


@patch("app.cost_explorer_worker.threading.Thread")
def test_cost_explorer_worker_registers_interval(mock_thread, monkeypatch):
    monkeypatch.setenv("COST_SYNC_INTERVAL_MINUTES", "60")
    monkeypatch.setenv("COST_SYNC_STARTUP_DELAY_SEC", "0")
    monkeypatch.setenv("COST_EXPLORER_WORKER_ENABLED", "true")

    import app.cost_explorer_worker as worker

    worker._started = False
    worker.start()

    mock_thread.assert_called_once()
    assert mock_thread.call_args.kwargs["args"] == (60 * 60.0, 0.0)


@patch("app.resource_discovery_worker.threading.Thread")
def test_inventory_sync_worker_registers_interval(mock_thread, monkeypatch):
    monkeypatch.setenv("INVENTORY_SYNC_INTERVAL_MINUTES", "15")
    monkeypatch.setenv("INVENTORY_SYNC_STARTUP_DELAY_SEC", "60")
    monkeypatch.setenv("RESOURCE_DISCOVERY_WORKER_ENABLED", "true")

    import app.resource_discovery_worker as worker

    worker._started = False
    worker.start()

    mock_thread.assert_called_once()
    assert mock_thread.call_args.kwargs["args"] == (15 * 60.0, 60.0)

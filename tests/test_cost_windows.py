"""Unit tests for rolling cost window comparison."""
from app.cost_windows import compare_rolling_daily_windows


def test_compare_insufficient_series():
    result = compare_rolling_daily_windows([1.0] * 10, window_days=7)
    assert result["sufficient"] is False


def test_compare_low_baseline_nonzero_days():
    # 7 baseline zeros + 7 recent values — not enough nonzero baseline days.
    series = [0.0] * 7 + [25.0] * 7
    result = compare_rolling_daily_windows(series, window_days=7, min_baseline_days=5)
    assert result["sufficient"] is False


def test_compare_recent_spike_oldest_first():
    # Oldest-first: low baseline week, then elevated recent week.
    series = [10.0] * 7 + [25.0] * 7
    result = compare_rolling_daily_windows(series, window_days=7)
    assert result["sufficient"] is True
    assert result["baseline_avg"] == 10.0
    assert result["current_avg"] == 25.0
    assert result["spike_factor"] == 2.5
    assert result["baseline_total"] == 70.0
    assert result["current_total"] == 175.0


def test_compare_recent_drop_not_spike():
    # Oldest-first: high baseline, low recent — current below baseline.
    series = [25.0] * 7 + [10.0] * 7
    result = compare_rolling_daily_windows(series, window_days=7)
    assert result["sufficient"] is True
    assert result["current_avg"] == 10.0
    assert result["baseline_avg"] == 25.0
    assert result["spike_factor"] == 0.4

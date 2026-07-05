"""Rolling cost window comparison helpers (oldest-first daily series)."""
from __future__ import annotations

from statistics import mean
from typing import Any


def compare_rolling_daily_windows(
    series: list[float],
    *,
    window_days: int = 7,
    min_baseline_days: int = 5,
) -> dict[str, Any]:
    """Compare the most recent N days to the prior N days in an oldest-first series."""
    window = max(1, int(window_days))
    required = window * 2
    if len(series) < required:
        return {
            "sufficient": False,
            "window_days": window,
            "current_avg": 0.0,
            "baseline_avg": 0.0,
            "spike_factor": None,
        }

    current = series[-window:]
    baseline = series[-required:-window]
    baseline_nonzero = sum(1 for v in baseline if v > 0)
    if baseline_nonzero < min_baseline_days:
        return {
            "sufficient": False,
            "window_days": window,
            "current_avg": 0.0,
            "baseline_avg": 0.0,
            "spike_factor": None,
        }

    current_avg = float(mean(current)) if current else 0.0
    baseline_avg = float(mean(baseline)) if baseline else 0.0
    spike_factor = round(current_avg / baseline_avg, 2) if baseline_avg > 0 else None

    return {
        "sufficient": True,
        "window_days": window,
        "current_avg": round(current_avg, 4),
        "baseline_avg": round(baseline_avg, 4),
        "spike_factor": spike_factor,
        "current_total": round(sum(current), 2),
        "baseline_total": round(sum(baseline), 2),
    }

"""Cost forecasting engine using linear regression with seasonality decomposition.

Provides:
  - Per-resource 30/60/90-day cost forecasts
  - Subscription-level spend trajectory
  - Budget breach prediction with confidence intervals
  - Trend classification (growing / stable / declining / volatile)

Design:
  - Pure Python (no numpy/pandas dependency)
  - Linear regression (OLS) for trend line
  - Simple 7-day moving average for seasonality decomposition
  - Monte Carlo confidence bands via bootstrapped residuals
"""
from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()

_MIN_POINTS_FOR_FORECAST = 7
_BOOTSTRAP_SAMPLES = 200
_RANDOM_SEED = 42


@dataclass
class ForecastResult:
    resource_id: str
    forecast_30d: float
    forecast_60d: float
    forecast_90d: float
    daily_rate_trend: float          # slope of the trend line ($/day change per day)
    trend_class: str                 # "growing" | "stable" | "declining" | "volatile"
    confidence_low_90d: float        # lower bound of 90% CI at 90 days
    confidence_high_90d: float       # upper bound of 90% CI at 90 days
    r_squared: float                 # goodness of fit for trend line
    volatility_cv: float             # coefficient of variation of residuals
    budget_breach_day: int | None    # day number when forecast crosses budget_limit
    evidence: dict[str, Any] = field(default_factory=dict)


def _ols_slope_intercept(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Ordinary Least Squares slope and intercept."""
    n = len(xs)
    if n < 2:
        return 0.0, ys[0] if ys else 0.0
    sx = sum(xs)
    sy = sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sxx = sum(x * x for x in xs)
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0, sy / n
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    return slope, intercept


def _r_squared(ys: list[float], slope: float, intercept: float) -> float:
    if not ys:
        return 0.0
    mean_y = statistics.mean(ys)
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (slope * i + intercept)) ** 2 for i, y in enumerate(ys))
    return max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0


def _remove_seasonality(values: list[float], period: int = 7) -> list[float]:
    """Subtract a rolling-average seasonal component to get the deseasonalised series."""
    if len(values) < period * 2:
        return list(values)
    out: list[float] = []
    for i, v in enumerate(values):
        start = max(0, i - period // 2)
        end   = min(len(values), i + period // 2 + 1)
        window = values[start:end]
        seasonal_avg = sum(window) / len(window)
        out.append(v - seasonal_avg + statistics.mean(values))
    return out


def _bootstrap_ci(
    residuals: list[float],
    forecast_base: float,
    n_samples: int = _BOOTSTRAP_SAMPLES,
    confidence: float = 0.90,
) -> tuple[float, float]:
    """Bootstrap confidence interval for a forecast value."""
    if not residuals:
        return forecast_base, forecast_base
    rng = random.Random(_RANDOM_SEED)
    boot_samples = [
        forecast_base + sum(rng.choice(residuals) for _ in range(max(1, len(residuals) // 4)))
        for _ in range(n_samples)
    ]
    boot_samples.sort()
    lo_idx = int(n_samples * (1 - confidence) / 2)
    hi_idx = int(n_samples * (1 - (1 - confidence) / 2))
    return boot_samples[lo_idx], boot_samples[min(hi_idx, n_samples - 1)]


def _classify_trend(slope: float, cv: float, mean_val: float) -> str:
    """Classify trend based on slope and volatility."""
    if cv > 0.5:
        return "volatile"
    if mean_val == 0:
        return "stable"
    slope_pct = slope / mean_val  # relative slope
    if slope_pct > 0.02:
        return "growing"
    if slope_pct < -0.02:
        return "declining"
    return "stable"


def forecast_resource(
    resource_id: str,
    daily_costs: list[float],
    budget_limit: float | None = None,
) -> ForecastResult | None:
    """Forecast 30/60/90-day costs for a single resource.

    Args:
        resource_id: ARM resource ID (used for labelling only).
        daily_costs: Daily cost values ordered oldest → newest.
        budget_limit: Optional budget threshold; if set, predicts breach day.

    Returns:
        ForecastResult, or None if insufficient data.
    """
    if not daily_costs or len(daily_costs) < _MIN_POINTS_FOR_FORECAST:
        return None

    # Deseasonalise before regression
    deseas = _remove_seasonality(daily_costs)
    xs = list(range(len(deseas)))
    slope, intercept = _ols_slope_intercept(xs, deseas)
    r2 = _r_squared(deseas, slope, intercept)

    residuals = [y - (slope * x + intercept) for x, y in zip(xs, deseas)]
    try:
        cv = statistics.stdev(residuals) / statistics.mean(deseas) if statistics.mean(deseas) > 0 else 0.0
    except Exception:
        cv = 0.0

    n = len(daily_costs)
    forecast_at = lambda d: max(0.0, slope * (n + d) + intercept)

    f30 = forecast_at(30)
    f60 = forecast_at(60)
    f90 = forecast_at(90)

    ci_low, ci_high = _bootstrap_ci(residuals, f90)

    mean_val = statistics.mean(deseas) if deseas else 0.0
    trend = _classify_trend(slope, cv, mean_val)

    # Budget breach prediction
    breach_day: int | None = None
    if budget_limit is not None and budget_limit > 0:
        for d in range(1, 365):
            if forecast_at(d) >= budget_limit:
                breach_day = d
                break

    return ForecastResult(
        resource_id=resource_id,
        forecast_30d=round(f30, 4),
        forecast_60d=round(f60, 4),
        forecast_90d=round(f90, 4),
        daily_rate_trend=round(slope, 6),
        trend_class=trend,
        confidence_low_90d=round(max(0.0, ci_low), 4),
        confidence_high_90d=round(ci_high, 4),
        r_squared=round(r2, 4),
        volatility_cv=round(cv, 4),
        budget_breach_day=breach_day,
        evidence={
            "n_data_points": n,
            "slope": round(slope, 6),
            "intercept": round(intercept, 4),
            "r_squared": round(r2, 4),
            "mean_daily": round(mean_val, 4),
        },
    )


def forecast_subscription_spend(
    daily_totals: list[float],
    budget_usd: float | None = None,
) -> dict[str, Any]:
    """Forecast subscription-level total spend trajectory.

    Args:
        daily_totals: Daily total subscription cost ordered oldest → newest.
        budget_usd: Optional monthly budget; predicts month-end overage.

    Returns:
        Dictionary with forecast values, trend classification, and budget outlook.
    """
    result = forecast_resource("__subscription__", daily_totals, budget_limit=None)
    if result is None:
        return {"status": "insufficient_data", "min_required": _MIN_POINTS_FOR_FORECAST}

    days_in_month = 30
    mtd_days = len(daily_totals)
    mtd_spend = sum(daily_totals)
    remaining_days = max(0, days_in_month - mtd_days)
    projected_month_end = mtd_spend + result.forecast_30d * (remaining_days / days_in_month)

    outlook: dict[str, Any] = {
        "status": "ok",
        "mtd_spend": round(mtd_spend, 2),
        "forecast_eom": round(projected_month_end, 2),
        "forecast_30d": result.forecast_30d,
        "forecast_60d": result.forecast_60d,
        "forecast_90d": result.forecast_90d,
        "daily_trend_slope": result.daily_rate_trend,
        "trend_class": result.trend_class,
        "r_squared": result.r_squared,
        "volatility_cv": result.volatility_cv,
        "confidence_low_90d": result.confidence_low_90d,
        "confidence_high_90d": result.confidence_high_90d,
    }

    if budget_usd:
        overage = projected_month_end - budget_usd
        breach_pct = round((projected_month_end / budget_usd - 1) * 100, 1) if budget_usd else 0
        outlook["budget_usd"] = budget_usd
        outlook["projected_overage"] = round(overage, 2)
        outlook["budget_breach_pct"] = breach_pct
        outlook["budget_status"] = (
            "over_budget" if overage > 0 else
            "at_risk" if overage > -budget_usd * 0.1 else
            "on_track"
        )

    return outlook


def batch_forecast_resources(
    resources: list[dict[str, Any]],
    cost_histories: dict[str, list[float]],
    budget_by_resource: dict[str, float] | None = None,
) -> dict[str, ForecastResult]:
    """Run forecasts for multiple resources in one call.

    Args:
        resources: List of resource dicts with at least an ``id`` key.
        cost_histories: Resource ID → daily cost list (oldest first).
        budget_by_resource: Optional per-resource budget limits.

    Returns:
        Dict of resource_id → ForecastResult for resources with enough data.
    """
    budget_by_resource = budget_by_resource or {}
    results: dict[str, ForecastResult] = {}
    for resource in resources:
        rid = (resource.get("id") or "").lower().strip()
        if not rid:
            continue
        history = cost_histories.get(rid)
        if not history:
            continue
        budget = budget_by_resource.get(rid)
        forecast = forecast_resource(rid, history, budget_limit=budget)
        if forecast:
            results[rid] = forecast
    log.info(
        "cost_forecaster.batch_done",
        resources_attempted=len(resources),
        resources_forecasted=len(results),
    )
    return results

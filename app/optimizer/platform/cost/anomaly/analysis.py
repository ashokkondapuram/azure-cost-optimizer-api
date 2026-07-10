"""Cost anomaly detection from daily service spend trends."""
from __future__ import annotations

from typing import Any

from app.cost_windows import compare_rolling_daily_windows
from app.optimizer.core.finding import ExtendedFinding

_MIN_BASELINE_DAILY_USD = 1.0
_MIN_CURRENT_DAILY_USD = 10.0
_SPIKE_FACTOR_THRESHOLD = 1.5


def analyze_cost_anomalies(
    engine,
    subscription_id: str,
    cost_history: dict[str, list[float]],
    *,
    window_days: int = 7,
) -> list[ExtendedFinding]:
    """Detect services whose recent daily spend spiked versus the prior window."""
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("COST_SPIKE_DETECTED")
    if not rule or not rule.enabled or not cost_history:
        return out

    for service_name, series in cost_history.items():
        if not service_name or service_name == "__subscription__":
            continue

        comparison = compare_rolling_daily_windows(series, window_days=window_days)
        if not comparison.get("sufficient"):
            continue

        baseline_avg = float(comparison["baseline_avg"])
        current_avg = float(comparison["current_avg"])
        if (
            baseline_avg <= _MIN_BASELINE_DAILY_USD
            or current_avg <= baseline_avg * _SPIKE_FACTOR_THRESHOLD
            or current_avg <= _MIN_CURRENT_DAILY_USD
        ):
            continue

        spike_factor = float(comparison["spike_factor"] or (current_avg / baseline_avg))
        projected_overage = round((current_avg - baseline_avg) * 30, 2)
        severity = "HIGH" if spike_factor >= 3.0 else "MEDIUM"
        savings = projected_overage
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource={
                "id": f"/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/services/{service_name}",
                "name": service_name,
                "type": "cost/service",
            },
            detail=(
                f"Azure service '{service_name}' daily spend rose to ${current_avg:,.2f}/day "
                f"from a ${baseline_avg:,.2f}/day baseline over the prior {window_days} days ({spike_factor}×)."
            ),
            recommendation="Review Cost Management breakdown for this service and identify new or scaled resources driving the spike.",
            savings=savings,
            waste_score=62 if severity == "HIGH" else 52,
            confidence=75,
            priority="P1" if severity == "HIGH" else "P2",
            impact="Early detection of runaway service spend",
            evidence={
                "service_name": service_name,
                "comparison_window_days": window_days,
                "baseline_daily_usd": round(baseline_avg, 2),
                "current_daily_usd": round(current_avg, 2),
                "baseline_period_total_usd": comparison.get("baseline_total"),
                "current_period_total_usd": comparison.get("current_total"),
                "spike_factor": round(spike_factor, 2),
                "projected_overage_usd": projected_overage,
                "series_order": "oldest_first",
            },
        ))
        finding = out[-1]
        finding.severity = severity
    return out

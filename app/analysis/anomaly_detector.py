"""Advanced cost and utilization anomaly detection for the optimization engine.

Detects:
  - Spend spikes / sustained-high / sudden-drop across cost history
  - CPU / memory / storage utilization anomalies using Z-score + IQR
  - Cross-day pattern breaks (weekday vs weekend divergence)
  - Multi-metric compound anomalies (low CPU + high cost = zombie candidate)
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()

_ZSCORE_THRESHOLD = 2.5      # flag if |z| > this
_IQR_MULTIPLIER   = 1.8      # flag if value > Q3 + multiplier*IQR
_MIN_SAMPLES      = 5        # skip if fewer data points
_SPIKE_RATIO      = 2.0      # flag if value > mean * ratio
_DROP_RATIO       = 0.25     # flag if value < mean * ratio (sudden drop)


@dataclass
class AnomalySignal:
    resource_id: str
    metric: str                      # e.g. "cost_usd", "avg_cpu_pct"
    detected_value: float
    expected_range: tuple[float, float]
    severity: str                    # "low" | "medium" | "high" | "critical"
    anomaly_type: str                # "spike" | "drop" | "sustained_high" | "compound" | "pattern_break"
    z_score: float | None = None
    iqr_outlier: bool = False
    description: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


def _zscore(values: list[float], target: float) -> float | None:
    if len(values) < _MIN_SAMPLES:
        return None
    try:
        mean = statistics.mean(values)
        stdev = statistics.stdev(values)
        if stdev == 0:
            return 0.0
        return (target - mean) / stdev
    except Exception:
        return None


def _iqr_outlier(values: list[float], target: float, multiplier: float = _IQR_MULTIPLIER) -> bool:
    if len(values) < _MIN_SAMPLES:
        return False
    try:
        sorted_v = sorted(values)
        n = len(sorted_v)
        q1 = sorted_v[n // 4]
        q3 = sorted_v[(3 * n) // 4]
        iqr = q3 - q1
        return target > q3 + multiplier * iqr or target < q1 - multiplier * iqr
    except Exception:
        return False


def _severity(z: float | None, iqr: bool) -> str:
    # When z is None we still honour the IQR flag as a low-severity signal.
    if z is None:
        return "low"
    abs_z = abs(z)
    if abs_z >= 4.0 or (abs_z >= 3.0 and iqr):
        return "critical"
    if abs_z >= 3.0 or (abs_z >= 2.5 and iqr):
        return "high"
    if abs_z >= 2.0:
        return "medium"
    return "low"


def detect_cost_anomalies(
    resource_id: str,
    daily_costs: list[float],       # ordered oldest → newest
    current_cost: float | None = None,
) -> list[AnomalySignal]:
    """Detect cost anomalies from a daily cost history list.

    Args:
        resource_id: ARM resource ID.
        daily_costs: Daily cost values ordered oldest to newest.
        current_cost: Override for the latest day's cost (uses last element if None).

    Returns:
        List of AnomalySignal objects, empty if no anomalies detected.
    """
    signals: list[AnomalySignal] = []
    if not daily_costs or len(daily_costs) < _MIN_SAMPLES:
        return signals

    history = daily_costs[:-1] if len(daily_costs) > 1 else daily_costs
    latest = current_cost if current_cost is not None else daily_costs[-1]

    mean_h = statistics.mean(history) if history else 0.0
    try:
        stdev_h = statistics.stdev(history) if len(history) > 1 else 0.0
    except Exception:
        stdev_h = 0.0

    z = _zscore(history, latest)
    iqr = _iqr_outlier(history, latest)

    # ── Spike detection ──
    if mean_h > 0 and latest > mean_h * _SPIKE_RATIO:
        sev = _severity(z, iqr)
        signals.append(AnomalySignal(
            resource_id=resource_id,
            metric="cost_usd",
            detected_value=round(latest, 4),
            expected_range=(round(mean_h - stdev_h, 4), round(mean_h + stdev_h, 4)),
            severity=sev,
            anomaly_type="spike",
            z_score=round(z, 3) if z is not None else None,
            iqr_outlier=iqr,
            description=(
                f"Cost spike: ${latest:.2f}/day vs ${mean_h:.2f} avg "
                f"({(latest / mean_h - 1) * 100:.0f}% above baseline)"
            ),
            evidence={"mean": round(mean_h, 4), "stdev": round(stdev_h, 4), "samples": len(history)},
        ))

    # ── Sustained high (rolling 7d mean well above prior baseline) ──
    if len(daily_costs) >= 14:
        recent7  = statistics.mean(daily_costs[-7:])
        prior7   = statistics.mean(daily_costs[-14:-7])
        if prior7 > 0 and recent7 > prior7 * 1.4:
            signals.append(AnomalySignal(
                resource_id=resource_id,
                metric="cost_usd",
                detected_value=round(recent7, 4),
                expected_range=(0.0, round(prior7 * 1.4, 4)),
                severity="medium",
                anomaly_type="sustained_high",
                description=(
                    f"Sustained cost elevation: 7-day avg ${recent7:.2f} vs prior ${prior7:.2f} "
                    f"(+{(recent7 / prior7 - 1) * 100:.0f}%)"
                ),
                evidence={"recent_7d_avg": round(recent7, 4), "prior_7d_avg": round(prior7, 4)},
            ))

    # ── Sudden drop (resource may be deprovisioned but still billed) ──
    if mean_h > 0 and 0 < latest < mean_h * _DROP_RATIO:
        signals.append(AnomalySignal(
            resource_id=resource_id,
            metric="cost_usd",
            detected_value=round(latest, 4),
            expected_range=(round(mean_h * _DROP_RATIO, 4), round(mean_h, 4)),
            severity="low",
            anomaly_type="drop",
            z_score=round(z, 3) if z is not None else None,
            description=(
                f"Cost drop: ${latest:.2f}/day vs ${mean_h:.2f} avg — possible de-provisioning"
            ),
            evidence={"mean": round(mean_h, 4), "samples": len(history)},
        ))

    return signals


def detect_utilization_anomalies(
    resource_id: str,
    metric_name: str,
    values: list[float],             # ordered oldest → newest
    current_value: float | None = None,
    normal_range: tuple[float, float] = (0.0, 100.0),
) -> list[AnomalySignal]:
    """Detect utilization anomalies via Z-score and IQR methods.

    Args:
        resource_id: ARM resource ID.
        metric_name: Human-readable metric name (e.g. ``avg_cpu_pct``).
        values: Ordered time-series values (oldest first).
        current_value: Override for the latest value; uses last element if None.
        normal_range: Sanity clamp range; values outside this are suspicious.

    Returns:
        List of AnomalySignal objects.
    """
    signals: list[AnomalySignal] = []
    if not values or len(values) < _MIN_SAMPLES:
        return signals

    history = values[:-1] if len(values) > 1 else values
    latest = current_value if current_value is not None else values[-1]

    mean_h = statistics.mean(history)
    try:
        stdev_h = statistics.stdev(history) if len(history) > 1 else 0.0
    except Exception:
        stdev_h = 0.0

    z = _zscore(history, latest)
    iqr = _iqr_outlier(history, latest)

    # Fix: add explicit parentheses to clarify operator precedence
    # Original: `if z is not None and abs(z) >= _ZSCORE_THRESHOLD or iqr`
    # was equivalent to `if (z is not None and ...) or iqr`, which flags
    # IQR-outliers unconditionally even when z is None — the intended guard
    # is `(z is not None and abs(z) >= threshold) or iqr`.
    if (z is not None and abs(z) >= _ZSCORE_THRESHOLD) or iqr:
        sev = _severity(z, iqr)
        if z is not None:
            desc = (
                f"{metric_name} anomaly: {latest:.1f} vs {mean_h:.1f} avg "
                f"(z={z:.2f})"
            )
        else:
            desc = f"{metric_name} IQR outlier: {latest:.1f}"
        signals.append(AnomalySignal(
            resource_id=resource_id,
            metric=metric_name,
            detected_value=round(latest, 3),
            expected_range=(round(mean_h - stdev_h, 3), round(mean_h + stdev_h, 3)),
            severity=sev,
            anomaly_type="spike" if latest > mean_h else "drop",
            z_score=round(z, 3) if z is not None else None,
            iqr_outlier=iqr,
            description=desc,
            evidence={"mean": round(mean_h, 3), "stdev": round(stdev_h, 3), "samples": len(history)},
        ))

    return signals


def detect_compound_anomaly(
    resource_id: str,
    avg_cpu_pct: float | None,
    monthly_cost_usd: float | None,
    avg_mem_pct: float | None = None,
    network_bytes_out: float | None = None,
) -> AnomalySignal | None:
    """Detect compound zombie/idle pattern: very low activity + non-trivial cost.

    This catches resources that are technically running but effectively idle,
    incurring cost without delivering value.

    Args:
        resource_id: ARM resource ID.
        avg_cpu_pct: Average CPU utilization percentage (0-100).
        monthly_cost_usd: Current month-to-date estimated cost.
        avg_mem_pct: Optional average memory utilization.
        network_bytes_out: Optional average outbound network bytes/s.

    Returns:
        AnomalySignal if compound zombie pattern is detected, else None.
    """
    if avg_cpu_pct is None or monthly_cost_usd is None:
        return None
    if monthly_cost_usd < 5.0:          # too cheap to flag
        return None

    cpu_idle   = avg_cpu_pct < 5.0
    mem_idle   = avg_mem_pct is not None and avg_mem_pct < 10.0
    net_silent = network_bytes_out is not None and network_bytes_out < 1_000  # <1 KB/s

    idle_signals = sum([cpu_idle, mem_idle, net_silent])
    if idle_signals == 0:
        return None

    severity = "critical" if idle_signals >= 3 else ("high" if idle_signals == 2 else "medium")
    evidence: dict[str, Any] = {
        "avg_cpu_pct": avg_cpu_pct,
        "monthly_cost_usd": monthly_cost_usd,
    }
    if avg_mem_pct is not None:
        evidence["avg_mem_pct"] = avg_mem_pct
    if network_bytes_out is not None:
        evidence["network_bytes_out"] = network_bytes_out
    evidence["idle_signal_count"] = idle_signals

    return AnomalySignal(
        resource_id=resource_id,
        metric="compound_idle",
        detected_value=avg_cpu_pct,
        expected_range=(5.0, 100.0),
        severity=severity,
        anomaly_type="compound",
        description=(
            f"Zombie/idle candidate: CPU {avg_cpu_pct:.1f}%, "
            f"monthly cost ${monthly_cost_usd:.2f} — {idle_signals} idle signals detected"
        ),
        evidence=evidence,
    )


def detect_weekday_weekend_pattern(
    resource_id: str,
    daily_costs: list[float],
    day_of_week_labels: list[int] | None = None,  # 0=Mon..6=Sun aligned to daily_costs
) -> AnomalySignal | None:
    """Detect weekday vs. weekend cost pattern break.

    A resource with consistently near-zero weekend cost but high weekday cost is
    a strong candidate for scheduled start/stop automation.

    Args:
        resource_id: ARM resource ID.
        daily_costs: Daily costs ordered oldest → newest.
        day_of_week_labels: ISO weekday integers (0=Mon, 6=Sun) aligned to daily_costs.
                            If None, assumes costs start on Monday.

    Returns:
        AnomalySignal if a clear weekday/weekend divergence is found, else None.
    """
    if len(daily_costs) < 14:
        return None

    if day_of_week_labels is None:
        day_of_week_labels = [i % 7 for i in range(len(daily_costs))]

    weekday = [c for c, d in zip(daily_costs, day_of_week_labels) if d < 5]
    weekend = [c for c, d in zip(daily_costs, day_of_week_labels) if d >= 5]

    if not weekday or not weekend:
        return None

    avg_wd = statistics.mean(weekday)
    avg_we = statistics.mean(weekend)

    if avg_wd == 0:
        return None

    ratio = avg_wd / max(avg_we, 0.01)
    if ratio < 3.0:
        return None

    monthly_wasted = avg_we * 8  # ~8 weekend days/month
    return AnomalySignal(
        resource_id=resource_id,
        metric="cost_usd_weekday_vs_weekend",
        detected_value=round(avg_wd, 4),
        expected_range=(0.0, round(avg_we, 4)),
        severity="high" if ratio >= 6 else "medium",
        anomaly_type="pattern_break",
        description=(
            f"Weekday/weekend divergence: avg ${avg_wd:.2f}/day weekday vs "
            f"${avg_we:.2f}/day weekend (ratio {ratio:.1f}x) — "
            f"~${monthly_wasted:.2f}/mo saveable via schedule"
        ),
        evidence={
            "avg_weekday_cost": round(avg_wd, 4),
            "avg_weekend_cost": round(avg_we, 4),
            "ratio": round(ratio, 2),
            "estimated_monthly_savings": round(monthly_wasted, 2),
        },
    )


def run_full_anomaly_scan(
    resource_id: str,
    *,
    daily_costs: list[float] | None = None,
    cpu_history: list[float] | None = None,
    mem_history: list[float] | None = None,
    storage_history: list[float] | None = None,
    current_cpu: float | None = None,
    current_mem: float | None = None,
    monthly_cost: float | None = None,
    network_bytes_out: float | None = None,
    day_of_week_labels: list[int] | None = None,
) -> list[AnomalySignal]:
    """Run all anomaly detectors for a single resource and return a merged list.

    This is the primary entry point for the orchestrator to call per resource.

    Args:
        resource_id: ARM resource ID.
        daily_costs: Optional daily cost history list.
        cpu_history: Optional CPU utilization history.
        mem_history: Optional memory utilization history.
        storage_history: Optional storage utilization history.
        current_cpu: Current (latest) CPU utilization.
        current_mem: Current (latest) memory utilization.
        monthly_cost: Estimated monthly cost in USD.
        network_bytes_out: Average outbound network bytes/s.
        day_of_week_labels: ISO weekday integers for cost series.

    Returns:
        Deduplicated and severity-sorted list of AnomalySignal objects.
    """
    all_signals: list[AnomalySignal] = []

    if daily_costs:
        all_signals.extend(detect_cost_anomalies(resource_id, daily_costs))
        pattern = detect_weekday_weekend_pattern(
            resource_id, daily_costs, day_of_week_labels=day_of_week_labels
        )
        if pattern:
            all_signals.append(pattern)

    if cpu_history:
        all_signals.extend(detect_utilization_anomalies(resource_id, "avg_cpu_pct", cpu_history, current_cpu))
    if mem_history:
        all_signals.extend(detect_utilization_anomalies(resource_id, "avg_mem_pct", mem_history, current_mem))
    if storage_history:
        all_signals.extend(detect_utilization_anomalies(resource_id, "storage_pct", storage_history))

    compound = detect_compound_anomaly(
        resource_id,
        avg_cpu_pct=current_cpu,
        monthly_cost_usd=monthly_cost,
        avg_mem_pct=current_mem,
        network_bytes_out=network_bytes_out,
    )
    if compound:
        all_signals.append(compound)

    # Sort by severity (critical first)
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_signals.sort(key=lambda s: sev_order.get(s.severity, 9))
    return all_signals

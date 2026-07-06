"""Rightsizing confidence scoring for VM and database resize recommendations.

The engine may produce a rightsizing suggestion (e.g. resize VM from D4s_v3 →
D2s_v3) but the *confidence* in that suggestion depends on many signals:

  - Observation window length (more days = higher confidence)
  - CPU/memory/disk utilization stability (low CV = higher confidence)
  - Workload classification (batch vs interactive vs critical)
  - Presence of corroborating Azure Advisor recommendation
  - Forecast trend direction (declining trend supports downsizing)
  - Maintenance window / change freeze (reduces recommended action confidence)

Output: a ``RightsizingConfidence`` dataclass that the finding engine attaches
to each rightsizing finding.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class RightsizingConfidence:
    resource_id: str
    action: str                      # "downsize" | "upsize" | "rightsize" | "delete"
    confidence_score: float          # 0.0–1.0
    confidence_band: str             # "very_high" | "high" | "medium" | "low" | "speculative"
    safe_to_automate: bool           # True only for high/very_high without change freeze
    observation_days: int
    utilization_stable: bool
    corroborated_by_advisor: bool
    trend_supports_action: bool
    change_freeze_active: bool
    blocking_reasons: list[str] = field(default_factory=list)
    supporting_reasons: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


_BAND_THRESHOLDS = [
    (0.85, "very_high"),
    (0.70, "high"),
    (0.50, "medium"),
    (0.30, "low"),
    (0.00, "speculative"),
]


def _band(score: float) -> str:
    for threshold, band in _BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return "speculative"


def _cv(values: list[float]) -> float:
    """Coefficient of variation — lower means more stable."""
    if not values or len(values) < 2:
        return 1.0
    try:
        mean = statistics.mean(values)
        if mean == 0:
            return 0.0
        return statistics.stdev(values) / mean
    except Exception:
        return 1.0


def score_rightsizing_confidence(
    resource_id: str,
    action: str,
    *,
    observation_days: int = 0,
    cpu_history: list[float] | None = None,
    mem_history: list[float] | None = None,
    avg_cpu_pct: float | None = None,
    avg_mem_pct: float | None = None,
    peak_cpu_pct: float | None = None,
    workload_class: str | None = None,     # "batch" | "interactive" | "critical" | "idle"
    advisor_corroborated: bool = False,
    trend_class: str | None = None,        # "growing" | "stable" | "declining" | "volatile"
    change_freeze: bool = False,
    maintenance_hold: bool = False,
    business_criticality: str | None = None,  # "low" | "medium" | "high" | "critical"
) -> RightsizingConfidence:
    """Compute confidence for a rightsizing recommendation.

    Args:
        resource_id: ARM resource ID.
        action: Recommended action type (``downsize``, ``delete``, etc.).
        observation_days: How many days of utilization data were used.
        cpu_history: Optional list of daily CPU utilization pct values.
        mem_history: Optional list of daily memory utilization pct values.
        avg_cpu_pct: Average CPU utilization (summary fallback).
        avg_mem_pct: Average memory utilization (summary fallback).
        peak_cpu_pct: Peak CPU seen in the observation window.
        workload_class: Detected workload classification.
        advisor_corroborated: True if Azure Advisor echoes the same action.
        trend_class: Cost/utilization trend from the forecaster.
        change_freeze: Whether a change freeze is active.
        maintenance_hold: Whether a maintenance window is active.
        business_criticality: Business criticality tag value.

    Returns:
        RightsizingConfidence with computed score and automation flag.
    """
    score = 0.0
    supporting: list[str] = []
    blocking: list[str] = []

    # ── Observation window (0.0–0.25) ──
    if observation_days >= 28:
        score += 0.25
        supporting.append(f"{observation_days}-day observation window provides strong signal.")
    elif observation_days >= 14:
        score += 0.15
        supporting.append(f"{observation_days}-day window; extending to 28+ days increases confidence.")
    elif observation_days >= 7:
        score += 0.08
    else:
        blocking.append("Less than 7 days of utilization data — observation window too short.")

    # ── Utilization stability (0.0–0.25) ──
    cpu_cv   = _cv(cpu_history) if cpu_history else None
    mem_cv   = _cv(mem_history) if mem_history else None
    avg_cv   = statistics.mean([v for v in [cpu_cv, mem_cv] if v is not None]) if (cpu_cv or mem_cv) else None

    utilization_stable = False
    if avg_cv is not None:
        if avg_cv < 0.15:
            score += 0.25
            utilization_stable = True
            supporting.append("Very stable utilization pattern (CV < 15%).")
        elif avg_cv < 0.30:
            score += 0.15
            utilization_stable = True
            supporting.append("Moderately stable utilization (CV < 30%).")
        elif avg_cv < 0.50:
            score += 0.08
        else:
            blocking.append("High utilization variance — workload may be bursty; downsizing risky.")
    elif avg_cpu_pct is not None:
        # No history, use summary stats
        if action == "downsize" and avg_cpu_pct < 15:
            score += 0.15
            utilization_stable = True
            supporting.append(f"Low average CPU ({avg_cpu_pct:.1f}%) supports downsizing.")
        elif action == "downsize" and avg_cpu_pct < 30:
            score += 0.08
    else:
        blocking.append("No utilization data available — confidence is speculative.")
        utilization_stable = False

    # ── Peak safety check (downsize actions) ──
    if action == "downsize" and peak_cpu_pct is not None:
        if peak_cpu_pct > 85:
            score -= 0.15
            blocking.append(f"Peak CPU {peak_cpu_pct:.1f}% — downsize may cause throttling under load.")
        elif peak_cpu_pct > 70:
            score -= 0.05
            blocking.append(f"Peak CPU {peak_cpu_pct:.1f}% — monitor after resize.")

    # ── Advisor corroboration (0.0–0.15) ──
    if advisor_corroborated:
        score += 0.15
        supporting.append("Azure Advisor corroborates this recommendation.")

    # ── Trend alignment (0.0–0.15) ──
    trend_supports = False
    if trend_class == "declining" and action in {"downsize", "delete"}:
        score += 0.15
        trend_supports = True
        supporting.append("Declining cost/utilization trend strongly supports downsizing.")
    elif trend_class == "stable" and action == "downsize":
        score += 0.08
        trend_supports = True
        supporting.append("Stable trend supports rightsizing.")
    elif trend_class == "growing" and action == "downsize":
        score -= 0.10
        blocking.append("Growing utilization trend — downsizing now may create headroom problems.")
    elif trend_class == "volatile":
        score -= 0.05
        blocking.append("Volatile utilization trend increases rightsizing risk.")

    # ── Business criticality penalty ──
    if business_criticality in {"high", "critical"} and action in {"downsize", "delete"}:
        score -= 0.15
        blocking.append(f"High business criticality ({business_criticality}) — extra caution required.")
    elif business_criticality == "low":
        score += 0.05
        supporting.append("Low business criticality enables more aggressive optimization.")

    # ── Workload class adjustments ──
    if workload_class == "critical":
        score -= 0.20
        blocking.append("Workload classified as critical — automation disabled.")
    elif workload_class == "idle":
        score += 0.10
        supporting.append("Workload classified as idle — deletion/deallocation is safe.")
    elif workload_class == "batch":
        score += 0.05
        supporting.append("Batch workload tolerates resizing between job runs.")

    # ── Change freeze / maintenance hold ──
    if change_freeze or maintenance_hold:
        score -= 0.30
        blocking.append(
            "Change freeze or maintenance window active — automated actions suppressed until resolved."
        )

    score = max(0.0, min(1.0, score))
    band = _band(score)
    safe = band in {"very_high", "high"} and not change_freeze and not maintenance_hold

    return RightsizingConfidence(
        resource_id=resource_id,
        action=action,
        confidence_score=round(score, 4),
        confidence_band=band,
        safe_to_automate=safe,
        observation_days=observation_days,
        utilization_stable=utilization_stable,
        corroborated_by_advisor=advisor_corroborated,
        trend_supports_action=trend_supports,
        change_freeze_active=change_freeze or maintenance_hold,
        blocking_reasons=blocking,
        supporting_reasons=supporting,
        evidence={
            "cpu_cv": round(cpu_cv, 4) if cpu_cv is not None else None,
            "mem_cv": round(mem_cv, 4) if mem_cv is not None else None,
            "avg_cpu_pct": avg_cpu_pct,
            "avg_mem_pct": avg_mem_pct,
            "peak_cpu_pct": peak_cpu_pct,
            "workload_class": workload_class,
            "trend_class": trend_class,
            "business_criticality": business_criticality,
        },
    )


def enrich_findings_with_confidence(
    findings: list[dict[str, Any]],
    resource_facts: dict[str, dict[str, Any]],
    advisor_by_resource: dict[str, bool] | None = None,
    trend_by_resource: dict[str, str] | None = None,
    maintenance_index: dict[str, bool] | None = None,
    workload_classes: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Attach rightsizing confidence to each eligible finding in-place.

    Eligible findings are those with ``rule_id`` containing
    'rightsize', 'underutilized', 'idle', 'resize', or 'delete'.

    Args:
        findings: List of finding dicts from the optimization engine.
        resource_facts: Resource ID → extracted utilization fact dict.
        advisor_by_resource: Resource ID → True if Azure Advisor corroborates.
        trend_by_resource: Resource ID → trend class from cost forecaster.
        maintenance_index: Resource ID → True if maintenance hold is active.
        workload_classes: Resource ID → workload class string.

    Returns:
        Same list with ``rightsizing_confidence`` attached to eligible findings.
    """
    advisor_by_resource = advisor_by_resource or {}
    trend_by_resource   = trend_by_resource or {}
    maintenance_index   = maintenance_index or {}
    workload_classes    = workload_classes or {}

    ELIGIBLE_KEYWORDS = {"rightsize", "underutilized", "idle", "resize", "delete", "deallocate", "downsize"}

    for finding in findings:
        rule_id = (finding.get("rule_id") or "").lower()
        if not any(kw in rule_id for kw in ELIGIBLE_KEYWORDS):
            continue

        rid = (finding.get("resource_id") or "").lower().strip()
        facts = resource_facts.get(rid) or {}
        action = "delete" if "delete" in rule_id else "downsize"

        conf = score_rightsizing_confidence(
            resource_id=rid,
            action=action,
            observation_days=int(facts.get("observation_days") or 0),
            avg_cpu_pct=facts.get("avg_cpu_pct"),
            avg_mem_pct=facts.get("avg_mem_pct"),
            peak_cpu_pct=facts.get("peak_cpu_pct"),
            workload_class=workload_classes.get(rid),
            advisor_corroborated=advisor_by_resource.get(rid, False),
            trend_class=trend_by_resource.get(rid),
            maintenance_hold=maintenance_index.get(rid, False),
        )

        finding["rightsizing_confidence"] = {
            "score": conf.confidence_score,
            "band": conf.confidence_band,
            "safe_to_automate": conf.safe_to_automate,
            "blocking_reasons": conf.blocking_reasons,
            "supporting_reasons": conf.supporting_reasons,
            "observation_days": conf.observation_days,
            "corroborated_by_advisor": conf.corroborated_by_advisor,
        }

    return findings

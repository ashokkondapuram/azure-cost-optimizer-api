"""Human-readable insights for resource advanced analysis."""
from __future__ import annotations

from typing import Any


def _workload_insights(workload: dict[str, Any] | None, evidence: dict[str, Any] | None) -> list[dict[str, str]]:
    if not workload:
        return [{
            "label": "Workload profile",
            "value": "Not available",
            "detail": "Run advanced scoring after Azure Monitor metrics are synced.",
            "tone": "muted",
        }]

    items: list[dict[str, str]] = []
    has_metrics = bool(evidence and evidence.get("has_monitor_data"))
    avg_cpu = evidence.get("avg_cpu_pct") if evidence else None
    max_cpu = evidence.get("max_cpu_pct") if evidence else None

    wtype = (workload.get("workload_type") or "unknown").lower()
    type_copy = {
        "steady": ("Steady", "Usage stays flat — good fit for reserved capacity or fixed SKUs."),
        "bursty": ("Bursty", "Usage spikes often — prefer autoscale or burst-tolerant sizing."),
        "interactive": ("Interactive", "User-facing pattern — validate latency before downsizing."),
    }
    title, detail = type_copy.get(wtype, (wtype.title(), "Classified from tags and utilization shape."))
    items.append({"label": "Pattern", "value": title, "detail": detail, "tone": "neutral"})

    burst = workload.get("burstiness_score")
    if burst is None:
        burst_label = "—"
        burst_detail = "Burstiness not calculated."
        burst_tone = "muted"
    elif not has_metrics and float(burst) == 0:
        burst_label = "No spike data"
        burst_detail = "Sync CPU metrics to measure how much peak exceeds average."
        burst_tone = "muted"
    elif float(burst) < 20:
        burst_label = "Low"
        burst_detail = "Peaks stay close to average — predictable capacity needs."
        burst_tone = "positive"
    elif float(burst) < 40:
        burst_label = "Moderate"
        burst_detail = "Some spikes above average — leave headroom or use burst SKUs."
        burst_tone = "caution"
    else:
        burst_label = "High"
        burst_detail = "Large gaps between average and peak — cost is driven by spikes."
        burst_tone = "warning"

    items.append({
        "label": "Burstiness",
        "value": burst_label,
        "detail": burst_detail,
        "tone": burst_tone,
    })

    peak = workload.get("peak_hour_factor")
    if peak is None:
        peak_label = "—"
        peak_detail = "Peak factor not available."
        peak_tone = "muted"
    elif not has_metrics and float(peak) <= 1:
        peak_label = "Unknown"
        peak_detail = "Needs Monitor history to compare peak vs average CPU."
        peak_tone = "muted"
    elif float(peak) < 1.3:
        peak_label = "Flat"
        peak_detail = "Peak usage is near average — very consistent load."
        peak_tone = "positive"
    elif float(peak) < 2.0:
        peak_label = f"{float(peak):.1f}× average"
        peak_detail = "Moderate peaks — rightsizing should target average, not peak."
        peak_tone = "caution"
    else:
        peak_label = f"{float(peak):.1f}× average"
        peak_detail = "Peak is much higher than average — avoid undersizing for peak hours."
        peak_tone = "warning"

    items.append({
        "label": "Peak vs average",
        "value": peak_label,
        "detail": peak_detail,
        "tone": peak_tone,
    })

    trend_raw = workload.get("utilization_trend")
    if isinstance(trend_raw, dict):
        trend = (trend_raw.get("slope") or "unknown").lower()
    else:
        trend = (trend_raw or "unknown").lower()
    if trend == "unknown" or (not has_metrics and trend in {"unknown", "stable"}):
        trend_label = "Insufficient data"
        trend_detail = "Need at least two weeks of Monitor metrics for a reliable trend."
        trend_tone = "muted"
    elif trend == "increasing":
        trend_label = "Rising"
        trend_detail = "Utilization is climbing — review growth before reducing size."
        trend_tone = "warning"
    elif trend == "decreasing":
        trend_label = "Falling"
        trend_detail = "Utilization is dropping — rightsizing may be appropriate."
        trend_tone = "positive"
    else:
        trend_label = "Stable"
        trend_detail = "Utilization is holding steady month over month."
        trend_tone = "neutral"

    items.append({
        "label": "Utilization trend",
        "value": trend_label,
        "detail": trend_detail,
        "tone": trend_tone,
    })

    if has_metrics and avg_cpu is not None:
        cpu_detail = f"Average CPU {avg_cpu:.1f}%"
        if max_cpu is not None:
            cpu_detail += f", peak {max_cpu:.1f}%"
        items.append({
            "label": "CPU evidence",
            "value": f"{avg_cpu:.0f}% avg",
            "detail": cpu_detail,
            "tone": "neutral",
        })

    if workload.get("detected_seasonality"):
        peak_pct = workload.get("seasonal_peak_percentage")
        detail = "Recurring weekly swings detected in utilization history."
        if peak_pct is not None:
            detail = f"Seasonal peaks run about {peak_pct:.0f}% above baseline."
        items.append({
            "label": "Seasonality",
            "value": "Detected",
            "detail": detail,
            "tone": "caution",
        })

    return items


def _dependency_insights(deps: dict[str, Any] | None) -> list[dict[str, str]]:
    if not deps:
        return [{
            "label": "Dependencies",
            "value": "Not analyzed",
            "detail": "Dependency graph has not been built for this subscription.",
            "tone": "muted",
        }]

    items: list[dict[str, str]] = []
    blast = int(deps.get("blast_radius") or 0)
    outbound = len(deps.get("direct_outbound") or [])
    inbound = len(deps.get("direct_inbound") or [])
    transitive = int(deps.get("transitive_dependent_count") or 0)

    if blast == 0 and outbound == 0 and inbound == 0:
        blast_label = "Isolated"
        blast_detail = "No mapped dependencies — changes likely affect only this resource."
        blast_tone = "positive"
    elif blast <= 2:
        blast_label = f"{blast} linked"
        blast_detail = f"{outbound} outbound · {inbound} inbound dependencies."
        blast_tone = "neutral"
    elif blast <= 5:
        blast_label = f"{blast} linked"
        blast_detail = f"{transitive} resources may be indirectly affected."
        blast_tone = "caution"
    else:
        blast_label = f"{blast} linked"
        blast_detail = f"Wide impact — {transitive} transitive dependents. Schedule changes carefully."
        blast_tone = "warning"

    items.append({
        "label": "Change impact",
        "value": blast_label,
        "detail": blast_detail,
        "tone": blast_tone,
    })

    crit = (deps.get("max_criticality") or "low").lower()
    crit_copy = {
        "critical": ("Critical", "Highest tagged criticality in the dependency chain."),
        "high": ("High", "Production or high-value neighbors in the graph."),
        "medium": ("Medium", "Mixed staging or moderate-cost neighbors."),
        "low": ("Low", "No high-criticality neighbors detected."),
    }
    crit_title, crit_detail = crit_copy.get(crit, (crit.title(), ""))
    items.append({
        "label": "Neighbor criticality",
        "value": crit_title,
        "detail": crit_detail,
        "tone": "warning" if crit in {"critical", "high"} else "neutral",
    })

    sla = (deps.get("sla_tier") or "none").lower()
    if sla == "none":
        sla_label = "Not tagged"
        sla_detail = "No SLA tag found — use default caution for production changes."
        sla_tone = "muted"
    elif sla == "gold":
        sla_label = "Gold"
        sla_detail = "High SLA tier — avoid risky optimizations without approval."
        sla_tone = "warning"
    elif sla == "silver":
        sla_label = "Silver"
        sla_detail = "Standard production SLA — balance savings with uptime."
        sla_tone = "caution"
    else:
        sla_label = sla.title()
        sla_detail = "SLA tag present — weigh savings against availability targets."
        sla_tone = "neutral"

    items.append({
        "label": "SLA tier",
        "value": sla_label,
        "detail": sla_detail,
        "tone": sla_tone,
    })

    if deps.get("compliance_locked"):
        items.append({
            "label": "Compliance",
            "value": "Locked",
            "detail": "Tagged as compliance-locked — automated changes may be blocked.",
            "tone": "warning",
        })

    return items


def _cost_insights(trends: dict[str, Any] | None) -> list[dict[str, str]]:
    if not trends:
        return [{
            "label": "Cost trend",
            "value": "Unknown",
            "detail": "No billing history for this resource yet.",
            "tone": "muted",
        }]

    trajectory = (trends.get("cost_trajectory") or "stable").lower()
    pct = trends.get("cost_vs_prev_month_pct")
    monthly = trends.get("monthly_cost_usd")

    if pct is None and trajectory == "stable":
        value = "Stable"
        detail = "Spend is unchanged vs the prior billed month."
        tone = "neutral"
        if monthly is not None and monthly <= 0:
            value = "No recent cost"
            detail = "This resource has little or no billed spend in the current period."
            tone = "muted"
    elif trajectory == "increasing":
        value = f"Up {abs(float(pct or 0)):.1f}%" if pct is not None else "Increasing"
        detail = "Monthly spend is growing — validate usage before downsizing elsewhere."
        tone = "warning"
    elif trajectory == "decreasing":
        value = f"Down {abs(float(pct or 0)):.1f}%" if pct is not None else "Decreasing"
        detail = "Spend is falling — good time to capture savings or rightsize."
        tone = "positive"
    else:
        value = "Stable"
        detail = "Month-over-month spend is within ±10%."
        tone = "neutral"

    items = [{
        "label": "Cost trend",
        "value": value,
        "detail": detail,
        "tone": tone,
    }]

    if monthly is not None and monthly > 0:
        items.append({
            "label": "Monthly spend",
            "value": f"${monthly:,.0f}",
            "detail": "Current period billed cost used for scoring.",
            "tone": "neutral",
        })

    return items


def build_advanced_insights(
    *,
    workload: dict[str, Any] | None,
    dependencies: dict[str, Any] | None,
    trends: dict[str, Any] | None,
    utilization_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workload_items = _workload_insights(workload, utilization_evidence)
    dependency_items = _dependency_insights(dependencies)
    cost_items = _cost_insights(trends)

    has_metrics = bool(utilization_evidence and utilization_evidence.get("has_monitor_data"))
    insufficient = bool(trends and trends.get("insufficient_history"))

    if not has_metrics and insufficient:
        headline = "Limited telemetry — sync Azure Monitor metrics and billing to unlock workload and trend insights."
    elif not has_metrics:
        headline = "Workload signals are estimated from tags — sync Monitor metrics for CPU-backed evidence."
    elif workload and (
        (isinstance(workload.get("utilization_trend"), dict) and workload["utilization_trend"].get("insufficient_history"))
        or (not isinstance(workload.get("utilization_trend"), dict) and (workload.get("utilization_trend") or "unknown") == "unknown")
    ):
        headline = "CPU metrics are present but more history is needed for utilization trends."
    else:
        headline = "Signals below summarize how safe it is to optimize this resource."

    return {
        "headline": headline,
        "workload": workload_items,
        "dependencies": dependency_items,
        "cost": cost_items,
        "data_quality": {
            "has_monitor_data": has_metrics,
            "insufficient_history": insufficient,
        },
    }

"""Shared types and builders for per-resource technical fetch and utilization specs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UsageMetricDef:
    """Runtime usage signal used to determine utilization and savings."""
    source: str  # azure_monitor | k8s_agent | arm_properties | cost_export
    metric_name: str
    fact_key: str
    description: str
    timespan: str = "P7D"
    rules: tuple[str, ...] = ()
    aggregation: str = "Average"  # Average | Total | Maximum | Minimum | Count


@dataclass(frozen=True)
class TechnicalFieldDef:
    """One technical fact derived from synced inventory."""
    fact_key: str
    source: str  # row:sku | props:hardwareProfile.vmSize | tag:Environment | computed:...
    label: str
    category: str  # configuration | association | utilization | governance | capacity
    rules: tuple[str, ...] = ()


@dataclass(frozen=True)
class TechnicalFetchSpec:
    canonical_type: str
    arm_type: str
    display_name: str
    sync_property_paths: tuple[str, ...] = ()
    fields: tuple[TechnicalFieldDef, ...] = ()
    usage_metrics: tuple[UsageMetricDef, ...] = ()
    generic_arm_sync: bool = False
    enrich_if_missing: tuple[str, ...] = ()
    enrich_if_empty: tuple[str, ...] = ()


@dataclass(frozen=True)
class UtilizationMetric:
    """One Azure Monitor metric for utilization analysis."""
    metric_name: str
    fact_key: str
    description: str
    aggregation: str = "Average"
    timespan: str = "P7D"
    rules: tuple[str, ...] = ()
    unit: str = ""
    primary_stat: str = ""
    display_stats: tuple[str, ...] = ()
    supported_aggregations: tuple[str, ...] = ()
    impact: str = ""  # cost | performance | both


DEFAULT_DISPLAY_STATS: tuple[str, ...] = (
    "average", "minimum", "maximum",
)

COUNT_DISPLAY_STATS: tuple[str, ...] = ("total", "average", "maximum", "minimum")

# Azure Monitor series keys we request via STANDARD_AGGREGATIONS (not client-side percentiles).
AZURE_MONITOR_STAT_KEYS: frozenset[str] = frozenset({
    "average", "minimum", "maximum", "total", "count",
})


def display_stats_for_aggregation(aggregation: str = "Average") -> tuple[str, ...]:
    """Map Monitor aggregation to display columns supported by the Azure metrics API."""
    agg = (aggregation or "Average").strip().lower()
    if agg == "total":
        return ("total", "average", "maximum", "minimum")
    if agg == "count":
        return ("count", "total", "average", "maximum")
    if agg == "maximum":
        return ("maximum", "average", "minimum")
    if agg == "minimum":
        return ("minimum", "average", "maximum")
    return DEFAULT_DISPLAY_STATS


def primary_stat_for_aggregation(aggregation: str = "Average") -> str:
    agg = (aggregation or "Average").strip().lower()
    if agg in {"average", "maximum", "minimum", "total", "count"}:
        return agg
    return "average"


def filter_stats_for_display(
    stats: dict[str, float | None],
    display_stats: tuple[str, ...] | list[str],
) -> dict[str, float | None]:
    keys = [k for k in display_stats if k in AZURE_MONITOR_STAT_KEYS]
    if not keys:
        keys = [k for k in stats if k in AZURE_MONITOR_STAT_KEYS]
    return {k: stats.get(k) for k in keys}


def infer_metric_metadata(fact_key: str, aggregation: str = "Average") -> dict[str, str | tuple[str, ...]]:
    """Infer unit, primary stat, display columns, and cost/performance impact from fact_key."""
    key = (fact_key or "").lower()

    if key.endswith("_pct") or key.endswith("_percent") or "cpu" in key or key.endswith("_mem_pct"):
        stats = display_stats_for_aggregation(aggregation)
        return {
            "unit": "percent",
            "primary_stat": primary_stat_for_aggregation(aggregation),
            "display_stats": stats,
            "impact": "both",
        }
    if key.endswith("_bytes") or key.endswith("_bps") or "throughput" in key or "capacity" in key:
        stats = display_stats_for_aggregation(aggregation)
        return {
            "unit": "bytes_per_sec" if key.endswith("_bps") or "throughput" in key else "bytes",
            "primary_stat": primary_stat_for_aggregation(aggregation),
            "display_stats": stats,
            "impact": "cost",
        }
    if key.endswith("_iops") or "queue_depth" in key:
        stats = display_stats_for_aggregation(aggregation)
        return {
            "unit": "count",
            "primary_stat": primary_stat_for_aggregation(aggregation),
            "display_stats": stats,
            "impact": "performance",
        }
    if key.endswith("_sec") or "duration" in key or "query_duration" in key:
        stats = display_stats_for_aggregation(aggregation)
        return {
            "unit": "seconds",
            "primary_stat": primary_stat_for_aggregation(aggregation),
            "display_stats": stats,
            "impact": "performance",
        }
    if key.endswith("_gb") or key == "ingestion_gb":
        stats = display_stats_for_aggregation(aggregation)
        return {
            "unit": "gb",
            "primary_stat": primary_stat_for_aggregation(aggregation),
            "display_stats": stats,
            "impact": "cost",
        }
    if "count" in key or "hits" in key or "requests" in key or "messages" in key or "runs" in key or "pull" in key or key.endswith("_ru"):
        return {
            "unit": "count",
            "primary_stat": "total",
            "display_stats": COUNT_DISPLAY_STATS,
            "impact": "cost",
        }
    if "ops_per_sec" in key or key.endswith("_qps"):
        stats = display_stats_for_aggregation("Maximum")
        return {
            "unit": "count",
            "primary_stat": "maximum",
            "display_stats": stats,
            "impact": "performance",
        }
    if "availability" in key:
        stats = display_stats_for_aggregation(aggregation)
        return {
            "unit": "percent",
            "primary_stat": primary_stat_for_aggregation(aggregation),
            "display_stats": stats,
            "impact": "performance",
        }
    stats = display_stats_for_aggregation(aggregation)
    return {
        "unit": "number",
        "primary_stat": primary_stat_for_aggregation(aggregation),
        "display_stats": stats,
        "impact": "both",
    }


@dataclass(frozen=True)
class ResourceMonitorProfile:
    """Monitor metrics for a single ARM resource type."""
    monitor_arm_type: str
    canonical_type: str
    display_name: str
    metrics: tuple[UtilizationMetric, ...]
    doc_ref: str = ""

    def metric_names(self) -> tuple[str, ...]:
        return tuple(m.metric_name for m in self.metrics)

    def aggregations(self) -> str:
        from app.azure_monitor_aggregations import fetch_aggregations_for_profile

        return fetch_aggregations_for_profile(self.metrics)


def field(
    fact_key: str,
    source: str,
    label: str,
    category: str,
    *rules: str,
) -> TechnicalFieldDef:
    return TechnicalFieldDef(fact_key, source, label, category, rules)


def metric(
    source: str,
    metric_name: str,
    fact_key: str,
    description: str,
    timespan: str = "P7D",
    *rules: str,
    aggregation: str = "Maximum",
) -> UsageMetricDef:
    return UsageMetricDef(source, metric_name, fact_key, description, timespan, rules, aggregation)


def utilization_metric(
    metric_name: str,
    fact_key: str,
    description: str,
    *,
    aggregation: str = "Maximum",
    timespan: str = "P7D",
    rules: tuple[str, ...] = (),
    unit: str = "",
    primary_stat: str = "",
    display_stats: tuple[str, ...] = (),
    impact: str = "",
) -> UtilizationMetric:
    meta = infer_metric_metadata(fact_key, aggregation)
    return UtilizationMetric(
        metric_name=metric_name,
        fact_key=fact_key,
        description=description,
        aggregation=aggregation,
        timespan=timespan,
        rules=rules,
        unit=unit or str(meta["unit"]),
        primary_stat=primary_stat or str(meta["primary_stat"]),
        display_stats=display_stats or tuple(meta["display_stats"]),  # type: ignore[arg-type]
        impact=impact or str(meta["impact"]),
    )


def get_nested(obj: dict[str, Any] | None, path: str) -> Any:
    cur: Any = obj or {}
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def sku_text(sku: Any) -> str:
    if isinstance(sku, dict):
        name = sku.get("name")
        if name not in (None, ""):
            return str(name)
        tier = sku.get("tier")
        return str(tier or "")
    text = str(sku or "").strip()
    if not text:
        return ""
    # Legacy inventory labels stored as "Premium_LRS (Premium)" — show ARM name only.
    if " (" in text and text.endswith(")"):
        return text.rsplit(" (", 1)[0]
    return text

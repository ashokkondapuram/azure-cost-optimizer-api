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
    sync_as_standalone: bool = True
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
    stats = display_stats_for_aggregation(aggregation)
    primary = primary_stat_for_aggregation(aggregation)

    def meta(
        unit: str,
        impact: str,
        *,
        primary_stat: str | None = None,
        display_stats_override: tuple[str, ...] | None = None,
    ) -> dict[str, str | tuple[str, ...]]:
        return {
            "unit": unit,
            "primary_stat": primary_stat or primary,
            "display_stats": display_stats_override or stats,
            "impact": impact,
        }

    # Misleading fact keys — explicit overrides before pattern rules.
    if key == "ingestion_bytes":
        return meta("mb", "cost", primary_stat="total")
    if key in {"byte_count", "byte_count_peak"}:
        return meta("bytes", "cost", primary_stat=primary_stat_for_aggregation(aggregation))
    if key == "provisioned_throughput":
        return meta("number", "cost", primary_stat="maximum")

    # Time
    if key.endswith("_ms"):
        return meta("milliseconds", "performance")
    if "ops_per_sec" in key or key.endswith("_qps"):
        return meta("count", "performance", primary_stat="maximum")
    if key.endswith("_sec") or key.endswith("_lag_sec"):
        return meta("seconds", "performance")

    # Percent utilization
    if key.endswith("_pct") or key.endswith("_percent") or key.endswith("_mem_pct"):
        return meta("percent", "both")
    if "cpu" in key:
        return meta("percent", "both")

    # Throughput rates
    if key.endswith("_bps") or (key.endswith("_rate") and "bytes" in key):
        return meta("bytes_per_sec", "cost")
    if "throughput" in key and "bytes" in key:
        return meta("bytes_per_sec", "cost")

    # Byte volumes (including pe_bytes_in / ddos_bytes_dropped style keys)
    if (
        key.endswith("_bytes")
        or "_bytes_" in key
        or key.endswith("_bytes_in")
        or key.endswith("_bytes_out")
        or "bytes_dropped" in key
    ):
        return meta("bytes", "cost")

    if key.endswith("_iops") or "queue_depth" in key:
        return meta("count", "performance")

    if key.endswith("_gb") or key == "ingestion_gb":
        return meta("gb", "cost")

    # Count-style metrics — use suffix match so byte_count stays bytes.
    if (
        key.endswith("_count")
        or key.endswith("_ru")
        or key.endswith("_hits")
        or key.endswith("_messages")
        or "requests" in key
        or "runs_" in key
        or key.endswith("_pull")
        or key.endswith("_push")
    ):
        return meta("count", "cost", primary_stat="total", display_stats_override=COUNT_DISPLAY_STATS)

    if "availability" in key:
        return meta("percent", "performance")

    return meta("number", "both")


def _format_bytes_display(num: float) -> str:
    if num >= 1_073_741_824:
        return f"{num / 1_073_741_824:.2f} GB"
    if num >= 1_048_576:
        return f"{num / 1_048_576:.1f} MB"
    if num >= 1024:
        return f"{num / 1024:.1f} KB"
    return f"{num:.0f} B"


def _format_bytes_per_sec_display(num: float) -> str:
    if num >= 1_048_576:
        return f"{num / 1_048_576:.2f} MB/s"
    if num >= 1024:
        return f"{num / 1024:.1f} KB/s"
    return f"{num:.0f} B/s"


def _format_seconds_display(num: float) -> str:
    if num >= 3600:
        return f"{num / 3600:,.2f} hr"
    if num >= 60:
        return f"{num / 60:,.1f} min"
    return f"{num:,.2f} s"


def format_fact_display_value(
    fact_key: str,
    value: Any,
    unit: str | None = None,
) -> str:
    """Human-readable metric/inventory value with units (mirrors frontend resourceMetricsUtils)."""
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not (num == num):  # NaN
        return "—"

    resolved_unit = (unit or infer_metric_metadata(fact_key, "Average")["unit"] or "").strip().lower()

    if resolved_unit == "percent":
        return f"{num:.1f}%"
    if resolved_unit == "usd":
        return f"${num:,.2f}"
    if resolved_unit == "gb":
        return f"{num:.2f} GB"
    if resolved_unit == "mb":
        return f"{num:,.2f} MB"
    if resolved_unit == "milliseconds":
        return f"{num:,.1f} ms"
    if resolved_unit == "seconds":
        return _format_seconds_display(num)
    if resolved_unit == "bytes":
        return _format_bytes_display(num)
    if resolved_unit == "bytes_per_sec":
        return _format_bytes_per_sec_display(num)
    if resolved_unit == "count":
        return f"{round(num):,}"

    key = (fact_key or "").lower()
    if key.endswith("_sec") or key.endswith("_lag_sec"):
        return _format_seconds_display(num)
    if key.endswith("_ms"):
        return f"{num:,.1f} ms"
    if key.endswith("_pct") or key.endswith("_percent") or key.endswith("_mem_pct") or "availability" in key:
        return f"{num:.1f}%"
    if "cpu" in key and "bytes" not in key:
        return f"{num:.1f}%"
    if (
        key.endswith("_bytes")
        or "_bytes_" in key
        or key.endswith("_bytes_in")
        or key.endswith("_bytes_out")
        or "bytes_dropped" in key
        or ("memory" in key and "pct" not in key)
    ):
        return _format_bytes_display(num)

    if num == int(num):
        return f"{int(num):,}"
    if abs(num) >= 1000:
        return f"{num:,.1f}"
    return f"{num:.2f}"


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

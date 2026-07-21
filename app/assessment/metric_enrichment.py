"""Derive assessment metric stats (baseline, trend, p95) from flat facts and time series."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from statistics import mean, stdev
from typing import Any

from app.assessment.spec import sanitize_metric_fact_key
from app.monitor_metrics import metric_timeseries_from_payload

log = logging.getLogger(__name__)

MIN_HISTORICAL_DAYS = 5
AUTO_BASELINE_DAYS = 7
DEFAULT_PERCENT_LIMIT = 100.0
STATIC_BASELINE_PCT = 50.0
ANOMALY_ZSCORE_THRESHOLD = 2.0
TREND_MIN_POINTS = 4


@dataclass(frozen=True)
class _MetricDef:
    nested_key: str
    rest_api_name: str
    fact_keys: tuple[str, ...]
    aggregation: str = "Average"
    unit: str | None = None


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _metric_defs(
    assessment: dict[str, Any] | None,
    canonical_type: str | None,
) -> list[_MetricDef]:
    defs: dict[str, _MetricDef] = {}

    if assessment:
        azure_metrics = assessment.get("azure_metrics") or {}
        for item in azure_metrics.get("metrics") or []:
            rest_name = str(item.get("metric_name") or "").strip()
            if not rest_name:
                continue
            nested = sanitize_metric_fact_key(rest_name)
            fact_keys: list[str] = []
            fact_key = str(item.get("fact_key") or "").strip()
            if fact_key:
                fact_keys.append(fact_key)
            fact_keys.append(nested)
            fact_keys.append(rest_name)
            defs[nested] = _MetricDef(
                nested_key=nested,
                rest_api_name=rest_name,
                fact_keys=tuple(dict.fromkeys(fact_keys)),
                aggregation=str(item.get("aggregation") or "Average"),
                unit=item.get("unit"),
            )

        for item in assessment.get("supportedMetricsFallback") or []:
            rest_name = str(item.get("restApiName") or item.get("displayName") or "").strip()
            if not rest_name:
                continue
            nested = sanitize_metric_fact_key(rest_name)
            if nested in defs:
                continue
            defs[nested] = _MetricDef(
                nested_key=nested,
                rest_api_name=rest_name,
                fact_keys=(nested, rest_name),
                aggregation=str(item.get("defaultAggregation") or "Average"),
            )

    if canonical_type:
        from app.resources.registry import profiles_for_canonical

        for profile in profiles_for_canonical(canonical_type):
            for metric_def in profile.metrics:
                nested = sanitize_metric_fact_key(metric_def.metric_name)
                fact_keys = [metric_def.fact_key, nested, metric_def.metric_name]
                existing = defs.get(nested)
                merged_keys = tuple(
                    dict.fromkeys([*(existing.fact_keys if existing else ()), *fact_keys])
                )
                defs[nested] = _MetricDef(
                    nested_key=nested,
                    rest_api_name=metric_def.metric_name,
                    fact_keys=merged_keys,
                    aggregation=metric_def.aggregation or "Average",
                    unit=metric_def.unit,
                )

    return list(defs.values())


def _lookup_scalar(flat_metrics: dict[str, Any], fact_keys: tuple[str, ...]) -> float | None:
    for key in fact_keys:
        val = _num(flat_metrics.get(key))
        if val is not None:
            return val
    return None


def _series_from_payload(
    metrics_payload: dict[str, Any] | None,
    monitor_raw: dict[str, Any] | None,
    metric_def: _MetricDef,
) -> list[float]:
    values: list[float] = []
    if metrics_payload:
        for row in metrics_payload.get("metrics") or metrics_payload.get("metrics_detail") or []:
            metric_name = str(row.get("metric_name") or "")
            if metric_name != metric_def.rest_api_name:
                continue
            for point in row.get("series_points") or []:
                val = _num(point.get("value"))
                if val is not None:
                    values.append(val)
            if not values:
                stats = row.get("stats") or {}
                for key in ("average", "maximum", "minimum"):
                    val = _num(stats.get(key))
                    if val is not None:
                        values.append(val)
            if values:
                return values

    payload = monitor_raw or (metrics_payload or {}).get("metrics_raw")
    if payload:
        points = metric_timeseries_from_payload(
            payload,
            metric_def.rest_api_name,
            aggregation=metric_def.aggregation,
            bucket="day",
        )
        values = [_num(p.get("value")) for p in points]
        return [v for v in values if v is not None]
    return []


def _trend_pct(series: list[float]) -> float | None:
    if len(series) < TREND_MIN_POINTS:
        return None
    midpoint = len(series) // 2
    prior = series[:midpoint]
    recent = series[midpoint:]
    if not prior or not recent:
        return None
    prior_avg = mean(prior)
    recent_avg = mean(recent)
    if prior_avg == 0:
        return None if recent_avg == 0 else 100.0
    return round(((recent_avg - prior_avg) / prior_avg) * 100.0, 2)


def _historical_baseline(series: list[float]) -> tuple[float | None, int]:
    if len(series) < MIN_HISTORICAL_DAYS:
        return None, len(series)
    window = series[: min(AUTO_BASELINE_DAYS, len(series))]
    nonzero = [v for v in window if v > 0]
    if len(nonzero) < MIN_HISTORICAL_DAYS:
        return None, len(series)
    return round(mean(window), 4), len(series)


def _is_percent_metric(metric_def: _MetricDef) -> bool:
    unit = (metric_def.unit or "").lower()
    name = metric_def.nested_key.lower()
    return (
        unit in {"percent", "percentage", "%"}
        or "percentage" in name
        or name.endswith("_pct")
        or "pct" in name
    )


def _metric_limit(
    metric_def: _MetricDef,
    thresholds: dict[str, float],
    metric_thresholds: dict[str, Any],
) -> float | None:
    for key in (metric_def.nested_key, metric_def.rest_api_name):
        block = metric_thresholds.get(key)
        if isinstance(block, dict):
            for field in ("limit_pct", "limit", "saturation_pct"):
                val = _num(block.get(field))
                if val is not None:
                    return val
        val = _num(block)
        if val is not None:
            return val

    if _is_percent_metric(metric_def):
        return DEFAULT_PERCENT_LIMIT

    nested = metric_def.nested_key
    if "memory" in nested and "pressure" not in nested:
        return _num(thresholds.get("memory_saturation_pct")) or DEFAULT_PERCENT_LIMIT
    if "cpu" in nested:
        return _num(thresholds.get("cpu_saturation_pct")) or DEFAULT_PERCENT_LIMIT
    return None


def _static_baseline(
    metric_def: _MetricDef,
    current: float | None,
    metric_thresholds: dict[str, Any],
) -> float | None:
    block = metric_thresholds.get(metric_def.nested_key) or metric_thresholds.get(metric_def.rest_api_name)
    if isinstance(block, dict):
        val = _num(block.get("static_baseline_pct") or block.get("static_baseline"))
        if val is not None:
            return val
    if current is not None:
        return current
    if _is_percent_metric(metric_def):
        return STATIC_BASELINE_PCT
    return None


def _anomaly_detected(series: list[float], baseline: float) -> bool:
    if len(series) < MIN_HISTORICAL_DAYS or baseline <= 0:
        return False
    recent = series[-min(7, len(series)) :]
    if len(recent) < 3:
        return False
    try:
        sigma = stdev(recent)
    except Exception:
        sigma = 0.0
    if sigma <= 0:
        return False
    latest = recent[-1]
    z = abs(latest - baseline) / sigma
    return z >= ANOMALY_ZSCORE_THRESHOLD


def _enrich_metric_node(
    metric_def: _MetricDef,
    flat_metrics: dict[str, Any],
    *,
    series: list[float],
    thresholds: dict[str, float],
    metric_thresholds: dict[str, Any],
) -> dict[str, Any]:
    current = _lookup_scalar(flat_metrics, metric_def.fact_keys)
    if current is None and series:
        current = round(mean(series), 4)

    node: dict[str, Any] = {}
    if current is not None:
        node["avg"] = current
        node["value"] = current

    if series:
        node["p95"] = round(_percentile(series, 95) or current or 0, 4) if series else None
        node["maximum"] = round(max(series), 4)
        node["minimum"] = round(min(series), 4)
        node["sampleCount"] = len(series)
        trend = _trend_pct(series)
        if trend is not None:
            node["trendPct"] = trend

    hist_baseline, hist_days = _historical_baseline(series)
    limit = _metric_limit(metric_def, thresholds, metric_thresholds)
    p95_val = _num(node.get("p95")) or current

    if hist_baseline is not None:
        node["baselineAvailable"] = True
        node["baselineSource"] = "historical"
        node["baselineValue"] = hist_baseline
        node["baselineDays"] = hist_days
        if _anomaly_detected(series, hist_baseline):
            node["anomalyDetected"] = True
    else:
        static_baseline = _static_baseline(metric_def, current, metric_thresholds)
        if static_baseline is not None:
            node["baselineAvailable"] = True
            node["baselineSource"] = "static_threshold"
            node["baselineValue"] = static_baseline
            log.info(
                "metric_baseline.static_fallback metric=%s baseline=%s samples=%s",
                metric_def.nested_key,
                static_baseline,
                len(series),
            )
        else:
            node["baselineAvailable"] = False
            node["baselineSource"] = "insufficient"
            log.info(
                "metric_baseline.unavailable metric=%s samples=%s",
                metric_def.nested_key,
                len(series),
            )

    if p95_val is not None and limit and limit > 0:
        node["p95LimitPct"] = round((p95_val / limit) * 100.0, 2)

    return node


def enrich_assessment_metric_stats(
    metrics: dict[str, Any] | None,
    *,
    flat_metrics: dict[str, Any] | None = None,
    assessment: dict[str, Any] | None = None,
    canonical_type: str | None = None,
    metrics_payload: dict[str, Any] | None = None,
    monitor_raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach nested per-metric stats expected by assessment JSON rules."""
    out: dict[str, Any] = dict(metrics or {})
    source = dict(flat_metrics or metrics or {})
    defs = _metric_defs(assessment, canonical_type)
    if not defs:
        return out

    from app.assessment.config_resolver import load_optimization_thresholds, load_resource_config

    thresholds = load_optimization_thresholds(canonical_type or "")
    config = load_resource_config(canonical_type or "") if canonical_type else {}
    metric_thresholds = dict(config.get("metric_thresholds") or {})

    for metric_def in defs:
        series = _series_from_payload(metrics_payload, monitor_raw, metric_def)
        node = _enrich_metric_node(
            metric_def,
            source,
            series=series,
            thresholds=thresholds,
            metric_thresholds=metric_thresholds,
        )
        if not node:
            continue
        existing = out.get(metric_def.nested_key)
        if isinstance(existing, dict):
            merged = dict(existing)
            merged.update(node)
            out[metric_def.nested_key] = merged
        else:
            if existing is not None and "value" not in node:
                node.setdefault("value", existing)
            out[metric_def.nested_key] = node

    return out

"""Slim API payloads for the resource insight drawer (Azure-style layout)."""

from __future__ import annotations

from typing import Any

# Fact keys retained for disk usage tiles when metric rows are sparse.
_DISK_FACT_KEYS = frozenset({
    "disk_read_bps",
    "disk_write_bps",
    "disk_read_iops",
    "disk_write_iops",
    "disk_queue_depth",
    "disk_iops_utilization_pct",
    "disk_throughput_utilization_pct",
    "disk_used_pct",
    "disk_used_gb",
})

# Utilization scalars used by overview/trends when metric rows are sparse.
_UTILIZATION_FACT_KEYS = frozenset({
    "avg_cpu_pct",
    "avg_memory_pct",
    "avg_mem_pct",
    "memory_usage_pct",
    "cluster_cpu_pct",
    "cluster_mem_pct",
    "normalized_ru_pct",
    "storage_pct",
    "used_capacity_bytes",
    "disk_iops_utilization_pct",
    "disk_throughput_utilization_pct",
    "peak_disk_iops_utilization_pct",
})

_METRIC_ROW_KEEP = frozenset({
    "fact_key",
    "label",
    "unit",
    "value",
    "stats",
    "primary_stat",
    "trigger",
    "status",
    "metric_name",
    "aggregation",
    "series_points",
})


def _slim_metric_row(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        return {}
    return {k: row[k] for k in _METRIC_ROW_KEEP if k in row and row[k] is not None}


def _merge_series_points_from_detail(
    metrics: list[dict[str, Any]],
    metrics_detail: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Backfill series_points on unified metric rows from metrics_detail when missing."""
    detail_by_key = {
        str(row.get("fact_key") or "").lower(): row
        for row in (metrics_detail or [])
        if row.get("fact_key") and row.get("series_points")
    }
    if not detail_by_key:
        return metrics

    merged: list[dict[str, Any]] = []
    for row in metrics:
        fact_key = str(row.get("fact_key") or "").lower()
        if fact_key and not row.get("series_points"):
            detail_row = detail_by_key.get(fact_key)
            if detail_row:
                merged.append({**row, "series_points": detail_row["series_points"]})
                continue
        merged.append(row)
    return merged


def _slim_instance_row(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        return {}
    slim = {
        k: row[k]
        for k in ("instance_id", "name", "resource_id", "source", "pool_name")
        if k in row
    }
    if row.get("id"):
        slim["id"] = row["id"]
    metrics = row.get("metrics") or row.get("metrics_detail") or []
    if metrics:
        slim["metrics"] = [_slim_metric_row(m) for m in metrics]
    for key in ("cpu_pct", "mem_pct", "power_state"):
        if row.get(key) is not None:
            slim[key] = row[key]
    return slim


def _slim_pool_instance_row(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        return {}
    return {
        k: row[k]
        for k in ("id", "name", "instance_id", "power_state", "cpu_pct", "mem_pct", "source")
        if k in row and row[k] is not None
    }


def _slim_pool_metrics(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    slim_rows: list[dict[str, Any]] = []
    for row in rows or []:
        if not row:
            continue
        slim = {
            k: row[k]
            for k in (
                "name",
                "cpu_pct",
                "mem_pct",
                "source",
                "nodes_with_metrics",
                "vmss_id",
                "vmss_instance_count",
            )
            if k in row and row[k] is not None
        }
        instances = row.get("vmss_instances")
        if instances:
            slim["vmss_instances"] = [_slim_pool_instance_row(inst) for inst in instances]
        slim_rows.append(slim)
    return slim_rows


def slim_metrics_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Drop heavy Monitor/debug fields; keep drawer Metrics + cost signals."""
    from app.cost_signals_filters import filter_metrics_payload_for_cost_signals

    if not payload:
        return {}

    out: dict[str, Any] = {
        k: payload[k]
        for k in (
            "ok",
            "error",
            "resource_id",
            "canonical_type",
            "display_name",
            "timespan",
            "data_quality",
            "unavailable_reason",
            "doc_ref",
            "doc_url",
        )
        if k in payload
    }

    metrics_detail = payload.get("metrics_detail") or []
    out["metrics"] = _merge_series_points_from_detail(
        [_slim_metric_row(r) for r in (payload.get("metrics") or [])],
        metrics_detail,
    )
    out["derived"] = [_slim_metric_row(r) for r in (payload.get("derived") or [])]
    out["instances"] = [_slim_instance_row(r) for r in (payload.get("instances") or [])]
    out["inventory_properties"] = payload.get("inventory_properties") or []

    mapping = payload.get("cost_driver_mapping") or {}
    out["cost_driver_mapping"] = {
        "cost_drivers": mapping.get("cost_drivers") or [],
    }

    facts = payload.get("facts") or {}
    if isinstance(facts, dict):
        metric_fact_keys = {
            str(row.get("fact_key") or "")
            for row in (payload.get("metrics") or []) + (payload.get("derived") or [])
            if row.get("fact_key")
        }
        slim_facts = {
            k: v
            for k, v in facts.items()
            if v is not None
            and (
                k in _DISK_FACT_KEYS
                or k in _UTILIZATION_FACT_KEYS
                or k in metric_fact_keys
            )
        }
        if slim_facts:
            out["facts"] = slim_facts

    pool_metrics = payload.get("pool_metrics") or []
    if pool_metrics:
        out["pool_metrics"] = _slim_pool_metrics(pool_metrics)

    # Fallback for legacy disk tile builder when unified rows are empty.
    if not out["metrics"] and not out["derived"]:
        detail = payload.get("metrics_detail") or []
        if detail:
            out["metrics_detail"] = [_slim_metric_row(r) for r in detail]

    return filter_metrics_payload_for_cost_signals(out)


def slim_scorecard(scorecard: dict[str, Any] | None) -> dict[str, Any] | None:
    if not scorecard:
        return None
    return {
        k: scorecard[k]
        for k in (
            "overall_recommendation_score",
            "recommendation_tier",
            "primary_action",
            "cost_savings_monthly",
            "dimensions",
        )
        if k in scorecard
    }


def slim_dependencies(dependencies: dict[str, Any] | None) -> dict[str, Any] | None:
    if not dependencies:
        return None
    return {
        k: dependencies[k]
        for k in ("direct_outbound", "direct_inbound", "transitive_dependent_count")
        if dependencies.get(k) is not None
    }


def slim_trends(trends: dict[str, Any] | None) -> dict[str, Any] | None:
    if not trends:
        return None
    slim = {
        k: trends[k]
        for k in (
            "cpu_trend",
            "memory_trend",
            "cost_vs_prev_month_pct",
            "cost_trajectory",
            "utilization_volatility",
        )
        if trends.get(k) is not None
    }
    return slim or None


def slim_analysis_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Insights tab: workload/cost signals only — no tier scorecard."""
    if not payload:
        return {}
    return {
        "insights": payload.get("insights"),
        "trends": slim_trends(payload.get("trends")),
        "dependencies": slim_dependencies(payload.get("dependencies")),
    }

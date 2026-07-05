"""Metrics catalog — single source for profile metadata, display, and API shaping."""

from __future__ import annotations

from typing import Any

from app.azure_monitor_aggregations import azure_metrics_doc_url
from app.optimization_metrics import METRIC_DEFS
from app.resources.registry import (
    RESOURCE_MONITOR_PROFILES,
    get_monitor_profile,
    profiles_for_canonical,
    usage_metrics_for_canonical,
)
from app.resources.types import ResourceMonitorProfile, UtilizationMetric


def _metric_def_status(fact_key: str, value: Any) -> str | None:
    defn = METRIC_DEFS.get(fact_key) or {}
    status_fn = defn.get("status_fn")
    if callable(status_fn):
        return status_fn(value)
    return None


def catalog_entry_from_metric(
    metric: UtilizationMetric,
    *,
    profile: ResourceMonitorProfile | None = None,
) -> dict[str, Any]:
    defn = METRIC_DEFS.get(metric.fact_key) or {}
    label = defn.get("label") or metric.description
    return {
        "metric_name": metric.metric_name,
        "fact_key": metric.fact_key,
        "label": label,
        "description": metric.description,
        "aggregation": metric.aggregation,
        "timespan": metric.timespan,
        "rules": list(metric.rules),
        "unit": metric.unit,
        "primary_stat": metric.primary_stat,
        "display_stats": list(metric.display_stats),
        "supported_aggregations": list(metric.supported_aggregations),
        "impact": metric.impact,
        "canonical_type": profile.canonical_type if profile else None,
        "monitor_arm_type": profile.monitor_arm_type if profile else None,
    }


def metrics_catalog_for_canonical_type(canonical_type: str) -> list[dict[str, Any]]:
    """All monitor + extra usage metrics for a canonical resource type."""
    ctype = (canonical_type or "").strip().lower()
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for profile in profiles_for_canonical(ctype):
        for metric in profile.metrics:
            if metric.fact_key in seen:
                continue
            seen.add(metric.fact_key)
            entries.append(catalog_entry_from_metric(metric, profile=profile))
    for extra in usage_metrics_for_canonical(ctype):
        if extra.source != "azure_monitor" and extra.fact_key not in seen:
            seen.add(extra.fact_key)
            entries.append({
                "metric_name": extra.metric_name,
                "fact_key": extra.fact_key,
                "label": extra.description,
                "description": extra.description,
                "aggregation": extra.aggregation,
                "timespan": extra.timespan,
                "rules": list(extra.rules),
                "unit": "usd" if extra.fact_key in {"monthly_cost_usd", "mtd_cost"} else "number",
                "primary_stat": "total",
                "display_stats": ["total"],
                "impact": "cost",
                "source": extra.source,
                "canonical_type": ctype,
            })
    return entries


def metrics_catalog_for_resource(resource_id: str, canonical_type: str | None = None) -> list[dict[str, Any]]:
    profile = get_monitor_profile(resource_id, canonical_type)
    if profile:
        return [catalog_entry_from_metric(m, profile=profile) for m in profile.metrics]
    if canonical_type:
        return metrics_catalog_for_canonical_type(canonical_type)
    return []


def build_unified_metric_row(
    detail_row: dict[str, Any],
    metric_def: UtilizationMetric | None,
    facts: dict[str, Any],
) -> dict[str, Any]:
    """Merge metrics_detail row with catalog metadata and status."""
    fact_key = detail_row.get("fact_key") or ""
    stats = detail_row.get("stats") or {}
    primary = (metric_def.primary_stat if metric_def else None) or detail_row.get("primary_aggregation", "Average")
    primary_key = str(primary).lower()
    value = stats.get(primary_key)
    if value is None:
        value = stats.get("average")
    row = {
        "fact_key": fact_key,
        "metric_name": detail_row.get("metric_name"),
        "label": (metric_def.description if metric_def else None) or detail_row.get("label") or fact_key,
        "unit": metric_def.unit if metric_def else "",
        "primary_stat": primary_key,
        "display_stats": list(metric_def.display_stats) if metric_def else list(stats.keys()),
        "impact": metric_def.impact if metric_def else "both",
        "rules": list(metric_def.rules) if metric_def else [],
        "stats": stats,
        "value": value,
        "status": _metric_def_status(fact_key, value if value is not None else facts.get(fact_key)),
    }
    defn = METRIC_DEFS.get(fact_key) or {}
    if defn.get("label"):
        row["label"] = defn["label"]
    return row


def build_derived_metric_rows(
    facts: dict[str, Any],
    *,
    canonical_type: str,
) -> list[dict[str, Any]]:
    """Computed metrics not directly from a single Monitor series."""
    derived: list[dict[str, Any]] = []
    ctype = (canonical_type or "").lower()

    if ctype in {"compute/vm", "compute/vmss"} and facts.get("avg_memory_pct") is not None:
        derived.append({
            "fact_key": "avg_memory_pct",
            "label": "Average memory utilization",
            "value": facts["avg_memory_pct"],
            "unit": "percent",
            "source": "computed_from_available_memory_and_sku",
            "impact": "both",
            "status": _metric_def_status("avg_memory_pct", facts["avg_memory_pct"]),
        })
    if ctype == "storage/account" and facts.get("storage_pct") is not None:
        derived.append({
            "fact_key": "storage_pct",
            "label": "Storage utilization",
            "value": facts["storage_pct"],
            "unit": "percent",
            "source": "computed_from_used_and_capacity",
            "impact": "both",
            "status": _metric_def_status("storage_pct", facts["storage_pct"]),
        })
    if ctype == "compute/disk" and facts.get("disk_iops_utilization_pct") is not None:
        derived.append({
            "fact_key": "disk_iops_utilization_pct",
            "label": "Disk IOPS utilization",
            "value": facts["disk_iops_utilization_pct"],
            "unit": "percent",
            "source": "computed_from_observed_and_provisioned_iops",
            "impact": "both",
            "status": _metric_def_status("disk_iops_utilization_pct", facts["disk_iops_utilization_pct"]),
        })
    return derived


def sql_server_metrics_unavailable(resource_id: str) -> dict[str, Any] | None:
    """Return unavailable payload when ARM ID is SQL server (metrics apply to databases)."""
    rid = (resource_id or "").lower()
    if "/microsoft.sql/servers/" in rid and "/databases/" not in rid:
        return {
            "ok": False,
            "data_quality": "unavailable",
            "unavailable_reason": (
                "Azure Monitor metrics apply to individual SQL databases, not the server resource. "
                "Open a database under this server to view CPU and storage utilization."
            ),
            "hint": "database/sql",
        }
    return None


def cost_export_metrics_for_resource(
    db,
    resource_id: str,
    canonical_type: str,
) -> dict[str, Any] | None:
    """Build cost-export proxy metrics when Monitor profile is empty."""
    from app.cost_db import resource_cost_map_from_db
    from app.cost_utils import monthly_cost_amounts_from_entry, resolve_cost_map_entry
    from app.focus_mapping import normalize_arm_id

    rid = normalize_arm_id(resource_id)
    if not rid:
        return None
    parts = rid.split("/")
    if "subscriptions" not in parts:
        return None
    sub_idx = parts.index("subscriptions")
    if sub_idx + 1 >= len(parts):
        return None
    sub = parts[sub_idx + 1].lower()
    cost_map = resource_cost_map_from_db(db, sub)
    detail = resolve_cost_map_entry(cost_map, rid)
    if detail is None:
        return None
    billing, usd, currency = monthly_cost_amounts_from_entry(detail)
    amount = billing if billing > 0 else usd
    if amount <= 0:
        return None
    unit = "usd" if usd > 0 and billing <= 0 else currency.lower() if currency else "usd"
    return {
        "metrics": [{
            "fact_key": "monthly_cost_usd",
            "label": "Month-to-date cost",
            "value": round(amount, 2),
            "unit": unit,
            "primary_stat": "total",
            "display_stats": ["total"],
            "impact": "cost",
            "rules": [],
            "stats": {"total": round(amount, 2)},
            "status": None,
        }],
        "derived": [],
        "data_quality": "cost_export_only",
        "unavailable_reason": None,
    }


def list_full_catalog() -> list[dict[str, Any]]:
    """All monitor profiles with enriched metric metadata."""
    out: list[dict[str, Any]] = []
    for profile in sorted(RESOURCE_MONITOR_PROFILES.values(), key=lambda p: p.canonical_type):
        out.append({
            "monitor_arm_type": profile.monitor_arm_type,
            "canonical_type": profile.canonical_type,
            "display_name": profile.display_name,
            "doc_ref": profile.doc_ref,
            "doc_url": azure_metrics_doc_url(profile.doc_ref) if profile.doc_ref else None,
            "metric_count": len(profile.metrics),
            "metrics": [catalog_entry_from_metric(m, profile=profile) for m in profile.metrics],
            "extra_metrics": metrics_catalog_for_canonical_type(profile.canonical_type),
        })
    return out

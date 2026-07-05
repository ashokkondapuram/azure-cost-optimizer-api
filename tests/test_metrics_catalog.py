"""Tests for metrics catalog and profile metadata."""
from __future__ import annotations

from app.metrics_catalog import (
    catalog_entry_from_metric,
    metrics_catalog_for_canonical_type,
    sql_server_metrics_unavailable,
)
from app.resources.registry import RESOURCE_MONITOR_PROFILES, list_monitor_profiles
from app.resources.types import utilization_metric


def test_all_monitor_profiles_have_metric_metadata():
    assert len(RESOURCE_MONITOR_PROFILES) >= 28
    for profile in RESOURCE_MONITOR_PROFILES.values():
        for metric in profile.metrics:
            assert metric.unit, f"{profile.canonical_type}/{metric.fact_key} missing unit"
            assert metric.primary_stat, f"{profile.canonical_type}/{metric.fact_key} missing primary_stat"
            assert metric.display_stats, f"{profile.canonical_type}/{metric.fact_key} missing display_stats"
            assert metric.supported_aggregations, f"{profile.canonical_type}/{metric.fact_key} missing supported_aggregations"
            assert metric.impact in {"cost", "performance", "both"}, metric.impact
            for stat in metric.display_stats:
                assert stat in {"average", "minimum", "maximum", "total", "count"}, stat


def test_catalog_entry_includes_display_fields():
    metric = utilization_metric(
        "Percentage CPU",
        "avg_cpu_pct",
        "Average CPU utilization",
        aggregation="Average",
        rules=("VM_IDLE",),
    )
    entry = catalog_entry_from_metric(metric)
    assert entry["unit"] == "percent"
    assert entry["impact"] == "both"
    assert "average" in entry["display_stats"]


def test_metrics_catalog_for_vm_type():
    entries = metrics_catalog_for_canonical_type("compute/vm")
    fact_keys = {e["fact_key"] for e in entries}
    assert "avg_cpu_pct" in fact_keys
    assert "avg_available_memory_bytes" in fact_keys


def test_list_monitor_profiles_includes_unit_and_impact():
    profiles = list_monitor_profiles()
    vm = next(p for p in profiles if p["canonical_type"] == "compute/vm")
    assert vm["metrics"][0]["unit"] == "percent"


def test_sql_server_metrics_unavailable_message():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Sql/servers/myserver"
    payload = sql_server_metrics_unavailable(rid)
    assert payload is not None
    assert payload["data_quality"] == "unavailable"
    assert "database" in payload["unavailable_reason"].lower()

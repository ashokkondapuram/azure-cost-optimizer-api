"""Tests for Azure-doc metric aggregation catalog."""

from __future__ import annotations

from app.azure_monitor_aggregations import (
    METRIC_SUPPORTED_AGGREGATIONS,
    display_stats_from_azure_aggregations,
    lookup_supported_aggregations,
)
from app.resources.registry import RESOURCE_MONITOR_PROFILES


def test_catalog_covers_all_profile_metrics():
    missing = []
    for profile in RESOURCE_MONITOR_PROFILES.values():
        for metric in profile.metrics:
            supported = lookup_supported_aggregations(profile.monitor_arm_type, metric.metric_name)
            if supported is None:
                missing.append((profile.monitor_arm_type, metric.metric_name))
    assert not missing, f"Missing Azure doc aggregations for: {missing[:5]}"


def test_vm_cpu_average_only():
    supported = lookup_supported_aggregations("microsoft.compute/virtualmachines", "Percentage CPU")
    assert supported == ("Average",)
    stats = display_stats_from_azure_aggregations(supported, primary_aggregation="Average")
    assert stats == ("average",)


def test_sql_cpu_supports_min_max_avg():
    supported = lookup_supported_aggregations("microsoft.sql/servers/databases", "cpu_percent")
    assert supported == ("Average", "Maximum", "Minimum")
    stats = display_stats_from_azure_aggregations(supported, primary_aggregation="Average")
    assert stats == ("average", "maximum", "minimum")


def test_storage_transactions_total_only():
    supported = lookup_supported_aggregations("microsoft.storage/storageaccounts", "Transactions")
    assert supported == ("Total",)
    stats = display_stats_from_azure_aggregations(supported, primary_aggregation="Total")
    assert stats == ("total",)


def test_enriched_profiles_match_catalog():
    for profile in RESOURCE_MONITOR_PROFILES.values():
        for metric in profile.metrics:
            key = (profile.monitor_arm_type, metric.metric_name)
            if key in METRIC_SUPPORTED_AGGREGATIONS:
                assert metric.supported_aggregations == METRIC_SUPPORTED_AGGREGATIONS[key]


def test_azure_metrics_doc_url():
    from app.azure_monitor_aggregations import azure_metrics_doc_url

    url = azure_metrics_doc_url("microsoft-compute-virtualmachines-metrics")
    assert url == (
        "https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics/"
        "microsoft-compute-virtualmachines-metrics"
    )
    assert azure_metrics_doc_url("microsoft-compute-virtualmachines") == url
    assert azure_metrics_doc_url("") is None

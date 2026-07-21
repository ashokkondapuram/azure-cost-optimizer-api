"""Regression tests for metric unit inference across all monitor profiles."""

from __future__ import annotations

import pytest

from app.resources.registry import RESOURCE_MONITOR_PROFILES
from app.resources.types import infer_metric_metadata, utilization_metric

# fact_key -> expected unit (covers misleading names and prior bugs)
EXPECTED_UNITS = {
    "cpu_time_sec": "seconds",
    "avg_cpu_pct": "percent",
    "cpu_pct": "percent",
    "cluster_cpu_pct": "percent",
    "avg_memory_bytes": "bytes",
    "avg_available_memory_bytes": "bytes",
    "used_capacity_bytes": "bytes",
    "egress_bytes": "bytes",
    "network_out_bytes": "bytes",
    "pe_bytes_in": "bytes",
    "pe_bytes_out": "bytes",
    "ddos_bytes_dropped": "bytes",
    "byte_count": "bytes",
    "byte_count_peak": "bytes",
    "throughput_bytes": "bytes_per_sec",
    "disk_read_bps": "bytes_per_sec",
    "bytes_received_rate": "bytes_per_sec",
    "bytes_sent_rate": "bytes_per_sec",
    "request_count": "count",
    "transaction_count": "count",
    "packet_count": "count",
    "total_ru": "count",
    "query_duration_ms": "milliseconds",
    "replication_latency_ms": "milliseconds",
    "server_latency_ms": "milliseconds",
    "replication_lag_sec": "seconds",
    "ingestion_bytes": "mb",
    "ingestion_gb": "gb",
    "provisioned_throughput": "number",
    "pod_count": "count",
    "vip_availability_pct": "percent",
    "memory_pct": "percent",
    "ops_per_sec": "count",
    "search_qps": "count",
}


@pytest.mark.parametrize("fact_key,expected_unit", list(EXPECTED_UNITS.items()))
def test_infer_metric_metadata_known_fact_keys(fact_key: str, expected_unit: str):
    assert infer_metric_metadata(fact_key, "Average")["unit"] == expected_unit


def test_format_fact_display_value_available_memory_bytes():
    from app.resources.types import format_fact_display_value

    assert format_fact_display_value("avg_available_memory_bytes", 62_262_717_653.0656) == "57.99 GB"
    assert format_fact_display_value("avg_cpu_pct", 12.345) == "12.3%"
    assert format_fact_display_value("query_duration_ms", 125.4) == "125.4 ms"
    assert format_fact_display_value("pod_count", 3220.23) == "3,220"


def test_aks_pod_count_uses_maximum_aggregation():
    profile = next(
        p for p in RESOURCE_MONITOR_PROFILES.values()
        if p.canonical_type == "containers/aks"
    )
    pod = next(m for m in profile.metrics if m.fact_key == "pod_count")
    assert pod.aggregation == "Maximum"
    assert pod.primary_stat == "maximum"


def test_all_monitor_profile_metrics_have_valid_units():
    allowed = {
        "percent", "bytes", "bytes_per_sec", "count", "seconds", "milliseconds",
        "gb", "mb", "number", "usd",
    }
    for profile in RESOURCE_MONITOR_PROFILES.values():
        for metric in profile.metrics:
            assert metric.unit in allowed, (
                f"{profile.canonical_type}/{metric.fact_key} has unit {metric.unit!r}"
            )


def test_webapp_profile_cpu_time_is_seconds():
    profile = next(
        p for p in RESOURCE_MONITOR_PROFILES.values()
        if p.canonical_type == "appservice/webapp"
    )
    cpu = next(m for m in profile.metrics if m.fact_key == "cpu_time_sec")
    assert cpu.unit == "seconds"


def test_utilization_metric_matches_infer():
    metric = utilization_metric(
        "QueryDuration",
        "query_duration_ms",
        "Query duration",
        aggregation="Maximum",
    )
    assert metric.unit == "milliseconds"

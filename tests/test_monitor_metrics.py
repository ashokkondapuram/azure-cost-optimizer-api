"""Tests for spec-driven Azure Monitor metrics loading."""

from app.monitor_metrics import (
    average_from_monitor_payload,
    extract_monitor_facts,
    metric_value_from_monitor_payload,
    monitor_fetch_plan,
)
from app.resources import get_technical_fetch_spec


def _payload(cpu: float, memory_bytes: float) -> dict:
    return {
        "value": [
            {
                "name": {"value": "Percentage CPU"},
                "timeseries": [{"data": [{"average": cpu}]}],
            },
            {
                "name": {"value": "Available Memory Bytes"},
                "timeseries": [{"data": [{"average": memory_bytes}]}],
            },
        ]
    }


def test_average_from_monitor_payload():
    assert average_from_monitor_payload(_payload(42.5, 0), "Percentage CPU") == 42.5


def test_extract_monitor_facts_for_vm():
    spec = get_technical_fetch_spec("compute/vm")
    facts = extract_monitor_facts(_payload(15.0, 8 * 1024**3), spec)
    assert facts["avg_cpu_pct"] == 15.0


def test_monitor_fetch_plan_covers_major_types():
    plan = monitor_fetch_plan()
    assert "compute/vm" in plan
    assert "appservice/webapp" in plan
    assert "database/redis" in plan
    assert "storage/account" in plan
    webapp_metrics = {m["name"] for m in plan["appservice/webapp"]["metrics"]}
    assert "CpuTime" in webapp_metrics
    assert "Requests" in webapp_metrics
    assert "AverageMemoryWorkingSet" in webapp_metrics
    assert "CpuPercentage" not in webapp_metrics
    assert any(m["name"] == "CpuPercentage" for m in plan["appservice/plan"]["metrics"])
    disk_metrics = {m["name"] for m in plan["compute/disk"]["metrics"]}
    assert "Composite Disk Read Bytes/sec" in disk_metrics
    assert "Composite Disk Write Bytes/sec" in disk_metrics
    assert "Composite Disk Read Operations/sec" in disk_metrics
    assert "Composite Disk Write Operations/sec" in disk_metrics
    agw_plan = plan["network/appgateway"]
    agw_names = {m["name"] for m in agw_plan["metrics"]}
    assert "TotalRequests" in agw_names
    assert "Throughput" in agw_names
    assert "Total" in agw_plan["aggregations"]


def test_metric_value_from_monitor_payload_prefers_total():
    payload = {
        "value": [
            {
                "name": {"value": "TotalRequests"},
                "timeseries": [{"data": [{"total": 42}, {"total": 58}]}],
            },
        ],
    }
    assert metric_value_from_monitor_payload(payload, "TotalRequests", aggregation="Total") == 100


def test_metric_value_from_monitor_payload_uses_maximum():
    payload = {
        "value": [
            {
                "name": {"value": "Percentage CPU"},
                "timeseries": [{"data": [{"maximum": 12.0}, {"maximum": 48.5}, {"maximum": 31.0}]}],
            },
        ],
    }
    assert metric_value_from_monitor_payload(payload, "Percentage CPU", aggregation="Maximum") == 48.5


def test_monitor_fetch_plan_includes_maximum_aggregation():
    plan = monitor_fetch_plan()
    assert "Maximum" in plan["compute/vm"]["aggregations"]


def test_extract_monitor_facts_skips_memory_bytes_as_pct():
    spec = get_technical_fetch_spec("compute/vm")
    facts = extract_monitor_facts(_payload(15.0, 8 * 1024**3), spec)
    assert facts.get("avg_cpu_pct") == 15.0
    assert "avg_mem_pct" not in facts


def test_extract_monitor_facts_for_webapp():
    spec = get_technical_fetch_spec("appservice/webapp")
    payload = {
        "value": [
            {
                "name": {"value": "CpuTime"},
                "timeseries": [{"data": [{"total": 900.0}]}],
            },
            {
                "name": {"value": "AverageMemoryWorkingSet"},
                "timeseries": [{"data": [{"average": 128 * 1024**2}]}],
            },
            {
                "name": {"value": "Requests"},
                "timeseries": [{"data": [{"total": 250.0}]}],
            },
        ],
    }
    facts = extract_monitor_facts(payload, spec)
    assert facts["cpu_time_sec"] == 900.0
    assert facts["avg_memory_bytes"] == 128 * 1024**2
    assert facts["request_count"] == 250.0


def test_group_resources_by_canonical_type():
    from app.metrics_loader import group_resources_by_canonical_type

    grouped = group_resources_by_canonical_type({
        "vms": [{"id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"}],
        "redis_caches": [{"id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Cache/redis/cache1"}],
    })
    assert "compute/vm" in grouped
    assert "database/redis" in grouped

"""Tests for strict utilization gates and false-positive prevention."""
from __future__ import annotations

from app.resource_utilization import (
    PARTIAL_MONITOR_CONFIDENCE_CAP,
    confidence_with_monitor,
    data_quality,
    has_rightsizing_monitor_data,
    monitor_facts_status,
    utilization_gate,
    vm_sizing_metrics_ok,
)
from app.vm_sizing import extract_vm_utilization


def test_confidence_capped_on_partial_monitor():
    partial = {"_technical_facts": {"data_source": "azure_monitor", "avg_cpu_pct": 12.0}}
    assert monitor_facts_status(partial, "avg_cpu_pct", "avg_memory_pct") == "partial"
    assert confidence_with_monitor(80, partial, required_keys=("avg_cpu_pct", "avg_memory_pct")) == PARTIAL_MONITOR_CONFIDENCE_CAP


def test_rightsizing_requires_both_cpu_and_memory():
    complete = {"_technical_facts": {"data_source": "azure_monitor", "avg_cpu_pct": 8.0, "avg_memory_pct": 10.0}}
    partial = {"_technical_facts": {"data_source": "azure_monitor", "avg_cpu_pct": 8.0}}
    assert has_rightsizing_monitor_data(complete) is True
    assert has_rightsizing_monitor_data(partial) is False
    assert utilization_gate(partial, "avg_cpu_pct", "avg_memory_pct", allow_inventory_only=False) is False


def test_data_quality_labels():
    full = {"_technical_facts": {"avg_cpu_pct": 1.0, "avg_memory_pct": 2.0, "data_source": "azure_monitor"}}
    inv = {"_technical_facts": {"vm_size": "Standard_D2s_v3"}}
    assert data_quality(full, "avg_cpu_pct", "avg_memory_pct") == "full_monitor"
    assert data_quality(inv) == "inventory_only"


def test_vm_sizing_metrics_ok_with_live_metrics_only():
    vm = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        "_technical_facts": {"avg_cpu_pct": 8.0},
    }
    metrics = {
        vm["id"].lower(): {
            "value": [
                {"name": {"value": "Percentage CPU"}, "timeseries": [{"data": [{"average": 8.0}]}]},
                {"name": {"value": "Available Memory Bytes"}, "timeseries": [{"data": [{"average": 14 * 1024 ** 3}]}]},
            ],
        },
    }
    util = extract_vm_utilization(metrics[vm["id"].lower()], sku="Standard_D4s_v3")
    assert vm_sizing_metrics_ok(vm, util, metrics) is True
    assert utilization_gate(vm, "avg_cpu_pct", "avg_memory_pct", allow_inventory_only=False) is False

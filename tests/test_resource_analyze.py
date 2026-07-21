"""Tests for single-resource scoped analysis."""
from __future__ import annotations

from app.analysis.orchestrator import filter_buckets_by_resource_ids, empty_buckets


def test_filter_buckets_by_resource_ids_keeps_matching_rows():
    buckets = empty_buckets()
    buckets["vms"] = [
        {"id": "/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a"},
        {"id": "/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Compute/virtualMachines/vm-b"},
    ]
    filtered = filter_buckets_by_resource_ids(
        buckets,
        ["/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Compute/virtualMachines/vm-b"],
    )
    assert len(filtered["vms"]) == 1
    assert filtered["vms"][0]["id"].endswith("/vm-b")

"""Tests for engine runtime filters and post-analysis rules."""

from app.optimizer.engine import OptimizationEngine
from app.optimizer.engine_filters import should_skip_resource
from app.optimizer.engine_runtime import filter_bucket_dict, filter_resources, split_rule_overrides
from app.metrics_loader import resolve_analysis_timespan
from app.optimizer.network_advanced_rules import analyze_network_advanced
from app.optimizer.rules import DEFAULT_RULES


def test_should_skip_resource_on_do_not_optimize_tag():
    resource = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        "name": "vm1",
        "tags": {"doNotOptimize": "true"},
    }
    assert should_skip_resource(resource) is True


def test_split_rule_overrides_extracts_global():
    merged, global_cfg = split_rule_overrides({
        "__global__": {"nonprod_severity_cap": "LOW"},
        "VM_IDLE": {"cpu_idle_pct": 2},
    })
    assert "VM_IDLE" in merged
    assert "__global__" not in merged
    assert global_cfg["nonprod_severity_cap"] == "LOW"


def test_expressroute_rule_emits_finding():
    engine = OptimizationEngine()
    circuit = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/expressRouteCircuits/er1",
        "name": "er1",
        "properties": {"provisioningState": "Succeeded", "peerings": [{"name": "p1"}]},
    }
    costs = {circuit["id"].lower(): 200.0}
    findings = analyze_network_advanced(
        engine,
        "sub",
        {"network/expressroute": [circuit]},
        costs,
    )
    assert any(f.rule_id == "NETWORK_EXPRESSROUTE_REVIEW" for f in findings)


def test_filter_resources_removes_tagged():
    items = [
        {"id": "a", "tags": {"doNotOptimize": "yes"}},
        {"id": "b", "tags": {}},
    ]
    kept = filter_resources(items, None)
    assert len(kept) == 1
    assert kept[0]["id"] == "b"


def test_filter_bucket_dict_applies_per_bucket():
    buckets = {
        "vms": [
            {"id": "skip", "tags": {"doNotOptimize": "true"}},
            {"id": "keep", "tags": {}},
        ],
        "disks": [{"id": "disk1", "tags": {}}],
    }
    filtered = filter_bucket_dict(buckets, None)
    assert len(filtered["vms"]) == 1
    assert filtered["vms"][0]["id"] == "keep"
    assert len(filtered["disks"]) == 1


def test_resolve_analysis_timespan_uses_max_rule_window():
    assert resolve_analysis_timespan() == "P7D"
    assert resolve_analysis_timespan({"VM_IDLE": {"evaluation_window_days": 14}}) == "P14D"
    assert resolve_analysis_timespan({
        "VM_IDLE": {"evaluation_window_days": 3},
        "DISK_IDLE": {"evaluation_window_days": 21},
    }) == "P21D"

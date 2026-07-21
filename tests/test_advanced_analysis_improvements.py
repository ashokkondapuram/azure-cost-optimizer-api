"""Tests for advanced analysis improvements (peak metrics, graph, chains, anomalies)."""

from __future__ import annotations

from app.analysis.resource_graph import (
    assign_action_chains,
    build_disk_snapshot_links,
    build_resource_graph,
)
from app.disk_utilization import peak_disk_iops_utilization_pct
from app.optimizer.resource_engines.cost.anomaly.analysis import analyze_cost_anomalies
from app.optimizer.resource_engines.cost.commitments.analysis import _is_stable_workload
from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.resource_pricing import compare_commitment_options
from app.optimizer.resource_engines.compute.vm.schedule import classify_workload_schedule
from app.resource_utilization import peak_cpu_ok_for_downsize


def test_peak_cpu_blocks_false_downsize_signal():
    resource = {"_technical_facts": {"max_cpu_pct": 50.0}}
    assert peak_cpu_ok_for_downsize(resource, avg_threshold=15.0) is False
    resource_low = {"_technical_facts": {"max_cpu_pct": 20.0}}
    assert peak_cpu_ok_for_downsize(resource_low, avg_threshold=15.0) is True


def test_peak_disk_iops_utilization():
    disk = {
        "properties": {"diskIOPSReadWrite": 1000},
        "_technical_facts": {"max_disk_read_iops": 200.0, "max_disk_write_iops": 100.0},
    }
    util = peak_disk_iops_utilization_pct(disk, disk)
    assert util == 30.0


def test_assign_action_chains_orders_vm_then_nic():
    vm_id = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    disk_id = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/d1"
    nic_id = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.network/networkinterfaces/nic1"
    buckets = {
        "vms": [{
            "id": vm_id,
            "properties": {
                "storageProfile": {
                    "osDisk": {"managedDisk": {"id": disk_id}},
                    "dataDisks": [],
                },
                "networkProfile": {"networkInterfaces": [{"id": nic_id}]},
            },
        }],
        "network_interfaces": [{"id": nic_id, "properties": {"ipConfigurations": []}}],
    }
    graph = build_resource_graph(buckets)
    assert disk_id.lower() in graph[vm_id.lower()]["disk_ids"]
    assert nic_id.lower() in graph[vm_id.lower()]["nic_ids"]


def test_assign_action_chains_orders_vm_then_nic():
    vm_id = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    nic_id = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.network/networkinterfaces/nic1"
    findings = [
        {
            "resource_id": nic_id,
            "rule_id": "NIC_UNATTACHED",
            "detail": "nic",
        },
        {
            "resource_id": vm_id,
            "rule_id": "VM_STOPPED_BILLING_EXTENDED",
            "detail": "vm",
        },
    ]
    graph = {vm_id.lower(): {"disk_ids": [], "nic_ids": [nic_id.lower()], "public_ip_ids": []}}
    chained = assign_action_chains(findings, graph)
    vm_finding = next(f for f in chained if f["resource_id"] == vm_id)
    nic_finding = next(f for f in chained if f["resource_id"] == nic_id)
    assert vm_finding["chain_step"] == 1
    assert nic_finding["chain_step"] == 2
    assert vm_finding["chain_id"] == nic_finding["chain_id"]


def test_cost_spike_anomaly_detection():
    engine = ExtendedOptimizationEngine()
    # Oldest-first: low baseline week, then elevated recent week.
    history = {
        "Virtual Machines": [10.0] * 7 + [25.0] * 7,
    }
    findings = analyze_cost_anomalies(engine, "sub", history)
    assert any(f.rule_id == "COST_SPIKE_DETECTED" for f in findings)


def test_stable_workload_rejects_declining_trend():
    declining = [float(100 - i) for i in range(28)]
    assert _is_stable_workload("rid", declining) is False
    stable = [50.0] * 28
    assert _is_stable_workload("rid", stable) is True


def test_compare_commitment_options_prefers_ri_3yr():
    result = compare_commitment_options(1000.0, "Standard_D2s_v3")
    assert result["best_option"] == "reserved_instance_3yr"
    assert result["best_monthly_savings_usd"] == 530.0


def test_aks_consolidation_rule_fires():
    from app.optimizer.resource_engines.containers.aks.analysis import _consolidation_score

    pool = {"name": "pool1", "count": 5, "vmSize": "Standard_D2s_v3"}
    cluster = {"_technical_facts": {"node_cpu_pct": 10.0, "node_mem_pct": 12.0}}
    score = _consolidation_score(pool, cluster, node_hourly_cost=0.2)
    assert score["recommended_nodes"] < 5
    assert score["recommended_nodes"] >= 2


def test_classify_schedule_candidate_from_idle_cost_days():
    vm = {
        "id": "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/ci-vm",
        "tags": {"environment": "dev"},
        "properties": {"instanceView": {"statuses": [{"code": "PowerState/deallocated"}]}},
        "_technical_facts": {"avg_cpu_pct": 2.0},
    }
    assert classify_workload_schedule(
        vm, vm["_technical_facts"], daily_cost=[0.0, 0.0, 0.0, 0.0, 0.0, 10.0, 10.0], power_state="deallocated",
    ) == "schedule_candidate"


def test_classify_zombie_candidate_low_cpu_always_on():
    vm = {
        "id": "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/zombie",
        "tags": {"environment": "dev"},
        "properties": {"instanceView": {"statuses": [{"code": "PowerState/running"}]}},
        "_technical_facts": {"avg_cpu_pct": 1.5},
    }
    assert classify_workload_schedule(
        vm, vm["_technical_facts"], daily_cost=[20.0] * 7, power_state="running",
    ) == "zombie_candidate"


def test_disk_snapshot_action_chain():
    disk_id = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/d1"
    snap_id = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/snapshots/s1"
    findings = [
        {"resource_id": snap_id, "rule_id": "SNAPSHOT_RETENTION_EXTENDED", "detail": "snap"},
        {"resource_id": disk_id, "rule_id": "DISK_UNUSED_EXTENDED", "detail": "disk"},
    ]
    links = build_disk_snapshot_links([
        {
            "id": snap_id,
            "properties": {"creationData": {"sourceResourceId": disk_id}},
        },
    ])
    chained = assign_action_chains(findings, {}, disk_snapshot_links=links)
    disk_f = next(f for f in chained if f["resource_id"] == disk_id)
    snap_f = next(f for f in chained if f["resource_id"] == snap_id)
    assert disk_f["chain_step"] == 1
    assert snap_f["chain_step"] == 2

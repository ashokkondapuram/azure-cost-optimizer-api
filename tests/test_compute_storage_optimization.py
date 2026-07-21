"""Tests for compute/storage optimization — catalog loaders and metric-driven rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.aks_metrics_catalog import load_aks_specifications, optimization_thresholds as aks_thresholds
from app.app_service_catalog import load_app_service_specifications
from app.app_service_plan_catalog import load_app_service_plan_specifications
from app.managed_disk_catalog import load_disk_specifications, parse_disk_arm
from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.resource_engines.compute.disk.optimization_rules import evaluate_disk_capacity_rightsize, evaluate_disk_queue_depth
from app.optimizer.resource_engines.compute.snapshot.optimization_rules import evaluate_snapshot_archive_candidate
from app.optimizer.resource_engines.compute.vm.optimization_rules import evaluate_vm_memory_pressure
from app.optimizer.resource_engines.compute.vmss.optimization_rules import evaluate_vmss_autoscale_tuning
from app.optimizer.resource_engines.storage.account.optimization_rules import evaluate_storage_egress_high
from app.snapshot_retention_catalog import load_snapshot_specifications
from app.storage_account_catalog import load_storage_specifications
from app.vm_metrics_catalog import load_vm_specifications, optimization_thresholds as vm_thresholds
from app.vmss_metrics_catalog import load_vmss_specifications, parse_vmss_arm


def test_catalog_json_files_load():
    assert load_vm_specifications().get("schema_version") == 1
    assert load_vmss_specifications().get("service")
    assert load_disk_specifications().get("disk_types")
    assert load_snapshot_specifications().get("retention_policy")
    assert load_aks_specifications().get("node_pool_defaults")
    assert load_app_service_specifications().get("tiers")
    assert load_app_service_plan_specifications().get("consolidation")
    storage_specs = load_storage_specifications()
    assert storage_specs.get("access_tiers")
    assert storage_specs.get("schema_version") >= 1


def test_vm_memory_pressure_fires_on_high_memory():
    rule = ADVANCED_RULES["VM_MEMORY_PRESSURE_EXTENDED"]
    vm = {
        "name": "vm1",
        "properties": {"hardwareProfile": {"vmSize": "Standard_D2s_v3"}},
        "_technical_facts": {"max_memory_pct": 92.0, "data_source": "azure_monitor"},
    }
    draft = evaluate_vm_memory_pressure(vm, {"vm_size": "Standard_D2s_v3"}, 50.0, rule)
    assert draft is not None
    assert draft.rule_id == "VM_MEMORY_PRESSURE_EXTENDED"
    assert draft.priority == "P1"


def test_vmss_autoscale_tuning_low_cpu():
    rule = ADVANCED_RULES["VMSS_AUTOSCALE_TUNING_EXTENDED"]
    vmss = {
        "name": "vmss1",
        "sku": {"capacity": 4},
        "properties": {"autoscaleSettings": {"profiles": []}},
        "_technical_facts": {"avg_cpu_pct": 18.0, "data_source": "azure_monitor"},
    }
    ctx = parse_vmss_arm(vmss)
    draft = evaluate_vmss_autoscale_tuning(vmss, ctx, 400.0, rule)
    assert draft is not None
    assert "scale in" in draft.recommendation.lower()


def test_disk_queue_depth_contention():
    rule = ADVANCED_RULES["DISK_QUEUE_DEPTH_EXTENDED"]
    disk = {
        "name": "disk1",
        "properties": {"diskState": "Attached", "diskSizeGB": 128},
        "sku": {"name": "Premium_LRS"},
        "_technical_facts": {"disk_queue_depth": 15.0, "data_source": "azure_monitor"},
    }
    draft = evaluate_disk_queue_depth(disk, 25.0, rule)
    assert draft is not None
    assert draft.priority == "P1"


def test_disk_capacity_savings_without_mtd_cost():
    rule = ADVANCED_RULES["DISK_CAPACITY_RIGHTSIZE_EXTENDED"]
    disk = {
        "name": "disk1",
        "properties": {"diskState": "Attached", "diskSizeGB": 128},
        "sku": {"name": "Premium_LRS"},
        "_technical_facts": {"disk_used_pct": 12.0, "data_source": "azure_monitor"},
    }
    draft = evaluate_disk_capacity_rightsize(disk, 0.0, rule)
    assert draft is not None
    assert draft.savings > 0


def test_vmss_autoscale_savings_without_mtd_cost():
    rule = ADVANCED_RULES["VMSS_AUTOSCALE_TUNING_EXTENDED"]
    vmss = {
        "name": "vmss1",
        "sku": {"capacity": 4},
        "properties": {"autoscaleSettings": {"profiles": []}},
        "_technical_facts": {"avg_cpu_pct": 18.0, "data_source": "azure_monitor"},
    }
    ctx = parse_vmss_arm(vmss)
    draft = evaluate_vmss_autoscale_tuning(vmss, ctx, 0.0, rule)
    assert draft is not None
    assert draft.savings > 0


def test_snapshot_archive_savings_without_mtd_cost():
    rule = ADVANCED_RULES["SNAPSHOT_ARCHIVE_EXTENDED"]
    created = datetime.now(timezone.utc) - timedelta(days=400)
    snapshot = {
        "name": "snap-old",
        "properties": {
            "timeCreated": created.isoformat(),
            "diskSizeGB": 100,
        },
    }
    draft = evaluate_snapshot_archive_candidate(snapshot, 0.0, rule)
    assert draft is not None
    assert draft.savings > 0


def test_snapshot_archive_candidate_old_snapshot():
    rule = ADVANCED_RULES["SNAPSHOT_ARCHIVE_EXTENDED"]
    created = datetime.now(timezone.utc) - timedelta(days=400)
    snapshot = {
        "name": "snap-old",
        "properties": {
            "timeCreated": created.isoformat(),
            "diskSizeGB": 100,
        },
    }
    draft = evaluate_snapshot_archive_candidate(snapshot, 12.0, rule)
    assert draft is not None
    assert draft.savings > 0


def test_storage_egress_high():
    rule = ADVANCED_RULES["STORAGE_EGRESS_HIGH_EXTENDED"]
    acct = {
        "name": "store1",
        "properties": {"accessTier": "Hot"},
        "_technical_facts": {"egress_bytes": 200_000_000_000, "data_source": "azure_monitor"},
    }
    draft = evaluate_storage_egress_high(acct, 80.0, rule)
    assert draft is not None
    assert draft.rule_id == "STORAGE_EGRESS_HIGH_EXTENDED"
    check = draft.evidence["checks"][0]
    assert "GB" in check["value_display"]
    assert check["threshold_display"].startswith("≥")


def test_new_rules_registered_in_advanced_rules():
    for rule_id in (
        "VM_MEMORY_PRESSURE_EXTENDED",
        "VM_EGRESS_HIGH_EXTENDED",
        "VMSS_AUTOSCALE_TUNING_EXTENDED",
        "DISK_CAPACITY_RIGHTSIZE_EXTENDED",
        "DISK_QUEUE_DEPTH_EXTENDED",
        "SNAPSHOT_ARCHIVE_EXTENDED",
        "AKS_NODE_MEMORY_PRESSURE_EXTENDED",
        "AKS_POD_DENSITY_EXTENDED",
        "ACR_IMAGE_RETENTION_EXTENDED",
        "WEBAPP_PLAN_LOAD_LOW_EXTENDED",
        "ASP_CONSOLIDATION_CANDIDATE_EXTENDED",
        "STORAGE_EGRESS_HIGH_EXTENDED",
        "STORAGE_COOL_TIER_CANDIDATE_EXTENDED",
    ):
        assert rule_id in ADVANCED_RULES


def test_threshold_defaults_match_catalog():
    vm = vm_thresholds()
    assert vm["cpu_downsize_pct"] == 20.0
    aks = aks_thresholds()
    assert aks["node_memory_pressure_pct"] == 85.0
    disk_ctx = parse_disk_arm({"properties": {"diskState": "Attached", "diskSizeGB": 64}, "sku": {"name": "Premium_LRS"}})
    assert disk_ctx["size_gb"] == 64

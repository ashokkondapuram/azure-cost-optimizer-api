"""Tests for Disks - Get ARM property normalization."""

from it_services.compute_disk.arm_disk_properties import (
    disk_attachment_arm_ids,
    disk_property_value,
    normalize_disk_arm_properties,
)
from app.managed_disk_catalog import resolve_disk_provisioned_performance


def test_disk_property_value_reads_pascal_case_timestamps():
    arm = {
        "properties": {
            "LastOwnershipUpdateTime": "2026-04-21T04:41:35.079872+00:00",
            "TimeCreated": "2026-04-20T04:41:35.079872+00:00",
        }
    }
    assert disk_property_value(arm, "lastOwnershipUpdateTime") == "2026-04-21T04:41:35.079872+00:00"
    assert disk_property_value(arm, "timeCreated") == "2026-04-20T04:41:35.079872+00:00"


def test_disk_attachment_arm_ids_from_managed_by_extended():
    arm = {
        "managedByExtended": [
            "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
            "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-b",
        ],
        "properties": {"diskState": "Attached"},
    }
    assert disk_attachment_arm_ids(arm) == [
        "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
        "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-b",
    ]


def test_normalize_disk_arm_properties_includes_tier_and_extended_hosts():
    arm = {
        "sku": {"name": "Premium_LRS"},
        "managedByExtended": ["/subscriptions/s/rg/providers/Microsoft.Compute/virtualMachines/host"],
        "properties": {
            "diskSizeGB": 512,
            "tier": "P50",
            "DiskState": "Attached",
        },
    }
    props = normalize_disk_arm_properties(arm)
    assert props["tier"] == "P50"
    assert props["diskState"] == "Attached"
    assert props["sku"] == "Premium_LRS"
    assert props["managedByExtended"][0].endswith("/virtualMachines/host")


def test_resolve_provisioned_performance_uses_properties_tier():
    disk = {
        "sku": {"name": "Premium_LRS"},
        "properties": {"diskSizeGB": 512, "tier": "P20"},
    }
    perf = resolve_disk_provisioned_performance(disk)
    assert perf["diskIOPSReadWrite"] == 2300
    assert perf["diskMBpsReadWrite"] == 150
    assert perf["provisionedPerformanceSource"] == "performance_tier"

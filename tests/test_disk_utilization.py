"""Tests for disk IOPS utilization helpers."""

from app.disk_utilization import (
    combined_disk_iops,
    disk_iops_utilization_pct,
    is_disk_underprovisioned,
    is_low_disk_iops_utilization,
    metrics_block_disk_downgrade,
    provisioned_iops,
)


def _attached_premium_disk(*, iops_cap: int = 5000) -> dict:
    return {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/disks/data1",
        "name": "data1",
        "sku": {"name": "Premium_LRS"},
        "properties": {
            "diskState": "Attached",
            "diskSizeGB": 256,
            "diskIOPSReadWrite": iops_cap,
            "diskMBpsReadWrite": 200,
        },
    }


def test_provisioned_iops_from_inventory():
    disk = _attached_premium_disk(iops_cap=3000)
    assert provisioned_iops(disk) == 3000.0


def test_provisioned_iops_from_tier_when_arm_missing():
    disk = {
        "sku": {"name": "StandardSSD_LRS"},
        "properties": {"diskSizeGB": 256, "diskState": "Attached"},
    }
    assert provisioned_iops(disk) == 500.0


def test_provisioned_iops_with_string_sku():
    disk = {
        "sku": "Premium_LRS",
        "properties": {"diskSizeGB": 256, "diskState": "Attached"},
    }
    assert provisioned_iops(disk) == 3500.0


def test_combined_disk_iops_from_monitor_facts():
    resource = {
        "_technical_facts": {
            "disk_read_iops": 120.0,
            "disk_write_iops": 80.0,
        },
    }
    assert combined_disk_iops(resource) == 200.0


def test_disk_iops_utilization_pct():
    disk = _attached_premium_disk(iops_cap=1000)
    resource = {
        "_technical_facts": {"disk_read_iops": 150.0, "disk_write_iops": 50.0},
    }
    assert disk_iops_utilization_pct(resource, disk) == 20.0


def test_metrics_block_disk_downgrade_at_threshold():
    disk = _attached_premium_disk(iops_cap=1000)
    resource = {
        "_technical_facts": {"disk_read_iops": 150.0, "disk_write_iops": 50.0},
    }
    assert metrics_block_disk_downgrade(resource, disk) is True


def test_metrics_block_disk_downgrade_when_idle_iops():
    disk = _attached_premium_disk(iops_cap=5000)
    resource = {
        "_technical_facts": {"disk_read_iops": 5.0, "disk_write_iops": 2.0},
    }
    assert metrics_block_disk_downgrade(resource, disk) is False
    assert is_low_disk_iops_utilization(resource, disk) is True


def test_is_disk_underprovisioned_when_near_cap():
    disk = _attached_premium_disk(iops_cap=1000)
    resource = {
        "_technical_facts": {"disk_read_iops": 700.0, "disk_write_iops": 150.0},
    }
    assert is_disk_underprovisioned(resource, disk) is True

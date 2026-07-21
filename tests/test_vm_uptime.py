"""Tests for VM / VMSS uptime from timeCreated and instanceView."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.vm_uptime import (
    fetch_vmss_instance_uptime,
    time_created_from_instance_view,
    time_created_from_vm,
    uptime_hours_since,
    vm_uptime_facts,
)


def test_time_created_from_instance_view_provisioning_status():
    iv = {
        "statuses": [
            {"code": "ProvisioningState/succeeded", "time": "2025-12-12T19:07:00Z"},
            {"code": "PowerState/running", "time": "2025-12-12T19:08:00Z"},
        ],
    }
    created = time_created_from_instance_view(iv)
    assert created == datetime(2025, 12, 12, 19, 7, tzinfo=timezone.utc)


def test_time_created_from_vm_properties():
    vm = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        "properties": {"timeCreated": "2025-06-01T12:00:00Z"},
    }
    assert time_created_from_vm(vm) == datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_vm_uptime_facts_from_vmss_oldest_instance():
    created = datetime.now(timezone.utc) - timedelta(days=30)
    vmss = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/aks-pool",
        "sku": {"capacity": 2},
        "properties": {
            "provisioningState": "Succeeded",
            "oldest_instance_time_created": created.isoformat(),
        },
        "_canonical_type": "compute/vmss",
    }
    facts = vm_uptime_facts(vmss)
    assert facts["uptime_source"] == "vmss_instance"
    assert facts["uptime_hours"] >= 24 * 29
    assert facts["is_running"] is True


def test_fetch_vmss_instance_uptime_uses_instance_views():
    created_old = datetime(2025, 12, 12, 19, 7, tzinfo=timezone.utc)
    created_new = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)

    class FakeClient:
        def list_vm_scale_set_vms(self, subscription_id, rg, name):
            return [
                {"name": f"{name}_0", "instanceId": "0", "properties": {}},
                {"name": f"{name}_1", "instanceId": "1", "properties": {}},
            ]

        def get_vm_scale_set_vm_instance_view(self, subscription_id, rg, name, instance_id):
            if instance_id == "0":
                return {
                    "statuses": [
                        {"code": "ProvisioningState/succeeded", "time": created_old.isoformat().replace("+00:00", "Z")},
                    ],
                }
            return {
                "statuses": [
                    {"code": "ProvisioningState/succeeded", "time": created_new.isoformat().replace("+00:00", "Z")},
                ],
            }

    vmss = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/myvmss",
        "name": "myvmss",
    }
    result = fetch_vmss_instance_uptime(FakeClient(), "s", vmss)
    assert result["vmss_instance_count"] == 2
    assert result["oldest_instance_time_created"] == created_old.isoformat()
    assert result["newest_instance_time_created"] == created_new.isoformat()


def test_uptime_hours_since_never_negative():
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    assert uptime_hours_since(future) == 0.0

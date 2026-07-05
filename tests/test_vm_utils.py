"""Tests for VM vs VMSS separation helpers."""

from app.vm_utils import (
    filter_standalone_vms,
    is_scale_set_instance,
    vmss_display_sku,
)


def _standalone_vm(name: str = "vm1") -> dict:
    return {
        "id": f"/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/{name}",
        "name": name,
        "properties": {"hardwareProfile": {"vmSize": "Standard_D2s_v3"}},
    }


def _vmss_instance(name: str = "vmss000001") -> dict:
    return {
        "id": (
            "/subscriptions/s/resourceGroups/rg/providers/"
            "Microsoft.Compute/virtualMachineScaleSets/myvmss/virtualMachines/0"
        ),
        "name": name,
        "properties": {
            "virtualMachineScaleSet": {
                "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/myvmss",
            },
        },
    }


def test_is_scale_set_instance_by_property():
    assert is_scale_set_instance(_vmss_instance()) is True
    assert is_scale_set_instance(_standalone_vm()) is False


def test_is_scale_set_instance_by_resource_id():
    vm = {
        "id": (
            "/subscriptions/s/resourceGroups/rg/providers/"
            "Microsoft.Compute/virtualMachineScaleSets/set1/virtualMachines/3"
        ),
        "properties": {},
    }
    assert is_scale_set_instance(vm) is True


def test_filter_standalone_vms():
    vms = [_standalone_vm("a"), _vmss_instance(), _standalone_vm("b")]
    filtered = filter_standalone_vms(vms)
    assert [v["name"] for v in filtered] == ["a", "b"]


def test_vmss_display_sku():
    item = {
        "sku": {"name": "Standard_D2s_v3", "capacity": 3},
        "properties": {
            "virtualMachineProfile": {
                "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
            },
        },
    }
    assert vmss_display_sku(item) == "Standard_D2s_v3 · 3 instances"

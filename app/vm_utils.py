"""Helpers to separate standalone VMs from virtual machine scale set instances."""

from __future__ import annotations

from typing import Any


def is_scale_set_instance(vm: dict[str, Any]) -> bool:
    """True when an ARM VM resource is an instance belonging to a VMSS."""
    props = vm.get("properties") or {}
    if props.get("virtualMachineScaleSet"):
        return True
    rid = (vm.get("id") or "").lower()
    # Scale set instance IDs include the parent scale set path.
    return "/virtualmachinescalesets/" in rid and "/virtualmachines/" in rid


def filter_standalone_vms(vms: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Drop VMSS instance VMs; keep only standalone virtual machines."""
    return [vm for vm in (vms or []) if not is_scale_set_instance(vm)]


def vmss_display_sku(item: dict[str, Any]) -> str | None:
    """VM size + instance count for list UI."""
    sku_obj = item.get("sku") or {}
    vm_size = (
        (item.get("properties") or {})
        .get("virtualMachineProfile", {})
        .get("hardwareProfile", {})
        .get("vmSize")
    )
    capacity = sku_obj.get("capacity")
    parts: list[str] = []
    if vm_size:
        parts.append(str(vm_size))
    if capacity is not None:
        parts.append(f"{capacity} instances")
    elif sku_obj.get("name"):
        parts.append(str(sku_obj["name"]))
    return " · ".join(parts) if parts else None

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


def _vmss_capacity(item: dict[str, Any], properties: dict[str, Any] | None = None) -> int | None:
    """Best-effort instance count from ARM sku or synced enrichment fields."""
    props = properties if properties is not None else (item.get("properties") or {})
    sku_obj = item.get("sku") or {}
    for raw in (
        sku_obj.get("capacity"),
        props.get("instance_count"),
        props.get("vmss_instance_count"),
    ):
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def vmss_operational_state(item: dict[str, Any]) -> str:
    """
    Derive list-friendly VMSS status from provisioning state and instance count.

    Azure list responses expose provisioningState (e.g. Succeeded) but not power state;
    capacity 0 means scaled to zero (stopped), capacity > 0 means running instances.
    """
    props = item.get("properties") or {}
    prov = str(props.get("provisioningState") or "").strip()
    if prov and prov.lower() not in ("", "succeeded"):
        return prov
    capacity = _vmss_capacity(item, props)
    if capacity is not None:
        return "Stopped" if capacity <= 0 else "Running"
    return prov or "Unknown"


def vmss_operational_state_from_props(properties: dict[str, Any], state: str | None = None) -> str:
    """Display state when only synced properties_json is available."""
    props = properties or {}
    power = str(props.get("powerState") or "").strip()
    if power:
        return power.split("/")[-1] if "/" in power else power
    text = (state or "").strip()
    if text and text.lower() not in ("succeeded", "creating", "updating", "deleting"):
        return text.split("/")[-1] if "/" in text else text
    prov = str(props.get("provisioningState") or "").strip()
    if prov and prov.lower() not in ("", "succeeded"):
        return prov
    for raw in (props.get("instance_count"), props.get("vmss_instance_count")):
        if raw is None:
            continue
        try:
            cap = int(raw)
            return "Stopped" if cap <= 0 else "Running"
        except (TypeError, ValueError):
            continue
    return prov or text or "Unknown"


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

"""Merge Node Auto Provisioning (NAP) VMSS into AKS agent pool profiles."""

from __future__ import annotations

from typing import Any

from it_services.containers_aks.engine.helpers import is_node_auto_provisioning_enabled
from it_services.containers_aks.vmss_match import (
    _vmss_pool_ref,
    filter_vmss_for_resource_group,
    vmss_id_for_pool,
)

NAP_POOL_MODE_LABEL = "Auto provisioning"


def pool_name_from_vmss(vmss_name: str) -> str:
    """Derive a stable pool display name from an AKS node VMSS resource name."""
    name = str(vmss_name or "").strip()
    if not name:
        return ""
    lower = name.lower()
    if lower.endswith("-vmss"):
        name = name[: -len("-vmss")]
        lower = name.lower()
    if lower.startswith("aks-"):
        name = name[4:]
    parts = [part for part in name.split("-") if part]
    if len(parts) > 1 and len(parts[-1]) >= 8:
        parts = parts[:-1]
    return "-".join(parts) if parts else str(vmss_name).replace("-vmss", "")


def merge_aks_pool_profiles(*pool_lists: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Merge agent pool profile lists by pool name (later entries fill missing fields)."""
    by_name: dict[str, dict[str, Any]] = {}
    for pools in pool_lists:
        for pool in pools or []:
            if not isinstance(pool, dict):
                continue
            name = str(pool.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in by_name:
                merged = dict(by_name[key])
                for field, value in pool.items():
                    if value not in (None, ""):
                        merged[field] = value
                by_name[key] = merged
            else:
                by_name[key] = dict(pool)
    return list(by_name.values())


def merge_nap_pools_from_vmss(
    pools: list[dict[str, Any]],
    vmss_list: list[dict[str, Any]] | None,
    *,
    cluster_props: dict[str, Any] | None = None,
    node_resource_group: str = "",
    nap_enabled: bool | None = None,
) -> list[dict[str, Any]]:
    """Attach synthetic pool rows for NAP VMSS not already linked to agentPoolProfiles."""
    props = cluster_props or {}
    enabled = nap_enabled if nap_enabled is not None else is_node_auto_provisioning_enabled(props)
    node_rg = str(node_resource_group or props.get("nodeResourceGroup") or "").strip()
    if not enabled or not node_rg:
        return pools

    scoped = filter_vmss_for_resource_group(vmss_list or [], node_rg)
    if not scoped:
        return pools

    matched_ids: set[str] = set()
    for pool in pools or []:
        vmss_id = vmss_id_for_pool(
            pool,
            node_resource_group=node_rg,
            vmss_list=scoped,
        )
        if vmss_id:
            matched_ids.add(vmss_id.lower())

    existing_names = {
        str(pool.get("name") or "").strip().lower()
        for pool in pools or []
        if pool.get("name")
    }
    merged = list(pools or [])

    for vmss in scoped:
        vmss_id = str(vmss.get("id") or "").strip()
        if not vmss_id or vmss_id.lower() in matched_ids:
            continue

        base_name = pool_name_from_vmss(str(vmss.get("name") or ""))
        if not base_name:
            continue

        pool_name = base_name
        suffix = 2
        while pool_name.lower() in existing_names:
            pool_name = f"{base_name}-{suffix}"
            suffix += 1
        existing_names.add(pool_name.lower())

        sku = vmss.get("sku") or {}
        props_vmss = vmss.get("properties") or {}
        storage = props_vmss.get("storageProfile") or {}
        os_disk = storage.get("osDisk") or {}
        merged.append({
            "name": pool_name,
            "count": sku.get("capacity") or 0,
            "vmSize": sku.get("name"),
            "mode": NAP_POOL_MODE_LABEL,
            "osType": os_disk.get("osType") or "Linux",
            "nodeProvisioningMode": "Auto",
            "_napPool": True,
            "virtualMachineScaleSet": _vmss_pool_ref(vmss, vmss_id=vmss_id),
        })
        matched_ids.add(vmss_id.lower())

    return merged

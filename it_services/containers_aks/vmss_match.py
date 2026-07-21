"""Match AKS agent pools to backing VM scale sets in the node resource group."""

from __future__ import annotations

from typing import Any


def _resource_group_from_arm_id(resource_id: str) -> str:
    parts = (resource_id or "").split("/")
    try:
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""


def vmss_name_prefix_for_pool(pool_name: str) -> str:
    return f"aks-{str(pool_name or '').strip().lower()}-"


def _vmss_ref_id(vmss_ref: Any) -> str:
    """Return the ARM id from a VMSS reference (dict or bare string)."""
    if isinstance(vmss_ref, str):
        return vmss_ref.strip()
    if isinstance(vmss_ref, dict):
        return str(vmss_ref.get("id") or "").strip()
    return ""


def match_pool_vmss(pool_name: str, vmss_list: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the VMSS resource dict that backs an AKS agent pool, if found."""
    if not pool_name or not vmss_list:
        return None

    pool_lower = str(pool_name).strip().lower()
    prefix = vmss_name_prefix_for_pool(pool_name)
    exact = f"aks-{pool_lower}"

    candidates: list[tuple[int, dict[str, Any]]] = []
    for vmss in vmss_list:
        name = str(vmss.get("name") or "").strip().lower()
        if not name:
            continue
        if name.startswith(prefix) or name == exact or name.startswith(f"{exact}-"):
            candidates.append((len(name), vmss))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def resolve_pool_vmss(
    pool: dict[str, Any],
    *,
    node_resource_group: str = "",
    vmss_list: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Resolve the backing VMSS for an agent pool profile."""
    if not isinstance(pool, dict):
        return None

    props = pool.get("properties") or {}
    direct = pool.get("virtualMachineScaleSet") or props.get("virtualMachineScaleSet")
    direct_id = direct if isinstance(direct, str) else (direct or {}).get("id")
    if direct_id:
        direct_id = str(direct_id).strip()
        if direct_id:
            return {"id": direct_id, "name": direct_id.rsplit("/", 1)[-1]}

    node_rg = str(node_resource_group or "").strip()
    if not node_rg or not vmss_list:
        return None

    scoped = filter_vmss_for_resource_group(vmss_list, node_rg)
    return match_pool_vmss(str(pool.get("name") or ""), scoped)


def filter_vmss_for_resource_group(
    vmss_list: list[dict[str, Any]],
    resource_group: str,
) -> list[dict[str, Any]]:
    """Keep VMSS resources that live in the given resource group."""
    rg_lower = str(resource_group or "").strip().lower()
    if not rg_lower:
        return []
    return [
        vmss for vmss in (vmss_list or [])
        if _resource_group_from_arm_id(str(vmss.get("id") or "")).lower() == rg_lower
    ]


def _vmss_pool_ref(
    matched: dict[str, Any] | None,
    *,
    vmss_id: str = "",
) -> dict[str, Any]:
    """Build the virtualMachineScaleSet object stored on an agent pool profile."""
    if matched:
        props = matched.get("properties") or {}
        sku = matched.get("sku") or {}
        ref: dict[str, Any] = {
            "id": str(matched.get("id") or vmss_id).strip(),
            "name": str(matched.get("name") or "").strip() or None,
        }
        sku_name = sku.get("name")
        if sku_name:
            ref["sku"] = sku_name
        capacity = sku.get("capacity")
        if capacity is not None:
            ref["capacity"] = capacity
        prov = props.get("provisioningState")
        if prov:
            ref["provisioningState"] = prov
        return {key: value for key, value in ref.items() if value not in (None, "")}

    rid = str(vmss_id or "").strip()
    if not rid:
        return {}
    return {"id": rid, "name": rid.rsplit("/", 1)[-1]}


def vmss_id_for_pool(
    pool: dict[str, Any],
    *,
    vmss_by_pool: dict[str, Any] | None = None,
    node_resource_group: str = "",
    vmss_list: list[dict[str, Any]] | None = None,
) -> str:
    """Resolve the backing VMSS ARM ID for an agent pool profile."""
    matched = resolve_pool_vmss(
        pool,
        node_resource_group=node_resource_group,
        vmss_list=vmss_list or [],
    )
    if matched:
        rid = str(matched.get("id") or "").strip()
        if rid:
            return rid

    pool_name = str(pool.get("name") or "").strip()
    if pool_name and vmss_by_pool:
        ref = vmss_by_pool.get(pool_name)
        if isinstance(ref, str) and ref.strip():
            return ref.strip()
        if isinstance(ref, dict):
            rid = str(ref.get("id") or "").strip()
            if rid:
                return rid
    return ""


def vmss_by_pool_map(pools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map agent pool name -> embedded virtualMachineScaleSet ref."""
    out: dict[str, dict[str, Any]] = {}
    for pool in pools or []:
        if not isinstance(pool, dict):
            continue
        name = str(pool.get("name") or "").strip()
        vmss_ref = pool.get("virtualMachineScaleSet")
        if name and isinstance(vmss_ref, dict) and vmss_ref.get("id"):
            out[name] = vmss_ref
    return out


def enrich_pools_with_vmss(
    pools: list[dict[str, Any]],
    vmss_list: list[dict[str, Any]],
    *,
    node_resource_group: str | None = None,
) -> list[dict[str, Any]]:
    """Attach virtualMachineScaleSet refs to normalized agent pool profiles."""
    if not pools:
        return pools

    enriched: list[dict[str, Any]] = []
    for pool in pools:
        if not isinstance(pool, dict):
            continue
        next_pool = dict(pool)
        matched: dict[str, Any] | None = None
        vmss_id = _vmss_ref_id(next_pool.get("virtualMachineScaleSet"))
        if not vmss_id:
            matched = resolve_pool_vmss(
                next_pool,
                node_resource_group=node_resource_group or "",
                vmss_list=vmss_list,
            )
            vmss_id = str((matched or {}).get("id") or "").strip()
        if vmss_id:
            next_pool["virtualMachineScaleSet"] = _vmss_pool_ref(matched, vmss_id=vmss_id)
        enriched.append(next_pool)
    return enriched

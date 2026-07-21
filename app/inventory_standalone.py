"""Canonical types excluded from standalone inventory (embedded under parent resources)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.focus_mapping import normalize_arm_id
from app.resources.registry import TECHNICAL_FETCH_SPECS

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

EMBEDDED_VMSS_ANALYSIS_MESSAGE = (
    "VM scale set is managed under AKS node pools. "
    "Open the parent cluster to view utilization and recommendations."
)

# VMSS backing AKS node pools is embedded on containers/aks agentPoolProfiles only.
STANDALONE_INVENTORY_EXCLUDED: frozenset[str] = frozenset(
    spec.canonical_type
    for spec in TECHNICAL_FETCH_SPECS.values()
    if not spec.sync_as_standalone
)


def is_standalone_inventory_type(canonical_type: str | None) -> bool:
    """True when a canonical type may appear as its own inventory row."""
    return (canonical_type or "").strip().lower() not in STANDALONE_INVENTORY_EXCLUDED


def filter_standalone_inventory_rows(rows: list[dict]) -> list[dict]:
    """Drop embedded-only resource types from API list payloads."""
    return [
        row for row in rows
        if is_standalone_inventory_snapshot(row)
    ]


def is_embedded_only_arm_id(resource_id: str | None) -> bool:
    """True for VMSS scale sets and VMSS instance VMs (embedded under AKS)."""
    rid = (resource_id or "").strip().lower()
    return "/virtualmachinescalesets/" in rid


def is_managed_aks_vmss(resource_id: str | None, canonical_type: str | None = None) -> bool:
    """True when a resource is a VMSS managed under AKS rather than standalone inventory."""
    if is_embedded_only_arm_id(resource_id):
        return True
    ctype = (canonical_type or "").strip().lower()
    return bool(ctype) and not is_standalone_inventory_type(ctype)


def _vmss_ref_id(vmss_ref: object) -> str:
    if isinstance(vmss_ref, str):
        return normalize_arm_id(vmss_ref)
    if isinstance(vmss_ref, dict):
        return normalize_arm_id(str(vmss_ref.get("id") or ""))
    return ""


def resolve_aks_cluster_for_embedded_vmss(
    db: Session,
    subscription_id: str,
    vmss_arm_id: str,
) -> str | None:
    """Return the parent AKS cluster ARM ID when vmss_arm_id backs an agent pool."""
    from app.models import ResourceSnapshot
    from it_services.containers_aks.vmss_match import (
        _resource_group_from_arm_id,
        vmss_name_prefix_for_pool,
    )

    vmss_rid = normalize_arm_id(vmss_arm_id)
    if not vmss_rid or not is_embedded_only_arm_id(vmss_rid):
        return None

    sub = subscription_id.lower()
    vmss_name = vmss_rid.rsplit("/", 1)[-1].lower()
    vmss_rg = _resource_group_from_arm_id(vmss_rid).lower()

    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.resource_type == "containers/aks",
            ResourceSnapshot.is_active.is_(True),
        )
        .all()
    )
    for row in rows:
        try:
            props = json.loads(row.properties_json or "{}")
        except Exception:
            props = {}

        for pool in props.get("agentPoolProfiles") or []:
            ref_id = _vmss_ref_id(pool.get("virtualMachineScaleSet"))
            if ref_id == vmss_rid:
                return normalize_arm_id(row.resource_id or "")

        for ref in (props.get("_vmssByPool") or {}).values():
            if isinstance(ref, dict) and _vmss_ref_id(ref) == vmss_rid:
                return normalize_arm_id(row.resource_id or "")

        node_rg = str(props.get("nodeResourceGroup") or "").strip().lower()
        if not vmss_rg or not node_rg or vmss_rg != node_rg:
            continue
        for pool in props.get("agentPoolProfiles") or []:
            pool_name = str(pool.get("name") or "").strip()
            if not pool_name:
                continue
            pool_lower = pool_name.lower()
            prefix = vmss_name_prefix_for_pool(pool_name)
            if (
                vmss_name.startswith(prefix)
                or vmss_name == f"aks-{pool_lower}"
                or vmss_name.startswith(f"aks-{pool_lower}-")
            ):
                return normalize_arm_id(row.resource_id or "")

    return None


def is_standalone_inventory_snapshot(row: object) -> bool:
    """True when a snapshot or dict row may appear as standalone inventory."""
    rtype = (
        getattr(row, "resource_type", None)
        or (row.get("type") if isinstance(row, dict) else None)
        or (row.get("resource_type") if isinstance(row, dict) else None)
    )
    if not is_standalone_inventory_type(rtype):
        return False
    rid = (
        getattr(row, "resource_id", None)
        or (row.get("id") if isinstance(row, dict) else None)
        or (row.get("resource_id") if isinstance(row, dict) else None)
    )
    return not is_embedded_only_arm_id(rid)


def standalone_inventory_snapshot_filter():
    """SQLAlchemy predicate for ResourceSnapshot standalone inventory queries."""
    from sqlalchemy import and_, not_

    from app.models import ResourceSnapshot

    excluded_types = sorted(STANDALONE_INVENTORY_EXCLUDED)
    clauses = []
    if excluded_types:
        clauses.append(ResourceSnapshot.resource_type.notin_(excluded_types))
    clauses.append(
        not_(ResourceSnapshot.resource_id.ilike("%/virtualmachinescalesets/%"))
    )
    return and_(*clauses)

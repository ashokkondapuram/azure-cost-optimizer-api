"""
db_sync.py — Azure → Database sync service

Call sync_all(subscription_id, db) to pull fresh data from Azure
and write it into the local DB. All API reads go through the DB after that.

Synced entities:
  - Subscriptions
  - Resources (VMs, Disks, AKS, Storage, Public IPs, SQL,
               Key Vaults, App Services, Load Balancers, CosmosDB,
               PostgreSQL, NSGs, ACR, App Gateways)
  - Costs by service (MTD)
  - Daily costs by resource group and by service
  - Per-resource MTD costs (PreTaxCost from Cost Management)
  - Budgets
"""

import json
import uuid
import gc
from datetime import datetime, timezone, date
from typing import Any, Optional

import structlog
from sqlalchemy.orm import Session

from app.models import (
    ResourceSnapshot, CostSnapshot, CostDailyByServiceSnapshot,
    CostByResourceSnapshot, CostByServiceSnapshot, CostSyncRun, SubscriptionCache,
    OptimizationFinding,
)
from app.azure_resources import AzureResourcesClient
from app import cost_export
from app.resources import (
    generic_arm_sync_types,
    get_technical_fetch_spec,
    pick_sync_properties,
)
from app.http_client import arm_patient_sync
from app.parallel_arm_sync import parallel_fetch
from app.db_sync_parallel import fetch_arm_lists_parallel
from app.bulk_resource_upsert import bulk_upsert_snapshots, _snapshot_mapping
from app.sync_scope import normalize_sync_types
from app.arm_resource_enrichment import enrich_arm_resources_for_type
from app.arm_sku_sync import VmSkuCatalogCache, build_sync_sku_fields, build_app_service_plan_sku_index, format_app_service_webapp_label
from app.disk_staleness import enrich_disk_sync_properties
from app.cost_utils import (
    aggregate_cost_rows_by_service,
    cost_column_indices,
    parse_cost_by_resource_details,
    service_name_from_cost_row,
)
from app.subscription_store import ensure_subscription_cache_row, sync_subscription_catalog
from app.vm_utils import filter_standalone_vms, is_scale_set_instance
from app.vm_uptime import enrich_vmss_list_with_instance_uptime

log = structlog.get_logger(__name__)


def _now():
    return datetime.now(timezone.utc)


def _find_resource_snapshot(db: Session, subscription_id: str, resource_id: str) -> ResourceSnapshot | None:
    """Find snapshot in DB or pending session inserts (autoflush may be off)."""
    sub = subscription_id.lower()
    rid = resource_id.lower().rstrip("/")
    for obj in db.new:
        if not isinstance(obj, ResourceSnapshot):
            continue
        if obj.subscription_id == sub and obj.resource_id == rid:
            return obj
    return (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.resource_id == rid,
        )
        .first()
    )


# Canonical types synced via dedicated list_* blocks — skip generic ARM list to avoid duplicates.
_DEDICATED_TYPED_SYNC_CANONICALS = frozenset({
    "network/vnet",
    "network/privateendpoint",
    "network/privatelinkservice",
    "network/privatedns",
})


def _upsert_resource(
    db: Session,
    subscription_id: str,
    resource_id: str,
    resource_name: str,
    resource_type: str,
    resource_group: str = None,
    location: str = None,
    sku: str = None,
    sku_json: dict | None = None,
    state: str = None,
    tags: dict = None,
    properties: dict = None,
    monthly_cost: float | None = None,
):
    """Insert or update a single resource in resource_snapshots."""
    from app.focus_mapping import normalize_arm_id

    resource_id = normalize_arm_id(resource_id)
    subscription_id = subscription_id.lower()
    existing = _find_resource_snapshot(db, subscription_id, resource_id)
    now = _now()
    props = properties or {}
    is_cost_export_only = props.get("source") == "cost_export"
    sku_json_text = json.dumps(sku_json or {})
    if existing:
        existing.resource_name    = resource_name
        existing.resource_type    = resource_type
        existing.resource_group   = resource_group
        existing.location         = location
        existing.sku              = sku
        existing.sku_json         = sku_json_text
        existing.state            = state
        existing.tags_json        = json.dumps(tags or {})
        existing.properties_json  = json.dumps(props)
        existing.is_cost_export_only = is_cost_export_only
        if monthly_cost is not None:
            existing.monthly_cost_usd = monthly_cost
        existing.is_active        = True
        existing.synced_at        = now
    else:
        db.add(ResourceSnapshot(
            id               = str(uuid.uuid4()),
            subscription_id  = subscription_id,
            resource_id      = resource_id,
            resource_name    = resource_name,
            resource_type    = resource_type,
            resource_group   = resource_group,
            location         = location,
            sku              = sku,
            sku_json         = sku_json_text,
            state            = state,
            tags_json        = json.dumps(tags or {}),
            properties_json  = json.dumps(props),
            is_cost_export_only = is_cost_export_only,
            monthly_cost_usd = monthly_cost if monthly_cost is not None else 0.0,
            is_active        = True,
            synced_at        = now,
        ))

    from app.resource_pricing import upsert_resource_pricing_profile

    upsert_resource_pricing_profile(
        db,
        subscription_id=subscription_id,
        resource_id=resource_id,
        resource_name=resource_name,
        canonical_type=resource_type,
        sku_label=sku,
        sku_json=sku_json or {},
        cost_mtd=float(monthly_cost or 0.0),
    )


def _bulk_upsert_arm_list(
    db: Session,
    subscription_id: str,
    arm_items: list[dict],
    canonical_type: str,
    *,
    catalog_cache: VmSkuCatalogCache | None = None,
    state_fn=None,
    properties_fn=None,
    sku_label_fn=None,
) -> int:
    """Build snapshot mappings and bulk-upsert a list of ARM resources."""
    mappings = []
    for item in arm_items:
        rid = item.get("id", "")
        spec = get_technical_fetch_spec(canonical_type)
        props = properties_fn(item) if properties_fn else pick_sync_properties(item, spec)
        sku_str, sku_payload = build_sync_sku_fields(
            item,
            canonical_type,
            catalog_cache=catalog_cache,
            sku_label_override=sku_label_fn(item) if sku_label_fn else None,
        )
        state = state_fn(item) if state_fn else (item.get("properties") or {}).get("provisioningState")
        mappings.append(_snapshot_mapping(
            subscription_id,
            resource_id=rid,
            resource_name=item.get("name", ""),
            resource_type=canonical_type,
            resource_group=_extract_rg(rid),
            location=item.get("location"),
            sku=sku_str,
            sku_json=sku_payload,
            state=state,
            tags=item.get("tags") or {},
            properties=props,
        ))
    written = bulk_upsert_snapshots(db, subscription_id, mappings)
    from app.resource_pricing import upsert_resource_pricing_profile
    for m in mappings:
        upsert_resource_pricing_profile(
            db,
            subscription_id=subscription_id,
            resource_id=m["resource_id"],
            resource_name=m["resource_name"],
            canonical_type=canonical_type,
            sku_label=m.get("sku"),
            sku_json=json.loads(m.get("sku_json") or "{}"),
            cost_mtd=float(m.get("monthly_cost_usd") or 0.0),
        )
    return written


def _bulk_sync_pick_properties(
    db: Session,
    subscription_id: str,
    items: list[dict],
    canonical_type: str,
    catalog_cache: VmSkuCatalogCache | None,
    *,
    state_fn,
) -> int:
    """Bulk upsert with pick_sync_properties and a per-item state resolver."""
    if not items:
        return 0
    spec = get_technical_fetch_spec(canonical_type)
    for item in items:
        item["_sync_state"] = state_fn(item)
        item["_sync_props"] = pick_sync_properties(item, spec)
    return _bulk_upsert_arm_list(
        db,
        subscription_id,
        items,
        canonical_type,
        catalog_cache=catalog_cache,
        state_fn=lambda i: i.get("_sync_state"),
        properties_fn=lambda i: i.get("_sync_props") or {},
    )


def _upsert_arm_resource(
    db: Session,
    subscription_id: str,
    arm_resource: dict,
    canonical_type: str,
    *,
    catalog_cache: VmSkuCatalogCache | None = None,
    state: str | None = None,
    properties: dict | None = None,
    monthly_cost: float | None = None,
    sku_label: str | None = None,
) -> None:
    """Upsert one ARM resource with full SKU/item details persisted."""
    rid = arm_resource.get("id", "")
    spec = get_technical_fetch_spec(canonical_type)
    props = properties if properties is not None else pick_sync_properties(arm_resource, spec)
    sku_str, sku_payload = build_sync_sku_fields(
        arm_resource,
        canonical_type,
        catalog_cache=catalog_cache,
        sku_label_override=sku_label,
    )
    _upsert_resource(
        db,
        subscription_id,
        resource_id=rid,
        resource_name=arm_resource.get("name", ""),
        resource_type=canonical_type,
        resource_group=_extract_rg(rid),
        location=arm_resource.get("location"),
        sku=sku_str,
        sku_json=sku_payload,
        state=state,
        tags=arm_resource.get("tags", {}),
        properties=props,
        monthly_cost=monthly_cost,
    )


def _extract_rg(resource_id: str) -> Optional[str]:
    """Parse resource group from ARM resource ID."""
    try:
        parts = resource_id.split("/")
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except Exception:
        return None


def _normalize_aks_pools(pools: list | None) -> list:
    """Normalize agent pool list entries to ManagedCluster agentPoolProfiles shape."""
    normalized = []
    for pool in pools or []:
        if pool.get("count") is not None or pool.get("vmSize"):
            normalized.append(pool)
            continue
        props = pool.get("properties") or {}
        normalized.append({
            "name": pool.get("name"),
            "count": props.get("count") or 0,
            "vmSize": props.get("vmSize"),
            "mode": props.get("mode"),
            "osType": props.get("osType"),
        })
    return normalized


def _aks_properties(cluster: dict, pools: list | None = None) -> dict:
    props = cluster.get("properties") or {}
    agent_pools = _normalize_aks_pools(pools or props.get("agentPoolProfiles") or [])
    return {
        "kubernetesVersion": props.get("kubernetesVersion"),
        "agentPoolProfiles": agent_pools,
        "powerState": props.get("powerState"),
        "networkProfile": props.get("networkProfile"),
        "provisioningState": props.get("provisioningState"),
    }


def _vm_power_state(vm: dict) -> str | None:
    """Power state (Running/Stopped/Deallocated/…) from the VM instanceView."""
    iv = (vm.get("properties") or {}).get("instanceView") or {}
    for status in iv.get("statuses") or []:
        code = status.get("code") or ""
        if code.startswith("PowerState/"):
            return code.split("/", 1)[1]  # PowerState/running -> running (UI capitalizes)
    return None


def enrich_aks_arm_clusters(client: AzureResourcesClient, subscription_id: str, clusters: list) -> list:
    """Ensure live AKS list responses include node pools and stable resource IDs."""
    enriched = []
    for c in clusters or []:
        rid = (c.get("id") or "").strip()
        rg = _extract_rg(rid)
        cname = c.get("name", "")
        if not rid and rg and cname:
            rid = (
                f"/subscriptions/{subscription_id}/resourceGroups/{rg}"
                f"/providers/Microsoft.ContainerService/managedClusters/{cname}"
            )
            c = {**c, "id": rid}
        props = c.get("properties") or {}
        pools = _normalize_aks_pools(props.get("agentPoolProfiles") or [])
        if rg and cname and not pools:
            try:
                pools = _normalize_aks_pools(
                    client.list_aks_node_pools(subscription_id, rg, cname),
                )
            except Exception as pool_exc:
                log.debug("live AKS pool fetch failed for %s: %s", cname, pool_exc)
        c = {
            **c,
            "properties": _aks_properties(c, pools),
        }
        enriched.append(c)
    return enriched


def _collect_arm_ids(items: list) -> set[str]:
    """Normalize ARM resource IDs from Azure list responses."""
    from app.focus_mapping import normalize_arm_id

    ids: set[str] = set()
    for item in items or []:
        rid = normalize_arm_id((item.get("id") or "").strip())
        if rid:
            ids.add(rid)
    return ids


def _resolve_findings_for_missing_resources(
    db: Session,
    subscription_id: str,
    resource_ids: set[str],
) -> int:
    """Close open findings for resources removed from Azure inventory."""
    from app.focus_mapping import normalize_arm_id

    if not resource_ids:
        return 0
    subscription_id = subscription_id.lower()
    normalized = {normalize_arm_id(rid) for rid in resource_ids if rid}
    rows = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == subscription_id,
            OptimizationFinding.status == "open",
        )
        .all()
    )
    now = _now()
    resolved = 0
    for row in rows:
        rid = normalize_arm_id(row.resource_id or "")
        if rid and rid in normalized:
            row.status = "resolved"
            row.resolved_at = now
            resolved += 1
    return resolved


def _deactivate_missing_resources(
    db: Session,
    subscription_id: str,
    resource_type: str,
    present_ids: set[str],
) -> int:
    """Mark active snapshots of this type that Azure no longer returns as inactive."""
    from app.focus_mapping import normalize_arm_id

    subscription_id = subscription_id.lower()
    present = {normalize_arm_id(rid) for rid in present_ids if rid}
    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == subscription_id,
            ResourceSnapshot.resource_type == resource_type,
            ResourceSnapshot.is_active.is_(True),
        )
        .all()
    )
    removed_ids: set[str] = set()
    deactivated = 0
    for row in rows:
        rid = normalize_arm_id(row.resource_id or "")
        if not rid or rid in present:
            continue
        row.is_active = False
        removed_ids.add(rid)
        deactivated += 1
    if removed_ids:
        findings_closed = _resolve_findings_for_missing_resources(
            db, subscription_id, removed_ids,
        )
        log.info(
            "sync.deactivated_missing",
            subscription_id=subscription_id,
            resource_type=resource_type,
            resources=deactivated,
            findings_resolved=findings_closed,
        )
    return deactivated


def deactivate_inventory_resources_not_found(
    db: Session,
    resource_ids: set[str] | list[str],
    *,
    source: str = "arm_probe",
) -> int:
    """Mark inventory rows inactive when ARM confirms the resource no longer exists."""
    from app.focus_mapping import normalize_arm_id

    targets = {normalize_arm_id(rid) for rid in resource_ids if rid}
    if not targets:
        return 0

    by_subscription: dict[str, set[str]] = {}
    deactivated = 0
    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.resource_id.in_(list(targets)),
        )
        .all()
    )
    for row in rows:
        rid = normalize_arm_id(row.resource_id or "")
        row.is_active = False
        deactivated += 1
        sub = (row.subscription_id or "").strip().lower()
        if sub and rid:
            by_subscription.setdefault(sub, set()).add(rid)

    if deactivated:
        findings_closed = 0
        for sub, ids in by_subscription.items():
            findings_closed += _resolve_findings_for_missing_resources(db, sub, ids)
        log.info(
            "inventory.deactivated_not_found",
            source=source,
            resources=deactivated,
            findings_resolved=findings_closed,
        )
    return deactivated


def _record_type_sync(
    synced_ids: dict[str, set[str]],
    successful_types: set[str],
    canonical_type: str,
    items: list,
) -> None:
    successful_types.add(canonical_type)
    synced_ids[canonical_type] = _collect_arm_ids(items)


def _prune_stale_resources(
    db: Session,
    subscription_id: str,
    synced_ids: dict[str, set[str]],
    successful_types: set[str],
) -> dict[str, int]:
    """Deactivate DB rows for resource types successfully synced but absent from Azure."""
    removed_by_type: dict[str, int] = {}
    for canonical in successful_types:
        removed = _deactivate_missing_resources(
            db,
            subscription_id,
            canonical,
            synced_ids.get(canonical, set()),
        )
        if removed:
            removed_by_type[canonical] = removed
    return removed_by_type


def _dedupe_resource_snapshots(db: Session, subscription_id: str) -> int:
    """Deactivate duplicate active rows (same ARM ID or same type+name+RG)."""
    subscription_id = subscription_id.lower()
    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == subscription_id,
            ResourceSnapshot.is_active.is_(True),
        )
        .order_by(ResourceSnapshot.synced_at.desc())
        .all()
    )
    seen_ids: set[str] = set()
    seen_logical: set[str] = set()
    deactivated = 0
    for row in rows:
        rid = (row.resource_id or "").strip().lower()
        logical = (
            f"{row.resource_type}|{(row.resource_name or '').strip().lower()}"
            f"|{(row.resource_group or '').strip().lower()}"
        )
        duplicate = False
        if rid:
            if rid in seen_ids:
                duplicate = True
            else:
                seen_ids.add(rid)
        if logical.strip("|") and logical in seen_logical:
            duplicate = True
        elif logical.strip("|"):
            seen_logical.add(logical)

        if duplicate:
            row.is_active = False
            deactivated += 1
    return deactivated


def _deactivate_scale_set_vm_rows(db: Session, subscription_id: str) -> int:
    """Hide VMSS instance VMs that were previously stored as compute/vm."""
    subscription_id = subscription_id.lower()
    deactivated = 0
    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == subscription_id,
            ResourceSnapshot.resource_type == "compute/vm",
            ResourceSnapshot.is_active.is_(True),
        )
        .all()
    )
    for row in rows:
        try:
            props = json.loads(row.properties_json or "{}")
        except Exception:
            props = {}
        pseudo = {"id": row.resource_id, "properties": props}
        if is_scale_set_instance(pseudo):
            row.is_active = False
            deactivated += 1
    if deactivated:
        log.info("deactivated_vmss_instance_vms", count=deactivated, subscription_id=subscription_id)
    return deactivated


def _sync_generic_arm_resources(
    client: AzureResourcesClient,
    db: Session,
    subscription_id: str,
    counts: dict,
    types_set: set[str] | None = None,
    *,
    catalog_cache: VmSkuCatalogCache | None = None,
    synced_ids: dict[str, set[str]] | None = None,
    successful_types: set[str] | None = None,
) -> None:
    """Sync extended resource types via the generic ARM resources list API."""
    for arm_type, canonical in generic_arm_sync_types():
        if canonical in _DEDICATED_TYPED_SYNC_CANONICALS:
            continue
        if types_set is not None and canonical not in types_set:
            continue
        spec = get_technical_fetch_spec(canonical)
        try:
            items = client.list_resources(subscription_id, arm_type)
            items = enrich_arm_resources_for_type(client, subscription_id, items, canonical)
            for item in items:
                props = item.get("properties") or {}
                item["_sync_props"] = pick_sync_properties(item, spec)
                item["_sync_state"] = props.get("provisioningState") or props.get("state")
            _bulk_upsert_arm_list(
                db,
                subscription_id,
                items,
                canonical,
                catalog_cache=catalog_cache,
                state_fn=lambda i: i.get("_sync_state"),
                properties_fn=lambda i: i.get("_sync_props") or {},
            )
            counts[canonical] = counts.get(canonical, 0) + len(items)
            if synced_ids is not None and successful_types is not None:
                _record_type_sync(synced_ids, successful_types, canonical, items)
        except Exception as exc:
            log.warning("sync generic ARM type %s failed: %s", arm_type, exc)


def sync_resources(
    subscription_id: str,
    db: Session,
    token: str,
    types: list[str] | None = None,
) -> dict:
    """
    Fetch resource types from Azure ARM and upsert into resource_snapshots.
    When types is set, only those canonical types are synced (scoped sync).
    Returns a summary dict of counts per category.
    """
    types_set = normalize_sync_types(types)

    def want(canonical: str) -> bool:
        return types_set is None or canonical in types_set

    from app.auth import arm_auth_context

    with arm_auth_context(db=db, token=token):
        return _sync_resources_inner(
            subscription_id,
            db,
            types_set=types_set,
            want=want,
        )


def _sync_resources_inner(
    subscription_id: str,
    db: Session,
    *,
    types_set: set[str] | None,
    want,
) -> dict:
    client = AzureResourcesClient(db=db)
    counts = {}
    synced_ids: dict[str, set[str]] = {}
    successful_types: set[str] = set()

    def _enriched(items: list, canonical: str) -> list:
        return enrich_arm_resources_for_type(client, subscription_id, items, canonical)

    with arm_patient_sync():
        catalog_cache = VmSkuCatalogCache(client, subscription_id)

        compute_fetch_specs: list[tuple[str, Any]] = []
        if want("compute/vm"):
            compute_fetch_specs.append((
                "compute/vm",
                lambda: filter_standalone_vms(
                    _enriched(client.list_vms(subscription_id, include_instance_view=True), "compute/vm"),
                ),
            ))
        if want("compute/disk"):
            compute_fetch_specs.append((
                "compute/disk",
                lambda: _enriched(client.list_disks(subscription_id), "compute/disk"),
            ))
        if want("compute/snapshot"):
            compute_fetch_specs.append((
                "compute/snapshot",
                lambda: _enriched(client.list_snapshots(subscription_id), "compute/snapshot"),
            ))
        if len(compute_fetch_specs) > 1:
            compute_fetched = parallel_fetch(compute_fetch_specs)
        else:
            compute_fetched = {k: fn() for k, fn in compute_fetch_specs}

        arm_prefetch_raw = fetch_arm_lists_parallel(client, subscription_id, want)
        arm_prefetch = {
            canonical: _enriched(items, canonical)
            for canonical, items in arm_prefetch_raw.items()
        }

        if want("compute/vm"):
            try:
                vms = compute_fetched.get("compute/vm", [])
                for vm in vms:
                    power_state = _vm_power_state(vm)
                    vm_spec = get_technical_fetch_spec("compute/vm")
                    vm_props = pick_sync_properties(vm, vm_spec)
                    if power_state:
                        vm_props["powerState"] = power_state
                    vm["properties"] = vm_props
                    vm["_sync_state"] = power_state or vm.get("properties", {}).get("provisioningState")
                _bulk_upsert_arm_list(
                    db,
                    subscription_id,
                    vms,
                    "compute/vm",
                    catalog_cache=catalog_cache,
                    state_fn=lambda vm: vm.get("_sync_state"),
                    properties_fn=lambda vm: vm.get("properties") or {},
                )
                counts["compute/vm"] = len(vms)
                _record_type_sync(synced_ids, successful_types, "compute/vm", vms)
                _deactivate_scale_set_vm_rows(db, subscription_id)
            except Exception as e:
                log.warning("sync VMs failed: %s", e)

        if want("compute/vmss"):
            try:
                scale_sets = arm_prefetch.get("compute/vmss", [])
                scale_sets = enrich_vmss_list_with_instance_uptime(
                    client, subscription_id, scale_sets,
                )
                vmss_spec = get_technical_fetch_spec("compute/vmss")
                for item in scale_sets:
                    props = item.get("properties") or {}
                    vmss_props = pick_sync_properties(item, vmss_spec)
                    for key in (
                        "oldest_instance_time_created",
                        "newest_instance_time_created",
                        "vmss_instance_count",
                        "vmss_instances_with_time",
                    ):
                        if props.get(key) is not None:
                            vmss_props[key] = props[key]
                    item["_sync_state"] = props.get("provisioningState")
                    item["_sync_props"] = vmss_props
                _bulk_upsert_arm_list(
                    db,
                    subscription_id,
                    scale_sets,
                    "compute/vmss",
                    catalog_cache=catalog_cache,
                    state_fn=lambda i: i.get("_sync_state"),
                    properties_fn=lambda i: i.get("_sync_props") or {},
                )
                counts["compute/vmss"] = len(scale_sets)
                _record_type_sync(synced_ids, successful_types, "compute/vmss", scale_sets)
            except Exception as e:
                log.warning("sync VMSS failed: %s", e)

        if want("compute/disk"):
            try:
                disks = compute_fetched.get("compute/disk", [])
                for d in disks:
                    disk_spec = get_technical_fetch_spec("compute/disk")
                    d["_sync_props"] = enrich_disk_sync_properties(
                        db,
                        subscription_id,
                        d,
                        pick_sync_properties(d, disk_spec),
                    )
                _bulk_upsert_arm_list(
                    db,
                    subscription_id,
                    disks,
                    "compute/disk",
                    catalog_cache=catalog_cache,
                    state_fn=lambda d: d.get("properties", {}).get("diskState"),
                    properties_fn=lambda d: d.get("_sync_props") or {},
                )
                counts["compute/disk"] = len(disks)
                _record_type_sync(synced_ids, successful_types, "compute/disk", disks)
            except Exception as e:
                log.warning("sync Disks failed: %s", e)

        if want("compute/snapshot"):
            try:
                snapshots = compute_fetched.get("compute/snapshot", [])
                _bulk_upsert_arm_list(
                    db,
                    subscription_id,
                    snapshots,
                    "compute/snapshot",
                    catalog_cache=catalog_cache,
                    state_fn=lambda snap: (snap.get("properties") or {}).get("diskState")
                    or (snap.get("properties") or {}).get("provisioningState"),
                )
                counts["compute/snapshot"] = len(snapshots)
                _record_type_sync(synced_ids, successful_types, "compute/snapshot", snapshots)
            except Exception as e:
                log.warning("sync Snapshots failed: %s", e)

        if want("containers/aks"):
            try:
                clusters = arm_prefetch.get("containers/aks", [])
                for c in clusters:
                    rid = (c.get("id") or "").strip()
                    rg = _extract_rg(rid)
                    cname = c.get("name", "")
                    if not rid and rg and cname:
                        rid = (
                            f"/subscriptions/{subscription_id}/resourceGroups/{rg}"
                            f"/providers/Microsoft.ContainerService/managedClusters/{cname}"
                        )
                    props = c.get("properties") or {}
                    pools = _normalize_aks_pools(props.get("agentPoolProfiles") or [])
                    if rg and cname and not pools:
                        try:
                            pools = _normalize_aks_pools(
                                client.list_aks_node_pools(subscription_id, rg, cname),
                            )
                        except Exception as pool_exc:
                            log.debug("AKS node pool fetch failed for %s: %s", cname, pool_exc)
                    power_state = props.get("powerState") or {}
                    provisioning = props.get("provisioningState")
                    display_state = power_state.get("code") or provisioning
                    c["_sync_state"] = display_state
                    c["_sync_props"] = _aks_properties(c, pools)
                _bulk_upsert_arm_list(
                    db,
                    subscription_id,
                    clusters,
                    "containers/aks",
                    catalog_cache=catalog_cache,
                    state_fn=lambda i: i.get("_sync_state"),
                    properties_fn=lambda i: i.get("_sync_props") or {},
                )
                counts["containers/aks"] = len(clusters)
                _record_type_sync(synced_ids, successful_types, "containers/aks", clusters)
            except Exception as e:
                log.warning("sync AKS failed: %s", e)

        if want("storage/account"):
            try:
                accounts = arm_prefetch.get("storage/account", [])
                storage_spec = get_technical_fetch_spec("storage/account")
                for s in accounts:
                    props = s.get("properties") or {}
                    s["_sync_state"] = props.get("accessTier") or props.get("provisioningState")
                    s["_sync_props"] = pick_sync_properties(s, storage_spec)
                _bulk_upsert_arm_list(
                    db, subscription_id, accounts, "storage/account",
                    catalog_cache=catalog_cache,
                    state_fn=lambda i: i.get("_sync_state"),
                    properties_fn=lambda i: i.get("_sync_props") or {},
                )
                counts["storage/account"] = len(accounts)
                _record_type_sync(synced_ids, successful_types, "storage/account", accounts)
            except Exception as e:
                log.warning("sync Storage failed: %s", e)

        if want("network/publicip"):
            try:
                ips = arm_prefetch.get("network/publicip", [])
                ip_spec = get_technical_fetch_spec("network/publicip")
                for ip in ips:
                    props = ip.get("properties") or {}
                    ip_cfg = props.get("ipConfiguration")
                    ip["_sync_state"] = "unassociated" if not ip_cfg else props.get("provisioningState")
                    ip["_sync_props"] = pick_sync_properties(ip, ip_spec)
                _bulk_upsert_arm_list(
                    db, subscription_id, ips, "network/publicip",
                    catalog_cache=catalog_cache,
                    state_fn=lambda i: i.get("_sync_state"),
                    properties_fn=lambda i: i.get("_sync_props") or {},
                )
                counts["network/publicip"] = len(ips)
                _record_type_sync(synced_ids, successful_types, "network/publicip", ips)
            except Exception as e:
                log.warning("sync Public IPs failed: %s", e)

        if want("database/sql"):
            try:
                servers = arm_prefetch.get("database/sql", [])
                _bulk_sync_pick_properties(
                    db, subscription_id, servers, "database/sql", catalog_cache,
                    state_fn=lambda i: i.get("properties", {}).get("state"),
                )
                counts["database/sql"] = len(servers)
                _record_type_sync(synced_ids, successful_types, "database/sql", servers)
            except Exception as e:
                log.warning("sync SQL failed: %s", e)

        if want("security/keyvault"):
            try:
                vaults = arm_prefetch.get("security/keyvault", [])
                _bulk_sync_pick_properties(
                    db, subscription_id, vaults, "security/keyvault", catalog_cache,
                    state_fn=lambda i: i.get("properties", {}).get("provisioningState"),
                )
                counts["security/keyvault"] = len(vaults)
                _record_type_sync(synced_ids, successful_types, "security/keyvault", vaults)
            except Exception as e:
                log.warning("sync Key Vaults failed: %s", e)

        if want("appservice/webapp"):
            try:
                apps = arm_prefetch.get("appservice/webapp", [])
                plan_sku_index = build_app_service_plan_sku_index(
                    arm_prefetch.get("appservice/plan", []),
                )
                app_spec = get_technical_fetch_spec("appservice/webapp")
                for a in apps:
                    a["_sync_state"] = a.get("properties", {}).get("state")
                    a["_sync_props"] = pick_sync_properties(a, app_spec)
                    plan_id = (a.get("properties", {}).get("serverFarmId") or "").strip().lower()
                    a["_plan_sku"] = plan_sku_index.get(plan_id)
                _bulk_upsert_arm_list(
                    db, subscription_id, apps, "appservice/webapp",
                    catalog_cache=catalog_cache,
                    state_fn=lambda i: i.get("_sync_state"),
                    properties_fn=lambda i: i.get("_sync_props") or {},
                    sku_label_fn=lambda i: format_app_service_webapp_label(
                        i.get("properties") or {},
                        plan_sku=i.get("_plan_sku"),
                    ),
                )
                counts["appservice/webapp"] = len(apps)
                _record_type_sync(synced_ids, successful_types, "appservice/webapp", apps)
            except Exception as e:
                log.warning("sync App Services failed: %s", e)

        if want("appservice/plan"):
            try:
                plans = arm_prefetch.get("appservice/plan", [])
                _bulk_sync_pick_properties(
                    db, subscription_id, plans, "appservice/plan", catalog_cache,
                    state_fn=lambda i: (i.get("properties") or {}).get("status")
                    or (i.get("properties") or {}).get("provisioningState"),
                )
                counts["appservice/plan"] = len(plans)
                _record_type_sync(synced_ids, successful_types, "appservice/plan", plans)
            except Exception as e:
                log.warning("sync App Service Plans failed: %s", e)

        if want("network/loadbalancer"):
            try:
                lbs = arm_prefetch.get("network/loadbalancer", [])
                _bulk_sync_pick_properties(
                    db, subscription_id, lbs, "network/loadbalancer", catalog_cache,
                    state_fn=lambda i: i.get("properties", {}).get("provisioningState"),
                )
                counts["network/loadbalancer"] = len(lbs)
                _record_type_sync(synced_ids, successful_types, "network/loadbalancer", lbs)
            except Exception as e:
                log.warning("sync Load Balancers failed: %s", e)

        if want("network/appgateway"):
            try:
                agws = arm_prefetch.get("network/appgateway", [])
                _bulk_sync_pick_properties(
                    db, subscription_id, agws, "network/appgateway", catalog_cache,
                    state_fn=lambda i: i.get("properties", {}).get("provisioningState"),
                )
                counts["network/appgateway"] = len(agws)
                _record_type_sync(synced_ids, successful_types, "network/appgateway", agws)
            except Exception as e:
                log.warning("sync App Gateways failed: %s", e)

        if want("network/nsg"):
            try:
                nsgs = arm_prefetch.get("network/nsg", [])
                _bulk_sync_pick_properties(
                    db, subscription_id, nsgs, "network/nsg", catalog_cache,
                    state_fn=lambda i: i.get("properties", {}).get("provisioningState"),
                )
                counts["network/nsg"] = len(nsgs)
                _record_type_sync(synced_ids, successful_types, "network/nsg", nsgs)
            except Exception as e:
                log.warning("sync NSGs failed: %s", e)

        if want("network/nic"):
            try:
                nics = arm_prefetch.get("network/nic", [])
                nic_spec = get_technical_fetch_spec("network/nic")
                for nic in nics:
                    props = nic.get("properties") or {}
                    vm_ref = props.get("virtualMachine")
                    nic["_sync_state"] = "unattached" if not vm_ref else props.get("provisioningState")
                    nic["_sync_props"] = pick_sync_properties(nic, nic_spec)
                _bulk_upsert_arm_list(
                    db, subscription_id, nics, "network/nic",
                    catalog_cache=catalog_cache,
                    state_fn=lambda i: i.get("_sync_state"),
                    properties_fn=lambda i: i.get("_sync_props") or {},
                )
                counts["network/nic"] = len(nics)
                _record_type_sync(synced_ids, successful_types, "network/nic", nics)
            except Exception as e:
                log.warning("sync NICs failed: %s", e)

        if want("network/nat"):
            try:
                nat_gws = arm_prefetch.get("network/nat", [])
                nat_spec = get_technical_fetch_spec("network/nat")
                for nat in nat_gws:
                    props = nat.get("properties") or {}
                    subnets = props.get("subnets") or []
                    nat["_sync_state"] = "idle" if not subnets else props.get("provisioningState")
                    nat["_sync_props"] = pick_sync_properties(nat, nat_spec)
                _bulk_upsert_arm_list(
                    db, subscription_id, nat_gws, "network/nat",
                    catalog_cache=catalog_cache,
                    state_fn=lambda i: i.get("_sync_state"),
                    properties_fn=lambda i: i.get("_sync_props") or {},
                )
                counts["network/nat"] = len(nat_gws)
                _record_type_sync(synced_ids, successful_types, "network/nat", nat_gws)
            except Exception as e:
                log.warning("sync NAT Gateways failed: %s", e)

        if want("network/vnet"):
            try:
                vnets = arm_prefetch.get("network/vnet", [])
                _bulk_sync_pick_properties(
                    db, subscription_id, vnets, "network/vnet", catalog_cache,
                    state_fn=lambda i: i.get("properties", {}).get("provisioningState"),
                )
                counts["network/vnet"] = len(vnets)
                _record_type_sync(synced_ids, successful_types, "network/vnet", vnets)
            except Exception as e:
                log.warning("sync virtual networks failed: %s", e)

        if want("network/privateendpoint"):
            try:
                endpoints = arm_prefetch.get("network/privateendpoint", [])
                _bulk_sync_pick_properties(
                    db, subscription_id, endpoints, "network/privateendpoint", catalog_cache,
                    state_fn=lambda i: i.get("properties", {}).get("provisioningState"),
                )
                counts["network/privateendpoint"] = len(endpoints)
                _record_type_sync(synced_ids, successful_types, "network/privateendpoint", endpoints)
            except Exception as e:
                log.warning("sync private endpoints failed: %s", e)

        if want("network/privatelinkservice"):
            try:
                pls_list = arm_prefetch.get("network/privatelinkservice", [])
                _bulk_sync_pick_properties(
                    db, subscription_id, pls_list, "network/privatelinkservice", catalog_cache,
                    state_fn=lambda i: i.get("properties", {}).get("provisioningState"),
                )
                counts["network/privatelinkservice"] = len(pls_list)
                _record_type_sync(synced_ids, successful_types, "network/privatelinkservice", pls_list)
            except Exception as e:
                log.warning("sync private link services failed: %s", e)

        if want("network/privatedns"):
            try:
                dns_zones = arm_prefetch.get("network/privatedns", [])
                _bulk_sync_pick_properties(
                    db, subscription_id, dns_zones, "network/privatedns", catalog_cache,
                    state_fn=lambda i: i.get("properties", {}).get("provisioningState"),
                )
                counts["network/privatedns"] = len(dns_zones)
                _record_type_sync(synced_ids, successful_types, "network/privatedns", dns_zones)
            except Exception as e:
                log.warning("sync private DNS zones failed: %s", e)

        if want("database/cosmosdb"):
            try:
                cosmos = arm_prefetch.get("database/cosmosdb", [])
                _bulk_sync_pick_properties(
                    db, subscription_id, cosmos, "database/cosmosdb", catalog_cache,
                    state_fn=lambda i: i.get("properties", {}).get("provisioningState"),
                )
                counts["database/cosmosdb"] = len(cosmos)
                _record_type_sync(synced_ids, successful_types, "database/cosmosdb", cosmos)
            except Exception as e:
                log.warning("sync Cosmos DB failed: %s", e)

        if want("database/postgresql"):
            try:
                pg_servers = arm_prefetch.get("database/postgresql", [])
                _bulk_sync_pick_properties(
                    db, subscription_id, pg_servers, "database/postgresql", catalog_cache,
                    state_fn=lambda i: i.get("properties", {}).get("state"),
                )
                counts["database/postgresql"] = len(pg_servers)
                _record_type_sync(synced_ids, successful_types, "database/postgresql", pg_servers)
            except Exception as e:
                log.warning("sync PostgreSQL failed: %s", e)

        if want("database/redis"):
            try:
                redis_list = arm_prefetch.get("database/redis", [])
                _bulk_sync_pick_properties(
                    db, subscription_id, redis_list, "database/redis", catalog_cache,
                    state_fn=lambda i: (i.get("properties") or {}).get("provisioningState"),
                )
                counts["database/redis"] = len(redis_list)
                _record_type_sync(synced_ids, successful_types, "database/redis", redis_list)
            except Exception as e:
                log.warning("sync Redis failed: %s", e)

        if want("containers/acr"):
            try:
                registries = arm_prefetch.get("containers/acr", [])
                acr_spec = get_technical_fetch_spec("containers/acr")
                for reg in registries:
                    rid = reg.get("id") or ""
                    rg = _extract_rg(rid)
                    name = reg.get("name")
                    if rg and name:
                        try:
                            reps = client.list_acr_replications(subscription_id, rg, name)
                            props = reg.setdefault("properties", {})
                            props["_replications"] = reps
                            props["replicationCount"] = len(reps)
                        except Exception as rep_err:
                            log.debug("acr replications fetch failed for %s: %s", name, rep_err)
                    reg["_sync_state"] = reg.get("properties", {}).get("provisioningState")
                    reg["_sync_props"] = pick_sync_properties(reg, acr_spec)
                _bulk_upsert_arm_list(
                    db, subscription_id, registries, "containers/acr",
                    catalog_cache=catalog_cache,
                    state_fn=lambda i: i.get("_sync_state"),
                    properties_fn=lambda i: i.get("_sync_props") or {},
                )
                counts["containers/acr"] = len(registries)
                _record_type_sync(synced_ids, successful_types, "containers/acr", registries)
            except Exception as e:
                log.warning("sync ACR failed: %s", e)

        generic_canonicals = {c for _, c in generic_arm_sync_types()}
        if types_set is None or types_set & generic_canonicals:
            _sync_generic_arm_resources(
                client, db, subscription_id, counts, types_set=types_set, catalog_cache=catalog_cache,
                synced_ids=synced_ids, successful_types=successful_types,
            )

        removed_by_type = _prune_stale_resources(
            db, subscription_id, synced_ids, successful_types,
        )
        if removed_by_type:
            counts["removed"] = removed_by_type

        from app.resource_pricing import _dedupe_pending_pricing_profiles

        _dedupe_pending_pricing_profiles(db)

    db.commit()
    from app.perf_cache import invalidate_subscription
    invalidate_subscription(subscription_id.lower())
    return counts


def _upsert_cost_snapshot(
    db: Session,
    subscription_id: str,
    cost_date: str,
    resource_group: str,
    amounts: dict,
) -> None:
    rg = resource_group or ""
    existing = (
        db.query(CostSnapshot)
        .filter(
            CostSnapshot.subscription_id == subscription_id,
            CostSnapshot.cost_date == cost_date,
            CostSnapshot.granularity == "Daily",
            CostSnapshot.resource_group == (rg or None),
        )
        .first()
    )
    if existing:
        existing.cost_usd = amounts["usd"]
        existing.cost_billing = amounts["pretax"]
        existing.currency = amounts["currency"]
        existing.synced_at = _now()
        return
    db.add(CostSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=subscription_id,
        cost_date=cost_date,
        granularity="Daily",
        resource_group=rg or None,
        cost_usd=amounts["usd"],
        cost_billing=amounts["pretax"],
        currency=amounts["currency"],
    ))


def _upsert_daily_service_cost(
    db: Session,
    subscription_id: str,
    cost_date: str,
    service_name: str,
    amounts: dict,
) -> None:
    existing = (
        db.query(CostDailyByServiceSnapshot)
        .filter(
            CostDailyByServiceSnapshot.subscription_id == subscription_id,
            CostDailyByServiceSnapshot.cost_date == cost_date,
            CostDailyByServiceSnapshot.service_name == service_name,
        )
        .first()
    )
    if existing:
        existing.cost_usd = amounts["usd"]
        existing.cost_billing = amounts["pretax"]
        existing.billing_currency = amounts["currency"]
        existing.synced_at = _now()
        return
    db.add(CostDailyByServiceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=subscription_id,
        cost_date=cost_date,
        service_name=service_name,
        cost_usd=amounts["usd"],
        cost_billing=amounts["pretax"],
        billing_currency=amounts["currency"],
    ))


def sync_cost_snapshots(subscription_id: str, db: Session, rows: list[dict] | None = None) -> dict:
    """Persist daily cost roll-ups by resource group and by service from blob export rows."""
    subscription_id = subscription_id.lower()
    if rows is None:
        rows = cost_export.load_rows(subscription_id)
    if not rows:
        log.warning("cost_sync.daily_snapshots_empty", subscription_id=subscription_id)
        return {"daily_by_rg": 0, "daily_by_service": 0}

    log.info("cost_sync.daily_snapshots_start", subscription_id=subscription_id, blob_rows=len(rows))

    by_rg: dict[tuple[str, str], dict] = {}
    by_svc: dict[tuple[str, str], dict] = {}

    for row in rows:
        cost_date = (row.get("date") or "").strip()[:10]
        if not cost_date:
            continue
        currency = row.get("currency") or "USD"
        pretax = float(row.get("cost") or 0.0)
        usd = float(row.get("cost_usd") or pretax)

        rg_key = (cost_date, row.get("resource_group") or "")
        rg_bucket = by_rg.setdefault(rg_key, {"pretax": 0.0, "usd": 0.0, "currency": currency})
        rg_bucket["pretax"] += pretax
        rg_bucket["usd"] += usd
        if currency:
            rg_bucket["currency"] = currency

        svc_name = row.get("service_name") or "Other"
        svc_key = (cost_date, svc_name)
        svc_bucket = by_svc.setdefault(svc_key, {"pretax": 0.0, "usd": 0.0, "currency": currency})
        svc_bucket["pretax"] += pretax
        svc_bucket["usd"] += usd
        if currency:
            svc_bucket["currency"] = currency

    return _persist_daily_aggregates(db, subscription_id, by_rg, by_svc)


def sync_cost_snapshots_from_parsed(
    subscription_id: str,
    db: Session,
    parsed: cost_export.ParsedCostExport,
) -> dict:
    """Persist pre-aggregated daily roll-ups from a streaming parse."""
    subscription_id = subscription_id.lower()
    if not parsed.daily_by_rg and not parsed.daily_by_service:
        log.warning("cost_sync.daily_snapshots_empty", subscription_id=subscription_id)
        return {"daily_by_rg": 0, "daily_by_service": 0}
    log.info(
        "cost_sync.daily_snapshots_start",
        subscription_id=subscription_id,
        daily_by_rg=len(parsed.daily_by_rg),
        daily_by_service=len(parsed.daily_by_service),
    )
    return _persist_daily_aggregates(
        db,
        subscription_id,
        parsed.daily_by_rg,
        parsed.daily_by_service,
    )


def _persist_daily_aggregates(
    db: Session,
    subscription_id: str,
    by_rg: dict[tuple[str, str], dict],
    by_svc: dict[tuple[str, str], dict],
) -> dict:
    for (cost_date, resource_group), amounts in by_rg.items():
        _upsert_cost_snapshot(db, subscription_id, cost_date, resource_group, amounts)
    for (cost_date, service_name), amounts in by_svc.items():
        _upsert_daily_service_cost(db, subscription_id, cost_date, service_name, amounts)

    db.commit()
    log.info(
        "cost_sync.daily_snapshots_done",
        subscription_id=subscription_id,
        daily_by_rg=len(by_rg),
        daily_by_service=len(by_svc),
    )
    return {"daily_by_rg": len(by_rg), "daily_by_service": len(by_svc)}


def sync_resource_costs(subscription_id: str, db: Session, rows: list[dict] | None = None) -> int:
    """Update resource_snapshots cost columns from blob export (current month MTD)."""
    subscription_id = subscription_id.lower()
    if rows is None:
        rows = cost_export.load_rows(subscription_id)
    mtd_rows, _month, _mtd_start, _mtd_end = cost_export.resolve_mtd_rows(rows)
    try:
        raw = cost_export.by_resource_response(mtd_rows)
        cost_details = parse_cost_by_resource_details(raw)
    except Exception as e:
        log.warning("cost_sync.resource_costs_failed", subscription_id=subscription_id, error=str(e))
        return 0
    return sync_resource_costs_from_details(subscription_id, db, cost_details)


def sync_resource_costs_from_details(
    subscription_id: str,
    db: Session,
    cost_details: dict[str, dict],
) -> int:
    """Apply per-resource MTD costs from blob CSV ResourceId aggregates to resource_snapshots."""
    from app.focus_mapping import normalize_arm_id

    subscription_id = subscription_id.lower()
    normalized: dict[str, dict] = {}
    for key, detail in cost_details.items():
        nk = normalize_arm_id(key)
        if nk:
            normalized[nk] = detail

    updated = 0
    matched = 0
    now = _now()
    q = (
        db.query(ResourceSnapshot)
        .filter(ResourceSnapshot.subscription_id == subscription_id)
        .yield_per(500)
    )
    for row in q:
        detail = normalized.get(normalize_arm_id(row.resource_id or ""), {})
        billing = float(detail.get("pretax") or 0.0)
        usd = float(detail.get("usd") or 0.0)
        if billing > 0 or usd > 0:
            matched += 1
        row.monthly_cost_billing = billing
        row.monthly_cost_usd = usd
        row.billing_currency = detail.get("currency") or row.billing_currency or "USD"
        service = detail.get("service_name")
        if service:
            row.azure_service_name = service
        row.synced_at = now
        updated += 1
    db.commit()
    log.info(
        "cost_sync.resource_costs_done",
        subscription_id=subscription_id,
        resources_in_db=updated,
        resources_with_cost=matched,
        csv_resource_ids=len(normalized),
    )
    return matched


def deactivate_cost_export_only_snapshots(subscription_id: str, db: Session) -> int:
    """Deactivate snapshots that were created from cost export only (not Azure inventory)."""
    subscription_id = subscription_id.lower()
    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == subscription_id,
            ResourceSnapshot.is_active.is_(True),
        )
        .all()
    )
    deactivated = 0
    for row in rows:
        try:
            props = json.loads(row.properties_json or "{}")
        except Exception:
            props = {}
        if props.get("source") != "cost_export":
            continue
        row.is_active = False
        deactivated += 1
    if deactivated:
        db.commit()
        log.info(
            "cost_sync.deactivated_export_only",
            subscription_id=subscription_id,
            deactivated=deactivated,
        )
    return deactivated


def sync_cost_discovered_resources(
    subscription_id: str,
    db: Session,
    by_resource: dict[str, dict],
) -> int:
    """Create resource_snapshots for ARM ResourceIds in the cost export missing from inventory."""
    from app.focus_mapping import normalize_arm_id
    from app.resource_type_map import (
        extract_rg_from_arm,
        internal_resource_type,
        resource_name_from_arm_id,
    )

    subscription_id = subscription_id.lower()
    existing_ids = {
        normalize_arm_id(rid)
        for (rid,) in db.query(ResourceSnapshot.resource_id)
        .filter(ResourceSnapshot.subscription_id == subscription_id)
        .all()
        if rid
    }
    created = 0
    now = _now()
    for rid, amounts in by_resource.items():
        resource_id = normalize_arm_id(rid)
        if not resource_id or resource_id in existing_ids:
            continue
        pretax = float(amounts.get("pretax") or 0.0)
        usd = float(amounts.get("usd") or 0.0)
        if pretax <= 0 and usd <= 0:
            continue
        internal_type = internal_resource_type(
            resource_id,
            amounts.get("resource_type") or "",
            amounts.get("service_name") or "",
        )
        name = resource_name_from_arm_id(resource_id) or resource_id.rsplit("/", 1)[-1]
        rg = amounts.get("resource_group") or extract_rg_from_arm(resource_id)
        db.add(ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=subscription_id,
            resource_id=resource_id,
            resource_name=name,
            resource_type=internal_type,
            resource_group=rg or None,
            azure_service_name=amounts.get("service_name") or "Other",
            monthly_cost_billing=pretax,
            monthly_cost_usd=usd,
            billing_currency=amounts.get("currency") or "USD",
            is_active=True,
            synced_at=now,
            properties_json=json.dumps({"source": "cost_export"}),
            tags_json="{}",
        ))
        existing_ids.add(resource_id)
        created += 1
    if created:
        db.commit()
    log.info(
        "cost_sync.discovered_resources_done",
        subscription_id=subscription_id,
        created=created,
        csv_resource_ids=len(by_resource),
    )
    return created


def sync_resource_costs_from_cost_table(
    subscription_id: str,
    db: Session,
    month: str | None = None,
) -> int:
    """Update resource_snapshots from persisted cost_by_resource rows."""
    from app.cost_db import resource_cost_map_from_db

    cost_details = resource_cost_map_from_db(db, subscription_id, "MonthToDate", month=month)
    if not cost_details:
        return 0
    return sync_resource_costs_from_details(subscription_id, db, cost_details)


def _cost_details_from_resource_agg(by_resource: dict[str, dict]) -> dict[str, dict]:
    from app.focus_mapping import normalize_arm_id

    out: dict[str, dict] = {}
    for rid, amounts in by_resource.items():
        key = normalize_arm_id(rid)
        if not key:
            continue
        out[key] = {
            "pretax": float(amounts.get("pretax") or 0.0),
            "usd": float(amounts.get("usd") or 0.0),
            "currency": amounts.get("currency") or "USD",
            "service_name": amounts.get("service_name") or "Other",
        }
    return out


def _persist_mtd_by_service_agg(
    db: Session,
    subscription_id: str,
    month: str,
    by_service: dict[str, dict],
) -> int:
    written = 0
    for svc, amounts in by_service.items():
        pretax = float(amounts.get("pretax") or 0.0)
        usd = float(amounts.get("usd") or 0.0)
        currency = str(amounts.get("currency") or "CAD")
        existing = (
            db.query(CostByServiceSnapshot)
            .filter(
                CostByServiceSnapshot.subscription_id == subscription_id,
                CostByServiceSnapshot.service_name == svc,
                CostByServiceSnapshot.month == month,
            )
            .first()
        )
        if existing:
            existing.cost_usd = usd
            existing.cost_billing = pretax
            existing.billing_currency = currency
            existing.synced_at = _now()
        else:
            db.add(CostByServiceSnapshot(
                id=str(uuid.uuid4()),
                subscription_id=subscription_id,
                service_name=svc,
                month=month,
                cost_usd=usd,
                cost_billing=pretax,
                billing_currency=currency,
            ))
        written += 1
    return written


def _replace_mtd_by_service_agg(
    db: Session,
    subscription_id: str,
    month: str,
    by_service: dict[str, dict],
) -> int:
    """Replace all MTD per-service rows for the month (drops stale buckets like Other)."""
    db.query(CostByServiceSnapshot).filter(
        CostByServiceSnapshot.subscription_id == subscription_id,
        CostByServiceSnapshot.month == month,
    ).delete(synchronize_session=False)
    return _persist_mtd_by_service_agg(db, subscription_id, month, by_service)


def _replace_mtd_by_resource_agg(
    db: Session,
    subscription_id: str,
    month: str,
    by_resource: dict[str, dict],
) -> int:
    """Replace all MTD per-resource rows for the month."""
    db.query(CostByResourceSnapshot).filter(
        CostByResourceSnapshot.subscription_id == subscription_id,
        CostByResourceSnapshot.month == month,
    ).delete(synchronize_session=False)
    return _persist_mtd_by_resource_agg(db, subscription_id, month, by_resource)


def _persist_mtd_by_resource_agg(
    db: Session,
    subscription_id: str,
    month: str,
    by_resource: dict[str, dict],
) -> int:
    from app.focus_mapping import normalize_arm_id

    written = 0
    for rid, amounts in by_resource.items():
        resource_id = normalize_arm_id(rid)
        if not resource_id:
            continue
        pretax = float(amounts.get("pretax") or 0.0)
        usd = float(amounts.get("usd") or 0.0)
        currency = str(amounts.get("currency") or "CAD")
        service_name = amounts.get("service_name") or "Other"
        resource_group = amounts.get("resource_group") or ""
        resource_type = amounts.get("resource_type") or ""
        existing = (
            db.query(CostByResourceSnapshot)
            .filter(
                CostByResourceSnapshot.subscription_id == subscription_id,
                CostByResourceSnapshot.resource_id == resource_id,
                CostByResourceSnapshot.month == month,
            )
            .first()
        )
        if existing:
            existing.service_name = service_name
            existing.resource_group = resource_group or None
            existing.resource_type = resource_type or None
            existing.cost_usd = usd
            existing.cost_billing = pretax
            existing.billing_currency = currency
            existing.synced_at = _now()
        else:
            db.add(CostByResourceSnapshot(
                id=str(uuid.uuid4()),
                subscription_id=subscription_id,
                resource_id=resource_id,
                service_name=service_name,
                resource_group=resource_group or None,
                resource_type=resource_type or None,
                month=month,
                cost_usd=usd,
                cost_billing=pretax,
                billing_currency=currency,
            ))
        written += 1
    return written


def _persist_mtd_by_resource(
    db: Session,
    subscription_id: str,
    month: str,
    rows: list[dict],
) -> int:
    """Write MTD per-resource costs with service name into cost_by_resource."""
    res_raw = cost_export.by_resource_response(rows)
    by_resource = parse_cost_by_resource_details(res_raw)
    if not by_resource:
        log.warning("cost_sync.resource_columns_missing", subscription_id=subscription_id)
        return 0
    return _persist_mtd_by_resource_agg(db, subscription_id, month, by_resource)


def _persist_mtd_by_service(
    db: Session,
    subscription_id: str,
    month: str,
    rows: list[dict],
) -> int:
    """Write MTD per-service totals from blob rows into cost_by_service."""
    svc_raw = cost_export.by_service_response(rows)
    props = svc_raw.get("properties", {})
    table_rows = props.get("rows", [])
    cols = props.get("columns", [])
    idx = cost_column_indices(cols)
    svc_idx = idx["service_name"]
    pretax_idx = idx["pretax"]
    usd_idx = idx["usd"]
    currency_idx = idx["currency"]
    if svc_idx is None or pretax_idx is None:
        log.warning("cost_sync.service_columns_missing", subscription_id=subscription_id)
        return 0

    written = 0
    for row in table_rows:
        svc = service_name_from_cost_row(
            row, idx, names=[c.get("name") if isinstance(c, dict) else c for c in cols],
        )
        pretax = float(row[pretax_idx])
        usd = float(row[usd_idx]) if usd_idx is not None else 0.0
        currency = str(row[currency_idx]) if currency_idx is not None and row[currency_idx] else "USD"
        existing = (
            db.query(CostByServiceSnapshot)
            .filter(
                CostByServiceSnapshot.subscription_id == subscription_id,
                CostByServiceSnapshot.service_name == svc,
                CostByServiceSnapshot.month == month,
            )
            .first()
        )
        if existing:
            existing.cost_usd = usd
            existing.cost_billing = pretax
            existing.billing_currency = currency
            existing.synced_at = _now()
        else:
            db.add(CostByServiceSnapshot(
                id=str(uuid.uuid4()),
                subscription_id=subscription_id,
                service_name=svc,
                month=month,
                cost_usd=usd,
                cost_billing=pretax,
                billing_currency=currency,
            ))
        written += 1
    return written


def _service_totals_from_service_agg(by_service: dict[str, dict]) -> dict[str, dict]:
    """Build per-service MTD totals from pre-aggregated service buckets."""
    agg: dict[str, dict] = {}
    for svc, bucket in by_service.items():
        agg[svc] = {
            "service_name": svc,
            "billing": round(float(bucket.get("pretax") or 0.0), 4),
            "usd": round(float(bucket.get("usd") or 0.0), 4),
            "currency": bucket.get("currency") or "USD",
        }
    return agg


def _persist_mtd_by_resource_response(
    db: Session,
    subscription_id: str,
    month: str,
    response: dict,
) -> int:
    """Write MTD per-resource costs from a Cost Management query response."""
    from app.azure_cost import normalize_query_response

    res_raw = normalize_query_response(response)
    by_resource = parse_cost_by_resource_details(res_raw)
    if not by_resource and (res_raw.get("properties") or {}).get("rows"):
        log.warning("cost_sync.resource_columns_missing", subscription_id=subscription_id)
        return 0
    return _persist_mtd_by_resource_agg(db, subscription_id, month, by_resource)


def _persist_mtd_by_service_response(
    db: Session,
    subscription_id: str,
    month: str,
    response: dict,
) -> int:
    """Write MTD per-service totals from a Cost Management query response."""
    from app.azure_cost import normalize_query_response

    svc_raw = normalize_query_response(response)
    props = svc_raw.get("properties", {})
    table_rows = props.get("rows", [])
    cols = props.get("columns", [])
    idx = cost_column_indices(cols)
    svc_idx = idx["service_name"]
    pretax_idx = idx["pretax"]
    usd_idx = idx["usd"]
    currency_idx = idx["currency"]
    if svc_idx is None or pretax_idx is None:
        log.warning("cost_sync.service_columns_missing", subscription_id=subscription_id)
        return 0

    written = 0
    default_currency = svc_raw.get("billing_currency") or "CAD"
    for row in table_rows:
        svc = service_name_from_cost_row(
            row, idx, names=[c.get("name") if isinstance(c, dict) else c for c in cols],
        )
        pretax = float(row[pretax_idx])
        usd = float(row[usd_idx]) if usd_idx is not None else 0.0
        currency = (
            str(row[currency_idx]) if currency_idx is not None and row[currency_idx] else default_currency
        )
        existing = (
            db.query(CostByServiceSnapshot)
            .filter(
                CostByServiceSnapshot.subscription_id == subscription_id,
                CostByServiceSnapshot.service_name == svc,
                CostByServiceSnapshot.month == month,
            )
            .first()
        )
        if existing:
            existing.cost_usd = usd
            existing.cost_billing = pretax
            existing.billing_currency = currency
            existing.synced_at = _now()
        else:
            db.add(CostByServiceSnapshot(
                id=str(uuid.uuid4()),
                subscription_id=subscription_id,
                service_name=svc,
                month=month,
                cost_usd=usd,
                cost_billing=pretax,
                billing_currency=currency,
            ))
        written += 1
    return written


def _service_totals_from_service_response(response: dict) -> dict[str, dict]:
    from app.azure_cost import billing_currency_from_response, normalize_query_response

    svc_raw = normalize_query_response(response)
    props = svc_raw.get("properties", {})
    cols = props.get("columns", [])
    idx = cost_column_indices(cols)
    svc_idx = idx["service_name"]
    pretax_idx = idx["pretax"]
    usd_idx = idx["usd"]
    currency_idx = idx["currency"]
    default_currency = billing_currency_from_response(svc_raw)
    agg: dict[str, dict] = {}
    for row in props.get("rows") or []:
        if svc_idx is None or pretax_idx is None:
            break
        svc = service_name_from_cost_row(row, idx, names=[c.get("name") if isinstance(c, dict) else c for c in cols])
        pretax = float(row[pretax_idx])
        usd = float(row[usd_idx]) if usd_idx is not None else 0.0
        currency = (
            str(row[currency_idx]) if currency_idx is not None and row[currency_idx] else default_currency
        )
        bucket = agg.setdefault(
            svc,
            {"service_name": svc, "billing": 0.0, "usd": 0.0, "currency": currency},
        )
        bucket["billing"] += pretax
        bucket["usd"] += usd
        bucket["currency"] = currency
    for bucket in agg.values():
        bucket["billing"] = round(bucket["billing"], 4)
        bucket["usd"] = round(bucket["usd"], 4)
    return agg


def _service_totals_from_mtd_rows(mtd_rows: list[dict]) -> dict[str, dict]:
    """Aggregate MTD rows to per-service billing and USD totals."""
    agg: dict[str, dict] = {}
    for row in mtd_rows:
        svc = row.get("service_name") or "Other"
        bucket = agg.setdefault(
            svc,
            {"service_name": svc, "billing": 0.0, "usd": 0.0, "currency": row.get("currency") or "CAD"},
        )
        bucket["billing"] += float(row.get("cost") or 0.0)
        bucket["usd"] += float(row.get("cost_usd") or 0.0)
        if row.get("currency"):
            bucket["currency"] = row["currency"]
    for bucket in agg.values():
        bucket["billing"] = round(bucket["billing"], 4)
        bucket["usd"] = round(bucket["usd"], 4)
    return agg


def _compute_service_changes(previous: dict[str, dict], current: dict[str, dict]) -> list[dict]:
    """Diff per-service MTD totals between two fetches."""
    changes: list[dict] = []
    for svc in set(previous) | set(current):
        prev = previous.get(svc, {})
        curr = current.get(svc, {})
        pb = float(prev.get("billing") or 0.0)
        cb = float(curr.get("billing") or 0.0)
        pu = float(prev.get("usd") or 0.0)
        cu = float(curr.get("usd") or 0.0)
        delta_b = round(cb - pb, 2)
        delta_u = round(cu - pu, 2)
        if delta_b == 0 and delta_u == 0:
            continue
        changes.append({
            "service_name": svc,
            "previous_billing": round(pb, 2),
            "current_billing": round(cb, 2),
            "delta_billing": delta_b,
            "previous_usd": round(pu, 2),
            "current_usd": round(cu, 2),
            "delta_usd": delta_u,
        })
    changes.sort(key=lambda item: abs(item["delta_billing"]), reverse=True)
    return changes


def _previous_service_totals(
    db: Session,
    subscription_id: str,
    month: str,
) -> tuple[dict[str, dict], datetime | None]:
    run = (
        db.query(CostSyncRun)
        .filter(
            CostSyncRun.subscription_id == subscription_id,
            CostSyncRun.month == month,
        )
        .order_by(CostSyncRun.synced_at.desc())
        .first()
    )
    if not run or not run.services_json:
        return {}, None
    try:
        items = json.loads(run.services_json)
    except json.JSONDecodeError:
        return {}, run.synced_at
    return {item["service_name"]: item for item in items}, run.synced_at


def _distinct_resource_groups_for_cost(
    db: Session,
    subscription_id: str,
    *,
    extra_groups: list[str] | None = None,
) -> list[str]:
    """Collect resource group names for batched Cost Management by-resource queries."""
    groups: set[str] = set()
    for (rg,) in (
        db.query(ResourceSnapshot.resource_group)
        .filter(
            ResourceSnapshot.subscription_id == subscription_id,
            ResourceSnapshot.resource_group.isnot(None),
            ResourceSnapshot.resource_group != "",
        )
        .distinct()
    ):
        name = (rg or "").strip()
        if name:
            groups.add(name)
    for rg in extra_groups or []:
        name = (rg or "").strip()
        if name:
            groups.add(name)
    return sorted(groups)


def _record_cost_sync_run(
    db: Session,
    subscription_id: str,
    month: str,
    mtd_start: str,
    mtd_end: str,
    current_services: dict[str, dict],
    changes: list[dict],
    previous_synced_at: datetime | None,
    *,
    subscription_total_billing: float,
    subscription_total_usd: float,
    subscription_currency: str,
) -> None:
    currency = subscription_currency or "CAD"
    if not subscription_currency and current_services:
        currency = next(iter(current_services.values())).get("currency") or "CAD"
    db.add(CostSyncRun(
        id=str(uuid.uuid4()),
        subscription_id=subscription_id,
        month=month,
        mtd_start=mtd_start,
        mtd_end=mtd_end,
        total_billing=round(float(subscription_total_billing), 2),
        total_usd=round(float(subscription_total_usd), 2),
        billing_currency=currency,
        services_json=json.dumps(list(current_services.values())),
        changes_json=json.dumps(changes),
        previous_synced_at=previous_synced_at,
    ))


def sync_costs(subscription_id: str, db: Session, token: str) -> dict:
    """Dashboard / Cost explorer sync (subscription + resource type only)."""
    from app.cost_explorer_sync import sync_cost_explorer

    return sync_cost_explorer(subscription_id, db, token)


def sync_scoped(
    subscription_id: str,
    db: Session,
    token: str,
    types: list[str],
    *,
    include_costs: bool = False,
) -> dict:
    """Sync only the requested resource types; optional cost export when include_costs=True."""
    subscription_id = subscription_id.lower()
    types_set = normalize_sync_types(types)
    if not types_set:
        raise ValueError("At least one resource type is required for scoped sync")

    log.info("sync_scoped.start", subscription_id=subscription_id, types=sorted(types_set))

    try:
        sync_subscription_catalog(db)
    except Exception as exc:
        log.warning("subscription catalog sync failed: %s", exc)
        ensure_subscription_cache_row(db, subscription_id)
        db.commit()

    resource_counts = sync_resources(subscription_id, db, token, types=list(types_set))
    cost_counts: dict = {}
    if include_costs:
        cost_counts = sync_costs(subscription_id, db, token)

    from app.resource_pricing import dedupe_resource_pricing_profiles

    removed_pricing_dupes = dedupe_resource_pricing_profiles(db, subscription_id)
    if removed_pricing_dupes:
        log.info("Removed %s duplicate resource pricing profile rows", removed_pricing_dupes)

    ensure_subscription_cache_row(db, subscription_id)
    db.commit()
    result = {
        "scoped": True,
        "types": sorted(types_set),
        "resources": resource_counts,
        "costs": cost_counts,
    }
    log.info("sync_scoped.complete", subscription_id=subscription_id, **result)
    return result


def sync_all(subscription_id: str, db: Session, token: str) -> dict:
    """
    Master sync: resources + costs. Called by POST /api/resources/sync.
    """
    subscription_id = subscription_id.lower()
    log.info("Starting full sync for subscription %s", subscription_id)
    log.info("sync_all.start", subscription_id=subscription_id)

    try:
        sync_subscription_catalog(db)
    except Exception as exc:
        log.warning("subscription catalog sync failed: %s", exc)
        ensure_subscription_cache_row(db, subscription_id)
        db.commit()

    resource_counts = sync_resources(subscription_id, db, token)
    removed_dupes = _dedupe_resource_snapshots(db, subscription_id)
    if removed_dupes:
        log.info("Deactivated %s duplicate resource snapshot rows", removed_dupes)
    from app.resource_pricing import dedupe_resource_pricing_profiles

    removed_pricing_dupes = dedupe_resource_pricing_profiles(db, subscription_id)
    if removed_pricing_dupes:
        log.info("Removed %s duplicate resource pricing profile rows", removed_pricing_dupes)
    # Costs: cost_explorer_worker + POST /costs/sync (not bundled with inventory sync).
    cost_counts: dict = {}
    ensure_subscription_cache_row(db, subscription_id)
    db.commit()
    db_total = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == subscription_id,
            ResourceSnapshot.is_active.is_(True),
        )
        .count()
    )
    result = {"resources": resource_counts, "costs": cost_counts, "db_total": db_total}
    try:
        from app.advisor_sync import sync_azure_advisor_recommendations

        advisor_result = sync_azure_advisor_recommendations(subscription_id, db, token)
        result["advisor"] = {
            "fetched": advisor_result.get("fetched", 0),
            "stored": advisor_result.get("stored", 0),
        }
    except Exception as exc:
        log.warning("advisor_sync_during_full_sync_failed", error=str(exc)[:200])
        result["advisor"] = {"error": str(exc)[:200]}
    log.info("sync_all.complete", subscription_id=subscription_id, **result)
    return result

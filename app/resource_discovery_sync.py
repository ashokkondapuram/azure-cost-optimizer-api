"""Discover subscription inventory from the ARM resources list API.

Uses ``GET /subscriptions/{id}/resources`` (paginated) once per subscription,
maps each row to our canonical layout, and upserts known types into
``resource_snapshots``. Complements per-component typed sync with a full
subscription sweep every 6 hours.
"""
from __future__ import annotations

from collections import defaultdict

import structlog
from sqlalchemy.orm import Session

from app.arm_resource_enrichment import enrich_arm_resources_for_type
from app.auth import arm_auth_context
from app.azure_resources import AzureResourcesClient
from app.db_sync import (
    VmSkuCatalogCache,
    _prune_stale_resources,
    _record_type_sync,
    _upsert_arm_resource,
    _vm_power_state,
    build_aks_sync_properties,
)
from app.http_client import arm_patient_sync
from app.resource_cost_audit import audit_from_arm_items
from app.resource_type_map import inventory_canonical_for_arm_type
from app.resources import get_technical_fetch_spec, pick_sync_properties
from app.vm_utils import filter_standalone_vms
from app.inventory_standalone import is_standalone_inventory_type

log = structlog.get_logger()


def sync_resource_discovery(subscription_id: str, db: Session, token: str) -> dict:
    """List all ARM resources for a subscription and upsert mapped inventory rows."""
    subscription_id = subscription_id.strip().lower()
    counts: dict[str, int] = {}
    synced_ids: dict[str, set[str]] = {}
    successful_types: set[str] = set()
    by_canonical: dict[str, list[dict]] = defaultdict(list)

    with arm_auth_context(db=db, token=token):
        client = AzureResourcesClient(db=db)
        with arm_patient_sync():
            all_items = client.list_resources(subscription_id)
            for item in all_items:
                arm_type = (item.get("type") or "").strip().lower()
                canonical = inventory_canonical_for_arm_type(arm_type)
                if not canonical:
                    continue
                by_canonical[canonical].append(item)

            catalog_cache = VmSkuCatalogCache(client, subscription_id)
            for canonical, items in sorted(by_canonical.items()):
                try:
                    if not is_standalone_inventory_type(canonical):
                        continue
                    if canonical == "compute/vm":
                        items = filter_standalone_vms(items)
                    items = enrich_arm_resources_for_type(client, subscription_id, items, canonical)
                    for item in items:
                        props = item.get("properties") or {}
                        spec = get_technical_fetch_spec(canonical)
                        state = props.get("provisioningState") or props.get("state")
                        extra_props = None
                        if canonical == "containers/aks":
                            props = item.get("properties") or {}
                            state = (
                                (props.get("powerState") or {}).get("code")
                                or props.get("provisioningState")
                            )
                            extra_props = build_aks_sync_properties(
                                client, subscription_id, item,
                            )
                        elif canonical == "compute/vm":
                            power = _vm_power_state(item)
                            if power:
                                extra_props = dict(pick_sync_properties(item, spec))
                                extra_props["powerState"] = power
                                state = power
                        _upsert_arm_resource(
                            db,
                            subscription_id,
                            item,
                            canonical,
                            catalog_cache=catalog_cache,
                            state=state,
                            properties=extra_props,
                        )
                    counts[canonical] = len(items)
                    _record_type_sync(synced_ids, successful_types, canonical, items)
                except Exception as exc:
                    log.warning(
                        "resource_discovery.type_failed",
                        subscription_id=subscription_id,
                        canonical_type=canonical,
                        error=str(exc),
                    )

            removed = _prune_stale_resources(
                db, subscription_id, synced_ids, successful_types,
            )
            db.commit()

    cost_audit = audit_from_arm_items(db, subscription_id, all_items)
    unmapped_cost = {
        row["arm_type"]: row["resource_count"]
        for row in cost_audit.get("gaps", [])
    }

    result = {
        "subscription_id": subscription_id,
        "source": "arm_resources_list",
        "total_listed": len(all_items),
        "resource_counts": counts,
        "synced_types": sorted(successful_types),
        "removed": removed,
        "unmapped_arm_types": unmapped_cost,
        "unmapped_count": sum(unmapped_cost.values()),
        "free_skipped_unmapped_count": cost_audit.get("free_skipped_unmapped_count", 0),
        "free_skipped_unmapped_types": cost_audit.get("free_skipped_unmapped_types", {}),
        "cost_audit": cost_audit,
    }
    log.info(
        "resource_discovery.complete",
        subscription_id=subscription_id,
        total_listed=result["total_listed"],
        synced_types=len(successful_types),
        unmapped=result["unmapped_count"],
    )
    return result

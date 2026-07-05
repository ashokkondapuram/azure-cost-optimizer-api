"""Fetch full ARM resource payloads when list-all responses omit technical properties."""

from __future__ import annotations

import os
import structlog
from concurrent import futures
from typing import Any

from app.arm_api_versions import ARM_GET_API_VERSIONS, api_version_for_arm_type
from app.focus_mapping import normalize_arm_id
from app.http_client import arm_patient_active
from app.resource_type_map import arm_provider_type, extract_rg_from_arm
from app.resources import TechnicalFetchSpec, get_technical_fetch_spec
from app.disk_staleness import disk_property_present
from app.resources.compute.snapshot import snapshot_property_present
from app.resources.storage.account import storage_property_present

log = structlog.get_logger(__name__)

_ENRICH_WORKERS = max(1, int(os.getenv("ARM_ENRICH_WORKERS", "4")))

# Property keys absent from list-all responses (trigger per-resource GET).
ENRICH_IF_MISSING: dict[str, tuple[str, ...]] = {
    "compute/vm": ("hardwareProfile",),
    "compute/vmss": ("virtualMachineProfile",),
    "compute/disk": ("diskSizeGB", "diskState", "timeCreated", "lastOwnershipUpdateTime"),
    "compute/snapshot": ("diskSizeGB", "timeCreated"),
    "containers/acr": ("provisioningState", "policies", "zoneRedundancy", "networkRuleSet"),
    "storage/account": ("kind", "accessTier"),
    "network/publicip": ("publicIPAllocationMethod", "ipAddress"),
    "network/nic": ("ipConfigurations",),
    "network/nat": ("subnets",),
    "database/sql": ("version",),
    "database/cosmosdb": ("databaseAccountOfferType",),
    "database/postgresql": ("storage",),
    "database/redis": ("redisConfiguration",),
    "appservice/webapp": ("state",),
    "appservice/plan": ("numberOfSites",),
    "security/keyvault": ("enableSoftDelete", "enablePurgeProtection", "sku", "networkAcls"),
    # Generic ARM sync — thin list responses from Resources API
    "monitoring/loganalytics": ("retentionInDays", "sku"),
    "monitoring/appinsights": ("Application_Type", "WorkspaceResourceId"),
    "integration/apim": ("virtualNetworkType",),
    "integration/datafactory": ("publicNetworkAccess",),
    "integration/logicapp": ("state",),
    "messaging/eventhub": ("kafkaEnabled",),
    "messaging/servicebus": ("zoneRedundant",),
    "analytics/databricks": ("parameters",),
    "analytics/synapse": ("settings",),
    "analytics/adx": ("state",),
    "analytics/mlworkspace": ("discoveryUrl",),
    "backup/recoveryvault": ("sku",),
    "search/cognitivesearch": ("replicaCount",),
    "network/privateendpoint": ("privateLinkServiceConnections", "privateDnsZoneGroups"),
    "network/privatelinkservice": ("privateEndpointConnections",),
    "network/privatedns": ("numberOfRecordSets",),
}

# Empty lists from list-all are often wrong (resource actually has config).
ENRICH_IF_EMPTY: dict[str, tuple[str, ...]] = {
    "network/loadbalancer": ("backendAddressPools",),
    "network/appgateway": ("httpListeners",),
    "network/nsg": ("securityRules",),
    "network/privateendpoint": ("privateLinkServiceConnections", "privateDnsZoneGroups"),
    "network/privatelinkservice": ("privateEndpointConnections",),
    "network/privatedns": ("numberOfRecordSets",),
    "containers/aks": ("agentPoolProfiles",),
}

def _property_populated(props: dict[str, Any], key: str) -> bool:
    val = props.get(key)
    if val is None or val == "":
        return False
    if isinstance(val, (list, dict)) and len(val) == 0:
        return False
    return True


def enrichment_paths(spec: TechnicalFetchSpec | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not spec:
        return (), ()
    missing = spec.enrich_if_missing or ENRICH_IF_MISSING.get(spec.canonical_type, ())
    empty = spec.enrich_if_empty or ENRICH_IF_EMPTY.get(spec.canonical_type, ())
    if not missing and spec.generic_arm_sync and spec.sync_property_paths:
        missing = spec.sync_property_paths[:2]
    return missing, empty


def needs_arm_enrichment(resource: dict[str, Any], spec: TechnicalFetchSpec | None) -> bool:
    """True when list-all payload lacks technical properties needed for analysis."""
    if not resource:
        return False
    props = resource.get("properties") or {}
    if not spec:
        return False

    if spec.generic_arm_sync:
        if not props:
            return True
        if spec.sync_property_paths:
            present = sum(1 for key in spec.sync_property_paths if _property_populated(props, key))
            if present < max(1, len(spec.sync_property_paths) // 2):
                return True

    missing_paths, empty_paths = enrichment_paths(spec)
    for key in missing_paths:
        if props.get(key) not in (None, "") or resource.get(key) not in (None, ""):
            continue
        if disk_property_present(props, key) or snapshot_property_present(resource, props, key):
            continue
        if storage_property_present(resource, props, key):
            continue
        return True
    for key in empty_paths:
        val = props.get(key)
        if val is None or (isinstance(val, list) and len(val) == 0):
            return True

    if spec.sync_property_paths and not missing_paths and not empty_paths:
        absent = sum(1 for key in spec.sync_property_paths if not _property_populated(props, key))
        if absent >= max(1, len(spec.sync_property_paths) // 2):
            return True
    return False


def _fetch_full_resource(client: Any, subscription_id: str, resource: dict[str, Any], spec: TechnicalFetchSpec) -> dict[str, Any]:
    rid = normalize_arm_id(resource.get("id") or "")
    rg = extract_rg_from_arm(rid)
    name = (resource.get("name") or "").strip()
    canonical = spec.canonical_type

    if canonical == "compute/vm" and rg and name:
        return client.get_vm(subscription_id, rg, name)
    if canonical == "compute/vmss" and rg and name:
        return client.get_vm_scale_set(subscription_id, rg, name)
    if canonical == "compute/disk" and rg and name:
        return client.get_disk(subscription_id, rg, name)
    if canonical == "compute/snapshot" and rg and name:
        return client.get_snapshot(subscription_id, rg, name)
    if canonical == "containers/aks" and rg and name:
        return client.get_aks_cluster(subscription_id, rg, name)
    if canonical == "network/appgateway" and rg and name:
        return client.get_application_gateway(subscription_id, rg, name)
    if canonical == "storage/account" and rg and name:
        return client.get_storage_account(subscription_id, rg, name)
    if rid:
        return client.get_arm_resource(rid)
    return resource


def _enrich_one(client: Any, subscription_id: str, resource: dict[str, Any], spec: TechnicalFetchSpec) -> dict[str, Any]:
    if not needs_arm_enrichment(resource, spec):
        return resource
    name = resource.get("name") or rid_short(resource.get("id"))
    try:
        return _fetch_full_resource(client, subscription_id, resource, spec)
    except Exception as exc:
        log.debug("arm_enrich_failed", resource=name, canonical=spec.canonical_type, error=str(exc))
        return resource


def rid_short(resource_id: str | None) -> str:
    rid = normalize_arm_id(resource_id or "")
    return rid.rsplit("/", 1)[-1] if rid else ""


def enrich_arm_resources(
    client: Any,
    subscription_id: str,
    resources: list[dict[str, Any]] | None,
    canonical_type: str,
    *,
    max_workers: int | None = None,
) -> list[dict[str, Any]]:
    """Ensure each resource has full technical properties from a per-resource GET when needed."""
    items = list(resources or [])
    if not items:
        return []

    spec = get_technical_fetch_spec(canonical_type)
    if spec is None:
        return items

    to_enrich = [r for r in items if needs_arm_enrichment(r, spec)]
    if not to_enrich:
        return items

    workers = 1 if arm_patient_active() else min(max_workers or _ENRICH_WORKERS, len(to_enrich))
    enriched_by_id: dict[str, dict[str, Any]] = {}

    def _run(resource: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        full = _enrich_one(client, subscription_id, resource, spec)
        return normalize_arm_id(resource.get("id") or ""), full

    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for rid, full in pool.map(_run, to_enrich):
            if rid:
                enriched_by_id[rid] = full

    out: list[dict[str, Any]] = []
    for resource in items:
        rid = normalize_arm_id(resource.get("id") or "")
        out.append(enriched_by_id.get(rid, resource))
    return out


def enrich_arm_resources_for_type(
    client: Any,
    subscription_id: str,
    resources: list[dict[str, Any]] | None,
    canonical_type: str,
) -> list[dict[str, Any]]:
    """AKS uses node-pool enrichment first; all other types use generic ARM GET enrichment."""
    canonical = (canonical_type or "").strip().lower()
    if canonical == "containers/aks":
        from app.db_sync import enrich_aks_arm_clusters

        rows = enrich_aks_arm_clusters(client, subscription_id, list(resources or []))
        return enrich_arm_resources(client, subscription_id, rows, canonical)
    return enrich_arm_resources(client, subscription_id, resources, canonical)


def api_version_for_resource_id(resource_id: str) -> str:
    arm = arm_provider_type(resource_id)
    return api_version_for_arm_type(arm)

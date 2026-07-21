"""Resource profile — owned by storage-account IT service."""

from __future__ import annotations

from typing import Any

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "storage/account"

_SYNC_KEYS = (
    "kind", "accessTier", "minimumTlsVersion", "supportsHttpsTrafficOnly",
    "allowBlobPublicAccess", "provisioningState",
)

_STORAGE_PROPERTY_ALIASES: dict[str, tuple[str, ...]] = {
    "accessTier": ("accessTier", "AccessTier"),
    "kind": ("kind", "Kind"),
    "sku": ("sku", "Sku"),
    "provisioningState": ("provisioningState", "ProvisioningState"),
    "minimumTlsVersion": ("minimumTlsVersion", "MinimumTlsVersion"),
    "supportsHttpsTrafficOnly": ("supportsHttpsTrafficOnly", "SupportsHttpsTrafficOnly"),
    "allowBlobPublicAccess": ("allowBlobPublicAccess", "AllowBlobPublicAccess"),
}

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Storage/storageAccounts",
    display_name="Storage account",
    sync_property_paths=_SYNC_KEYS,
    fields=(
        field("access_tier", "props:accessTier", "Access tier", "configuration",
              "STORAGE_HOT_TIER", "STORAGE_COOL_TIER"),
        field("kind", "props:kind", "Storage kind", "configuration", "STORAGE_NO_LIFECYCLE"),
        field("sku_name", "sku:name", "Replication", "configuration",
              "STORAGE_LRS_CRITICAL", "STORAGE_REDUNDANCY_EXTENDED"),
        field("https_only", "props:supportsHttpsTrafficOnly", "HTTPS only", "governance"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.storage/storageaccounts",
    canonical_type=CANONICAL_TYPE,
    display_name="Storage account",
    doc_ref="microsoft-storage-storageaccounts-metrics",
    metrics=(
        um("UsedCapacity", "used_capacity_bytes", "Storage capacity used",
           rules=("STORAGE_NO_LIFECYCLE", "STORAGE_LIFECYCLE_EXTENDED", "STORAGE_COOL_TIER_CANDIDATE_EXTENDED")),
        um("Transactions", "transaction_count", "Storage transaction volume", aggregation="Total",
           rules=("STORAGE_NO_LIFECYCLE", "STORAGE_COOL_TIER_CANDIDATE_EXTENDED")),
        um("Egress", "egress_bytes", "Data egress volume", aggregation="Total",
           rules=("STORAGE_EGRESS_HIGH_EXTENDED",)),
        um("Ingress", "ingress_bytes", "Data ingress volume", aggregation="Total",
           rules=("STORAGE_EGRESS_HIGH_EXTENDED",)),
        um("Availability", "availability_pct", "Storage availability", aggregation="Average",
           rules=()),
    ),
)


def storage_property_present(
    resource: dict[str, Any],
    props: dict[str, Any],
    canonical_key: str,
) -> bool:
    """True when a storage account field exists (top-level kind or properties)."""
    aliases = _STORAGE_PROPERTY_ALIASES.get(canonical_key)
    if not aliases:
        return False
    if resource.get(canonical_key) not in (None, ""):
        return True
    return any(props.get(alias) not in (None, "") for alias in aliases)


def normalize_storage_arm_properties(arm_resource: dict[str, Any]) -> dict[str, Any]:
    """Normalize Storage Accounts GET properties for persistence."""
    props = dict(arm_resource.get("properties") or {})
    if arm_resource.get("kind"):
        props.setdefault("kind", arm_resource["kind"])
    sku = arm_resource.get("sku")
    if isinstance(sku, dict) and sku.get("name"):
        props.setdefault("sku", sku)
    out: dict[str, Any] = {}
    for key in _SYNC_KEYS:
        if key in props and props[key] is not None:
            out[key] = props[key]
            continue
        if arm_resource.get(key) not in (None, ""):
            out[key] = arm_resource[key]
            continue
        for alias in _STORAGE_PROPERTY_ALIASES.get(key, (key,)):
            if alias in props:
                out[key] = props[alias]
                break
    return out

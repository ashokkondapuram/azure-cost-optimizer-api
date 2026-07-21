"""Resource profile — owned by compute-snapshot IT service."""

from __future__ import annotations

from typing import Any

from app.disk_staleness import disk_property_present, disk_property_value
from app.resources.types import TechnicalFetchSpec, field

CANONICAL_TYPE = "compute/snapshot"

_SNAPSHOT_PROPERTY_ALIASES: dict[str, tuple[str, ...]] = {
    "provisioningState": ("provisioningState", "ProvisioningState"),
    "timeCreated": ("timeCreated", "TimeCreated"),
    "diskState": ("diskState", "DiskState"),
}

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Compute/snapshots",
    display_name="Disk snapshot",
    sync_property_paths=(
        "diskSizeGB", "diskState", "provisioningState", "timeCreated", "creationData",
    ),
    fields=(
        field("size_gb", "props:diskSizeGB", "Snapshot size (GB)", "capacity",
              "SNAPSHOT_OLD", "SNAPSHOT_RETENTION_EXTENDED"),
        field("disk_state", "props:diskState", "Snapshot state", "association",
              "SNAPSHOT_OLD", "SNAPSHOT_RETENTION_EXTENDED"),
        field("provisioning_state", "props:provisioningState", "Provisioning state", "configuration",
              "SNAPSHOT_RETENTION_EXTENDED"),
        field("sku", "row:sku", "SKU", "configuration",
              "SNAPSHOT_OLD", "SNAPSHOT_RETENTION_EXTENDED"),
        field("time_created", "props:timeCreated", "Created", "configuration",
              "SNAPSHOT_OLD", "SNAPSHOT_RETENTION_EXTENDED"),
        field("age_days", "computed:snapshot_age_days", "Age (days)", "utilization",
              "SNAPSHOT_OLD", "SNAPSHOT_RETENTION_EXTENDED"),
        field("source_disk_id", "props:creationData.sourceResourceId", "Source disk", "association",
              "SNAPSHOT_RETENTION_EXTENDED"),
        field("incremental", "props:creationData.incremental", "Incremental snapshot", "configuration",
              "SNAPSHOT_RETENTION_EXTENDED"),
    ),
)

MONITOR_PROFILE = None


def snapshot_property_present(
    resource: dict[str, Any],
    props: dict[str, Any],
    canonical_key: str,
) -> bool:
    """True when a snapshot property exists under any supported ARM casing."""
    if resource.get(canonical_key) not in (None, ""):
        return True
    if disk_property_present(props, canonical_key):
        return True
    aliases = _SNAPSHOT_PROPERTY_ALIASES.get(canonical_key)
    if not aliases:
        return False
    return any(props.get(alias) not in (None, "") for alias in aliases)


def normalize_snapshot_arm_properties(arm_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize Snapshots GET properties to canonical camelCase keys for persistence."""
    out: dict[str, Any] = {}
    for key in ("diskSizeGB", "timeCreated", "diskState"):
        val = disk_property_value(arm_snapshot, key)
        if val is not None:
            out[key] = val
    props = arm_snapshot.get("properties") or {}
    creation = props.get("creationData") or props.get("CreationData")
    if creation:
        out["creationData"] = creation
    for key, aliases in _SNAPSHOT_PROPERTY_ALIASES.items():
        for alias in aliases:
            if alias in props:
                out[key] = props[alias]
                break
    return out

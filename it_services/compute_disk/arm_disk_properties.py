"""Normalize Microsoft.Compute/disks GET/LIST payloads per Disks - Get REST API."""

from __future__ import annotations

from typing import Any

# Disks - Get (api-version 2026-03-02): properties may use camelCase or PascalCase.
# https://learn.microsoft.com/en-us/rest/api/compute/disks/get?view=rest-compute-2026-03-02
_DISK_PROPERTY_ALIASES: dict[str, tuple[str, ...]] = {
    "lastOwnershipUpdateTime": ("lastOwnershipUpdateTime", "LastOwnershipUpdateTime"),
    "timeCreated": ("timeCreated", "TimeCreated"),
    "diskState": ("diskState", "DiskState"),
    "diskSizeGB": ("diskSizeGB", "DiskSizeGB"),
    "diskSizeBytes": ("diskSizeBytes", "DiskSizeBytes"),
    "managedBy": ("managedBy", "ManagedBy"),
    "creationData": ("creationData", "CreationData"),
    "diskIOPSReadWrite": ("diskIOPSReadWrite", "DiskIOPSReadWrite"),
    "diskMBpsReadWrite": ("diskMBpsReadWrite", "DiskMBpsReadWrite"),
    "diskIOPSReadOnly": ("diskIOPSReadOnly", "DiskIOPSReadOnly"),
    "diskMBpsReadOnly": ("diskMBpsReadOnly", "DiskMBpsReadOnly"),
    "provisioningState": ("provisioningState", "ProvisioningState"),
    "tier": ("tier", "Tier"),
    "burstingEnabled": ("burstingEnabled", "BurstingEnabled"),
    "osType": ("osType", "OsType"),
    "maxShares": ("maxShares", "MaxShares"),
    "shareInfo": ("shareInfo", "ShareInfo"),
    "encryption": ("encryption", "Encryption"),
}


def disk_property_present(props: dict[str, Any], canonical_key: str) -> bool:
    """True when a disk property exists under any supported ARM casing."""
    aliases = _DISK_PROPERTY_ALIASES.get(canonical_key, (canonical_key,))
    return any(props.get(alias) not in (None, "") for alias in aliases)


def disk_property_value(arm_disk: dict[str, Any], canonical_key: str) -> Any:
    """Read a disk field from a Disks GET/LIST payload."""
    if canonical_key == "managedBy":
        return (
            arm_disk.get("managedBy")
            or arm_disk.get("ManagedBy")
            or (arm_disk.get("properties") or {}).get("managedBy")
            or (arm_disk.get("properties") or {}).get("ManagedBy")
        )
    if canonical_key == "managedByExtended":
        return arm_disk.get("managedByExtended") or arm_disk.get("ManagedByExtended")

    props = arm_disk.get("properties") or {}
    for alias in _DISK_PROPERTY_ALIASES.get(canonical_key, (canonical_key,)):
        val = props.get(alias)
        if val not in (None, ""):
            return val
    return None


def _read_sync_property(arm_disk: dict[str, Any], key: str) -> Any:
    """Read one assessment sync_property_paths key from an ARM disk payload."""
    if key in {"managedBy", "managedByExtended"} or key in _DISK_PROPERTY_ALIASES:
        return disk_property_value(arm_disk, key)
    props = arm_disk.get("properties") or {}
    pascal = key[:1].upper() + key[1:] if key else key
    for alias in (key, pascal):
        val = props.get(alias)
        if val not in (None, ""):
            return val
    return arm_disk.get(key) or arm_disk.get(pascal)


def disk_attachment_arm_ids(arm_disk: dict[str, Any]) -> list[str]:
    """
    VM host ARM IDs from managedBy, managedByExtended, or shareInfo.vmUri.

    See Disk.managedBy, Disk.managedByExtended, Disk.properties.shareInfo.
    """
    ids: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if not value or not isinstance(value, str):
            return
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            ids.append(value.strip())

    add(disk_property_value(arm_disk, "managedBy"))
    for item in disk_property_value(arm_disk, "managedByExtended") or []:
        add(item)
    for entry in disk_property_value(arm_disk, "shareInfo") or []:
        if isinstance(entry, dict):
            add(entry.get("vmUri") or entry.get("VmUri"))

    return ids


def normalize_disk_arm_properties(arm_disk: dict[str, Any]) -> dict[str, Any]:
    """Normalize Disks GET properties — only keys listed in disk-assessment.json sync_property_paths."""
    from it_services.compute_disk.assessment_bridge import disk_sync_property_paths

    out: dict[str, Any] = {}
    for key in disk_sync_property_paths():
        val = _read_sync_property(arm_disk, key)
        if val is not None:
            out[key] = val

    sku = arm_disk.get("sku")
    if isinstance(sku, dict) and sku.get("name"):
        out["sku"] = sku["name"]

    return out

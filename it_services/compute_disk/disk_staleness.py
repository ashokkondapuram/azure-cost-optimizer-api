"""Unattached managed disk staleness — creation time, ownership history, detach age."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.focus_mapping import normalize_arm_id
from app.models import ResourceSnapshot
from it_services.compute_disk.arm_disk_properties import (
    disk_property_present,
    disk_property_value,
    normalize_disk_arm_properties,
)
def disk_sync_state(
    arm_disk: dict[str, Any],
    sync_props: dict[str, Any] | None = None,
) -> str | None:
    """Resolve diskState for DB state column (handles PascalCase and managedBy fallback)."""
    props = sync_props or {}
    for source in (props, normalize_disk_arm_properties(arm_disk)):
        val = source.get("diskState")
        if val not in (None, ""):
            return str(val).strip()
    managed = disk_property_value(arm_disk, "managedBy")
    if managed:
        return "Attached"
    return None


def is_disk_finding(finding: dict[str, Any]) -> bool:
    rt = (finding.get("resource_type") or "").lower()
    rid = (finding.get("resource_id") or "").lower()
    return rt in ("compute/disk", "microsoft.compute/disks") or "/microsoft.compute/disks/" in rid


def augment_disk_evidence(
    facts: dict[str, Any] | None,
    properties: dict[str, Any] | None = None,
    *,
    disk_resource: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge synced disk properties and derived lineage into evidence facts."""
    out = dict(facts or {})
    props = dict(properties or {})
    if disk_resource:
        props = {**props, **normalize_disk_arm_properties(disk_resource)}
    if props:
        merged_props = dict(out.get("properties") or {})
        merged_props.update({k: v for k, v in props.items() if v not in (None, "")})
        out["properties"] = merged_props
    lineage = disk_lineage_from_facts(out)
    for key, val in lineage.items():
        if val is not None and val != "":
            out[key] = val
    return out


def _parse_azure_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def owner_display_name(arm_id: str | None) -> str | None:
    """Human-readable last owner from an ARM resource ID."""
    if not arm_id:
        return None
    text = arm_id.strip().rstrip("/")
    lower = text.lower()
    for marker in ("/virtualmachines/", "/virtualmachinescalesets/"):
        if marker in lower:
            idx = lower.index(marker)
            return text[idx + len(marker):].split("/")[0]
    return text.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class UnattachedDiskContext:
    is_unattached: bool
    time_created: datetime | None
    last_ownership_update: datetime | None
    last_managed_by: str | None
    last_owner_name: str | None
    stale_since: datetime | None
    age_days: int | None
    is_stale: bool
    is_recent: bool


def enrich_disk_sync_properties(
    db: Session,
    subscription_id: str,
    arm_disk: dict[str, Any],
    base_props: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Persist disk creation/ownership timestamps and last known VM owner across syncs.

    When a disk detaches, Azure clears managedBy but exposes lastOwnershipUpdateTime.
    We also retain the previous managedBy from the last sync as lastManagedBy.
    """
    props = dict(base_props or {})
    rid = normalize_arm_id(arm_disk.get("id") or "")
    sub = subscription_id.lower()

    for key, val in normalize_disk_arm_properties(arm_disk).items():
        props[key] = val

    disk_state = (props.get("diskState") or "").strip().lower()
    current_managed = props.get("managedBy")
    is_unattached = disk_state == "unattached" or not current_managed

    existing = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.resource_id == rid,
        )
        .first()
    )
    prev_props: dict[str, Any] = {}
    if existing and existing.properties_json:
        try:
            prev_props = json.loads(existing.properties_json)
        except Exception:
            prev_props = {}

    prev_managed = prev_props.get("managedBy")

    if current_managed:
        props["managedBy"] = current_managed
        props.pop("lastManagedBy", None)
    elif is_unattached:
        last_owner = prev_managed or prev_props.get("lastManagedBy")
        if last_owner:
            props["lastManagedBy"] = last_owner

    from it_services.compute_disk.managed_disk_catalog import enrich_disk_provisioned_properties

    enrich_disk_provisioned_properties(props, sku=arm_disk.get("sku"))

    return props


def evaluate_unattached_disk(
    disk: dict[str, Any],
    *,
    max_days: int = 14,
) -> UnattachedDiskContext:
    """Decide whether an unattached disk is stale enough to recommend deletion."""
    props = disk.get("properties") or {}
    facts = disk.get("_technical_facts") or {}

    state = (props.get("diskState") or disk.get("state") or "").strip().lower()
    managed_by = props.get("managedBy")
    is_unattached = state == "unattached" or not managed_by

    time_created = _parse_azure_datetime(
        props.get("timeCreated") or props.get("TimeCreated") or facts.get("time_created"),
    )
    last_ownership_update = _parse_azure_datetime(
        props.get("lastOwnershipUpdateTime")
        or props.get("LastOwnershipUpdateTime")
        or facts.get("last_ownership_update"),
    )
    last_managed_by = props.get("lastManagedBy") or facts.get("last_managed_by")
    last_owner_name = owner_display_name(last_managed_by)

    if is_unattached:
        stale_since = last_ownership_update or time_created
    else:
        stale_since = None

    age_days: int | None = None
    if stale_since:
        age_days = max(0, (datetime.now(timezone.utc) - stale_since).days)

    is_stale = bool(is_unattached and age_days is not None and age_days >= max_days)
    is_recent = bool(is_unattached and age_days is not None and age_days < max_days)

    return UnattachedDiskContext(
        is_unattached=is_unattached,
        time_created=time_created,
        last_ownership_update=last_ownership_update,
        last_managed_by=last_managed_by,
        last_owner_name=last_owner_name,
        stale_since=stale_since,
        age_days=age_days,
        is_stale=is_stale,
        is_recent=is_recent,
    )


def disk_lineage_from_facts(facts: dict[str, Any] | None) -> dict[str, Any]:
    """
    Normalize disk timestamp/owner fields from evidence, resource_details, or ARM props.

    Computes age_days and last_owner_name when timestamps exist but derived fields do not.
    """
    if not facts:
        return {}

    merged: dict[str, Any] = {}
    for block in (facts, facts.get("resource_details") or {}):
        if not isinstance(block, dict):
            continue
        for key, val in block.items():
            if val is not None and val != "" and key not in merged:
                merged[key] = val

    props = facts.get("properties")
    if isinstance(props, dict):
        for key, val in props.items():
            if val is not None and val != "":
                merged.setdefault(key, val)

    alias_map = {
        "timeCreated": "time_created",
        "TimeCreated": "time_created",
        "lastOwnershipUpdateTime": "last_ownership_update",
        "LastOwnershipUpdateTime": "last_ownership_update",
        "lastManagedBy": "last_managed_by",
        "diskState": "disk_state",
        "diskSizeGB": "size_gb",
    }
    for src, dest in alias_map.items():
        if src in merged and dest not in merged:
            merged[dest] = merged[src]

    disk_props = {
        "diskState": merged.get("disk_state") or merged.get("diskState") or facts.get("disk_state"),
        "timeCreated": merged.get("time_created") or merged.get("timeCreated"),
        "lastOwnershipUpdateTime": merged.get("last_ownership_update") or merged.get("lastOwnershipUpdateTime"),
        "lastManagedBy": merged.get("last_managed_by") or merged.get("lastManagedBy"),
        "managedBy": merged.get("managed_by") or merged.get("managedBy"),
    }
    disk_props = {k: v for k, v in disk_props.items() if v is not None and v != ""}

    disk = {
        "properties": disk_props,
        "state": merged.get("disk_state") or merged.get("state") or "",
        "_technical_facts": {
            k: merged[k]
            for k in ("time_created", "last_ownership_update", "last_managed_by", "disk_state")
            if merged.get(k) not in (None, "")
        },
    }
    ctx = evaluate_unattached_disk(disk)
    out = staleness_evidence(ctx)
    for key in ("time_created", "last_ownership_update", "last_managed_by", "disk_state", "size_gb", "sku"):
        if merged.get(key) not in (None, "") and key not in out:
            out[key] = merged[key]
    return out


def staleness_evidence(ctx: UnattachedDiskContext) -> dict[str, Any]:
    """Evidence block for findings and UI metric panels."""
    out: dict[str, Any] = {
        "stale_since": ctx.stale_since.isoformat() if ctx.stale_since else None,
        "age_days": ctx.age_days,
        "is_stale": ctx.is_stale,
        "is_recent_unattached": ctx.is_recent,
    }
    if ctx.time_created:
        out["time_created"] = ctx.time_created.isoformat()
    if ctx.last_ownership_update:
        out["last_ownership_update"] = ctx.last_ownership_update.isoformat()
    if ctx.last_managed_by:
        out["last_managed_by"] = ctx.last_managed_by
    if ctx.last_owner_name:
        out["last_owner_name"] = ctx.last_owner_name
    return out

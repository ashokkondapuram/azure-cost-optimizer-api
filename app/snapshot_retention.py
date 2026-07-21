"""Disk snapshot age, size gates, and retention helpers for cost optimization rules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.metrics_triggers import TRAFFIC_THRESHOLDS


def snapshot_created_at(snapshot: dict[str, Any]) -> datetime | None:
    """Resolve creation time from technical facts or synced ARM properties."""
    from app.vm_uptime import parse_azure_datetime

    facts = snapshot.get("_technical_facts") or {}
    props = snapshot.get("properties") or {}
    for raw in (
        facts.get("time_created"),
        props.get("timeCreated"),
        props.get("TimeCreated"),
    ):
        parsed = parse_azure_datetime(raw)
        if parsed:
            return parsed
    return None


def snapshot_age_days(snapshot: dict[str, Any], *, now: datetime | None = None) -> int | None:
    facts = snapshot.get("_technical_facts") or {}
    raw_age = facts.get("age_days")
    if raw_age is not None:
        try:
            return max(0, int(raw_age))
        except (TypeError, ValueError):
            pass
    created = snapshot_created_at(snapshot)
    if not created:
        return None
    ref = now or datetime.now(timezone.utc)
    return max(0, (ref - created).days)


def snapshot_size_gb(snapshot: dict[str, Any]) -> float:
    facts = snapshot.get("_technical_facts") or {}
    props = snapshot.get("properties") or {}
    raw = facts.get("size_gb")
    if raw is None:
        raw = props.get("diskSizeGB")
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def is_stale_snapshot(
    snapshot: dict[str, Any],
    *,
    retention_days: int | None = None,
    now: datetime | None = None,
) -> bool | None:
    age = snapshot_age_days(snapshot, now=now)
    if age is None:
        return None
    threshold = (
        retention_days
        if retention_days is not None
        else TRAFFIC_THRESHOLDS["snapshot_retention_days_default"]
    )
    return age > threshold


def meets_snapshot_size_gate(
    snapshot: dict[str, Any],
    *,
    min_size_gb: float | None = None,
) -> bool:
    minimum = min_size_gb if min_size_gb is not None else TRAFFIC_THRESHOLDS["snapshot_min_size_gb"]
    if minimum <= 0:
        return True
    return snapshot_size_gb(snapshot) >= minimum


def meets_snapshot_savings_gate(
    monthly_cost: float,
    *,
    min_monthly_savings_usd: float | None = None,
) -> bool:
    minimum = min_monthly_savings_usd if min_monthly_savings_usd is not None else 0.0
    return monthly_cost >= minimum


def snapshot_threshold_evidence(rule) -> dict[str, Any]:
    """Persist rule thresholds on snapshot finding evidence."""
    out: dict[str, Any] = {}
    for key in ("snapshot_retention_days", "snapshot_min_size_gb", "min_monthly_savings_usd"):
        val = getattr(rule, key, None)
        if val is not None:
            out[key] = val
    return out


def snapshot_lineage_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Inventory lineage fields for snapshot findings."""
    facts = snapshot.get("_technical_facts") or {}
    props = snapshot.get("properties") or {}
    out: dict[str, Any] = {}
    for key in ("sku", "provisioning_state", "disk_state", "source_disk_id", "incremental"):
        val = facts.get(key)
        if val is None:
            creation = props.get("creationData") or {}
            if key == "source_disk_id":
                val = creation.get("sourceResourceId")
            elif key == "incremental":
                val = creation.get("incremental")
            elif key == "disk_state":
                val = props.get("diskState") or props.get("DiskState")
            elif key == "provisioning_state":
                val = props.get("provisioningState") or props.get("ProvisioningState")
            elif key == "sku":
                row_sku = snapshot.get("sku")
                if isinstance(row_sku, dict):
                    val = row_sku.get("name")
                elif row_sku not in (None, ""):
                    val = row_sku
        if val not in (None, ""):
            out[key] = val
    return out

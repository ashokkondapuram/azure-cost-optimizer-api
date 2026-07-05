"""Batch resource snapshot upserts (1-E)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.focus_mapping import normalize_arm_id
from app.models import ResourceSnapshot

BATCH_SIZE = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot_mapping(
    subscription_id: str,
    *,
    resource_id: str,
    resource_name: str,
    resource_type: str,
    resource_group: str | None = None,
    location: str | None = None,
    sku: str | None = None,
    sku_json: dict | None = None,
    state: str | None = None,
    tags: dict | None = None,
    properties: dict | None = None,
    monthly_cost: float | None = None,
) -> dict[str, Any]:
    props = properties or {}
    return {
        "resource_id": normalize_arm_id(resource_id).lower(),
        "resource_name": resource_name,
        "resource_type": resource_type,
        "resource_group": resource_group,
        "location": location,
        "sku": sku,
        "sku_json": json.dumps(sku_json or {}),
        "state": state,
        "tags_json": json.dumps(tags or {}),
        "properties_json": json.dumps(props),
        "is_cost_export_only": props.get("source") == "cost_export",
        "monthly_cost_usd": float(monthly_cost or 0.0),
    }


def bulk_upsert_snapshots(
    db: Session,
    subscription_id: str,
    mappings: list[dict[str, Any]],
) -> int:
    """
    Upsert resource snapshots in batches of BATCH_SIZE.
    One SELECT per batch + in-memory merge (avoids per-row round-trips).
    """
    if not mappings:
        return 0

    sub = subscription_id.lower()
    now = _now()
    written = 0

    for offset in range(0, len(mappings), BATCH_SIZE):
        chunk = mappings[offset: offset + BATCH_SIZE]
        ids = [m["resource_id"] for m in chunk]
        existing_rows = (
            db.query(ResourceSnapshot)
            .filter(
                ResourceSnapshot.subscription_id == sub,
                ResourceSnapshot.resource_id.in_(ids),
            )
            .all()
        )
        by_rid = {r.resource_id: r for r in existing_rows}

        for m in chunk:
            rid = m["resource_id"]
            row = by_rid.get(rid)
            if row:
                row.resource_name = m["resource_name"]
                row.resource_type = m["resource_type"]
                row.resource_group = m.get("resource_group")
                row.location = m.get("location")
                row.sku = m.get("sku")
                row.sku_json = m.get("sku_json", "{}")
                row.state = m.get("state")
                row.tags_json = m.get("tags_json", "{}")
                row.properties_json = m.get("properties_json", "{}")
                row.is_cost_export_only = bool(m.get("is_cost_export_only"))
                if m.get("monthly_cost_usd") is not None:
                    row.monthly_cost_usd = m["monthly_cost_usd"]
                row.is_active = True
                row.synced_at = now
            else:
                db.add(ResourceSnapshot(
                    id=str(uuid.uuid4()),
                    subscription_id=sub,
                    resource_id=rid,
                    resource_name=m["resource_name"],
                    resource_type=m["resource_type"],
                    resource_group=m.get("resource_group"),
                    location=m.get("location"),
                    sku=m.get("sku"),
                    sku_json=m.get("sku_json", "{}"),
                    state=m.get("state"),
                    tags_json=m.get("tags_json", "{}"),
                    properties_json=m.get("properties_json", "{}"),
                    is_cost_export_only=bool(m.get("is_cost_export_only")),
                    monthly_cost_usd=float(m.get("monthly_cost_usd") or 0.0),
                    is_active=True,
                    synced_at=now,
                ))
            written += 1

    return written

"""Cost-first subscription resource type audit.

Joins ARM resource inventory with MTD cost-by-type data so discovery and
gap reports surface billable types first and skip free resources.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.cost_db import month_for_timeframe, _normalize_sub
from app.cost_explorer_sync import resource_type_display_name
from app.models import CostByResourceTypeSnapshot
from app.optimizer.component_map import CANONICAL_TO_COMPONENT
from app.azure_service_cost_catalog import classify_resource_type
from app.resource_cost_mapping import resource_cost_mapping_for_type
from app.resource_type_map import internal_resource_type, inventory_canonical_for_arm_type
from app.sync_scope import inventory_syncable_types


def load_mtd_cost_by_arm_type(
    db: Session,
    subscription_id: str,
    *,
    month: str | None = None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Return ``arm_type → {cost_usd, cost_billing, billing_currency, canonical}``."""
    sub = _normalize_sub(subscription_id)
    m = month or month_for_timeframe("MonthToDate")
    rows = (
        db.query(CostByResourceTypeSnapshot)
        .filter(
            CostByResourceTypeSnapshot.subscription_id == sub,
            CostByResourceTypeSnapshot.month == m,
        )
        .all()
    )
    if not rows:
        return {}, None

    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        arm = (row.arm_resource_type or "").strip().lower()
        if not arm:
            continue
        out[arm] = {
            "cost_usd": float(row.cost_usd or 0.0),
            "cost_billing": float(row.cost_billing if row.cost_billing is not None else row.cost_usd or 0.0),
            "billing_currency": row.billing_currency or "CAD",
            "canonical_resource_type": row.canonical_resource_type
            or internal_resource_type("", blob_resource_type=arm),
        }
    return out, rows[0].month if rows else m


def _mapping_status(arm_type: str, canonical: str | None) -> str:
    if canonical and canonical in inventory_syncable_types():
        return "synced"
    if canonical and not canonical.startswith("other/"):
        return "catalog_only"
    return "unmapped"


def _type_entry(
    arm_type: str,
    *,
    resource_count: int,
    cost: dict[str, Any] | None,
) -> dict[str, Any]:
    cost = cost or {}
    cost_usd = float(cost.get("cost_usd") or 0.0)
    cost_billing = float(cost.get("cost_billing") or 0.0)
    canonical = inventory_canonical_for_arm_type(arm_type) or cost.get("canonical_resource_type")
    if not canonical:
        canonical = internal_resource_type("", blob_resource_type=arm_type)
    status = _mapping_status(arm_type, inventory_canonical_for_arm_type(arm_type))
    ctype = (canonical or "").strip().lower()
    drivers = resource_cost_mapping_for_type(ctype).get("cost_drivers", []) if ctype else []
    classification = classify_resource_type(
        canonical_type=canonical or "",
        arm_type=arm_type,
        cost_mtd=cost_usd if cost_usd > 0 else cost_billing,
    )
    return {
        "arm_type": arm_type,
        "display_name": resource_type_display_name(arm_type, canonical),
        "resource_count": resource_count,
        "cost_usd": round(cost_usd, 2),
        "cost_billing": round(cost_billing, 2),
        "billing_currency": cost.get("billing_currency") or "CAD",
        "canonical_type": canonical,
        "component": CANONICAL_TO_COMPONENT.get(ctype),
        "status": status,
        "has_cost_drivers": bool(drivers),
        "cost_type": classification.cost_type,
        "is_cost_bearing": classification.cost_type != "free" and (
            cost_usd > 0
            or cost_billing > 0
            or (classification.cost_type == "costed" and resource_count > 0)
        ),
    }


def build_resource_cost_audit(
    arm_counts: Counter[str],
    cost_by_arm: dict[str, dict[str, Any]],
    *,
    month: str | None = None,
) -> dict[str, Any]:
    """Merge ARM inventory counts with MTD cost-by-type rows."""
    syncable = inventory_syncable_types()
    all_arms = set(arm_counts.keys()) | set(cost_by_arm.keys())

    cost_bearing: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    synced_cost: list[dict[str, Any]] = []
    free_unmapped: Counter[str] = Counter()
    free_unmapped_count = 0

    for arm in sorted(all_arms):
        count = int(arm_counts.get(arm, 0))
        cost = cost_by_arm.get(arm)
        entry = _type_entry(arm, resource_count=count, cost=cost)
        if not entry["is_cost_bearing"]:
            canonical = inventory_canonical_for_arm_type(arm)
            if not canonical and count:
                free_unmapped[arm] = count
                free_unmapped_count += count
            continue

        cost_bearing.append(entry)
        canonical = inventory_canonical_for_arm_type(arm)
        if canonical and canonical in syncable:
            synced_cost.append(entry)
        elif entry["status"] == "unmapped":
            gaps.append(entry)

    cost_bearing.sort(key=lambda row: (-row["cost_usd"], -row["resource_count"], row["arm_type"]))
    gaps.sort(key=lambda row: (-row["cost_usd"], -row["resource_count"], row["arm_type"]))
    synced_cost.sort(key=lambda row: (-row["cost_usd"], -row["resource_count"], row["arm_type"]))

    return {
        "month": month,
        "total_arm_types": len(all_arms),
        "cost_bearing_type_count": len(cost_bearing),
        "synced_cost_type_count": len(synced_cost),
        "gap_type_count": len(gaps),
        "free_skipped_unmapped_count": free_unmapped_count,
        "free_skipped_unmapped_types": dict(free_unmapped.most_common(50)),
        "cost_bearing_types": cost_bearing,
        "synced_cost_types": synced_cost,
        "gaps": gaps,
        "total_cost_usd": round(sum(row["cost_usd"] for row in cost_bearing), 2),
    }


def audit_from_arm_items(
    db: Session,
    subscription_id: str,
    arm_items: list[dict],
) -> dict[str, Any]:
    """Build a cost-first audit from ARM list API rows."""
    arm_counts: Counter[str] = Counter()
    for item in arm_items:
        arm = (item.get("type") or "").strip().lower()
        if arm:
            arm_counts[arm] += 1
    cost_by_arm, month = load_mtd_cost_by_arm_type(db, subscription_id)
    audit = build_resource_cost_audit(arm_counts, cost_by_arm, month=month)
    audit["subscription_id"] = subscription_id.strip().lower()
    audit["total_listed"] = len(arm_items)
    return audit


def audit_from_cost_db(db: Session, subscription_id: str) -> dict[str, Any]:
    """Cost-first audit using synced cost-by-type rows (no ARM list required)."""
    cost_by_arm, month = load_mtd_cost_by_arm_type(db, subscription_id)
    audit = build_resource_cost_audit(Counter(), cost_by_arm, month=month)
    audit["subscription_id"] = subscription_id.strip().lower()
    audit["total_listed"] = 0
    audit["source"] = "cost_by_resource_type"
    return audit

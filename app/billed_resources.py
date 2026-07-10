"""Billed resource listing — Azure inventory merged with Cost Management MTD costs."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import and_, func, not_, or_
from sqlalchemy.orm import Session, aliased

from app.arm_resource_probe import arm_type_from_id, resource_name_from_id
from app.cost_db import _latest_cost_by_resource_month, _resolve_resource_cost_month
from app.focus_mapping import normalize_arm_id
from app.models import CostByResourceSnapshot, ResourceSnapshot
from app.pagination import cached_total, slice_page
from app.perf_cache import cached_cost_map
from app.resource_store import (
    DEFAULT_RESOURCE_PAGE_SIZE,
    MAX_RESOURCE_PAGE_SIZE,
    _extract_rg_from_arm,
    _inventory_id_set,
    _is_cost_export_snapshot,
    rows_to_list,
)
from app.vm_utils import is_scale_set_instance

_COST_POSITIVE = or_(
    CostByResourceSnapshot.cost_billing > 0,
    CostByResourceSnapshot.cost_usd > 0,
)


def _resolve_billed_month(db: Session, subscription_id: str) -> str | None:
    month = _resolve_resource_cost_month(db, subscription_id, "MonthToDate", None)
    if month:
        return month
    return _latest_cost_by_resource_month(db, subscription_id)


def azure_status_for(cost_row: CostByResourceSnapshot | None, inv: ResourceSnapshot | None) -> str:
    """exists | missing | unknown"""
    if inv is not None:
        return "exists"
    if cost_row is not None and cost_row.azure_exists is False:
        return "missing"
    if cost_row is not None and cost_row.azure_exists is True:
        return "exists"
    return "unknown"


def _display_state_for_status(status: str, inv_state: str | None) -> str:
    if status == "missing":
        return "Doesn't exist on Azure"
    if inv_state:
        return inv_state
    if status == "unknown":
        return "—"
    return inv_state or "Synced"


def _apply_cost_to_row(row: dict, cost: CostByResourceSnapshot) -> dict:
    pretax = float(cost.cost_billing or 0.0)
    usd = float(cost.cost_usd or 0.0)
    row["monthlyCostBilling"] = pretax
    row["monthlyCostUsd"] = usd
    row["billingCurrency"] = cost.billing_currency or row.get("billingCurrency") or "CAD"
    row["hasMtdCost"] = pretax > 0 or usd > 0
    row["costPending"] = not row["hasMtdCost"]
    if cost.service_name:
        row["billingServiceName"] = cost.service_name
        if not row.get("azureServiceName"):
            row["azureServiceName"] = cost.service_name
    return row


def billed_row_from_inventory(
    inv: ResourceSnapshot,
    cost: CostByResourceSnapshot | None = None,
) -> dict:
    """Azure inventory row; cost overlay when Cost Management has caught up."""
    row = rows_to_list([inv])[0]
    row["azureStatus"] = "exists"
    row["inInventory"] = True
    row["costExportOnly"] = False
    row["hasMtdCost"] = False
    row["costPending"] = True
    if cost is not None:
        _apply_cost_to_row(row, cost)
    return row


def billed_row_from_cost(
    cost: CostByResourceSnapshot,
    inv: ResourceSnapshot | None,
) -> dict:
    """Cost Management row; enriched from inventory when synced."""
    rid = normalize_arm_id(cost.resource_id)
    status = azure_status_for(cost, inv)

    if inv is not None:
        row = billed_row_from_inventory(inv, cost)
        row["state"] = _display_state_for_status(status, row.get("state"))
        return row

    arm_type = cost.resource_type or arm_type_from_id(rid)
    row = {
        "id": rid,
        "name": resource_name_from_id(rid),
        "type": arm_type,
        "resourceGroup": cost.resource_group or _extract_rg_from_arm(rid),
        "location": None,
        "sku": None,
        "skuDetails": {},
        "state": None,
        "tags": {},
        "properties": {},
        "monthlyCostUsd": 0.0,
        "monthlyCostBilling": 0.0,
        "billingCurrency": cost.billing_currency or "CAD",
        "azureServiceName": cost.service_name,
        "syncedAt": None,
        "analysisFindingsCount": 0,
        "analysisSavingsUsd": 0,
        "analysisTopSeverity": None,
        "analysisUpdatedAt": None,
        "analysisSummary": [],
        "hasMtdCost": False,
        "costPending": False,
    }
    _apply_cost_to_row(row, cost)
    row["azureStatus"] = status
    row["inInventory"] = False
    row["costExportOnly"] = True
    row["state"] = _display_state_for_status(status, row.get("state"))
    return row


def _filter_inventory_batch(rows: list[ResourceSnapshot]) -> list[ResourceSnapshot]:
    """Drop cost-export stubs and VMSS instances from a small inventory batch."""
    kept: list[ResourceSnapshot] = []
    for row in rows:
        if getattr(row, "is_cost_export_only", False):
            continue
        try:
            props = json.loads(row.properties_json or "{}")
        except Exception:
            props = {}
        if _is_cost_export_snapshot(props):
            continue
        if row.resource_type == "compute/vm" and is_scale_set_instance(
            {"id": row.resource_id, "properties": props},
        ):
            continue
        kept.append(row)
    return kept


def _load_inventory_snapshots(db: Session, subscription_id: str) -> list[ResourceSnapshot]:
    """All Azure inventory rows from resource sync (excludes cost-export stubs)."""
    sub = subscription_id.lower()
    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.is_cost_export_only.is_(False),
        )
        .all()
    )
    return _filter_inventory_batch(rows)


def _cost_rows_query(db: Session, subscription_id: str, month: str):
    sub = subscription_id.lower()
    return (
        db.query(CostByResourceSnapshot)
        .filter(
            CostByResourceSnapshot.subscription_id == sub,
            CostByResourceSnapshot.month == month,
            _COST_POSITIVE,
        )
        .order_by(
            CostByResourceSnapshot.cost_billing.desc(),
            CostByResourceSnapshot.cost_usd.desc(),
            CostByResourceSnapshot.resource_id,
        )
    )


def _inventory_pending_query(db: Session, subscription_id: str, month: str):
    """Inventory rows with no positive MTD cost for the month."""
    sub = subscription_id.lower()
    cost = aliased(CostByResourceSnapshot)
    return (
        db.query(ResourceSnapshot)
        .outerjoin(
            cost,
            and_(
                ResourceSnapshot.resource_id == cost.resource_id,
                cost.subscription_id == sub,
                cost.month == month,
            ),
        )
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.is_cost_export_only.is_(False),
            not_(ResourceSnapshot.resource_id.ilike("%/virtualmachinescalesets/%/virtualmachines/%")),
            or_(
                cost.id.is_(None),
                and_(
                    func.coalesce(cost.cost_billing, 0) <= 0,
                    func.coalesce(cost.cost_usd, 0) <= 0,
                ),
            ),
        )
        .order_by(ResourceSnapshot.resource_name)
    )


def _count_billed_with_cost(db: Session, subscription_id: str, month: str) -> int:
    sub = subscription_id.lower()
    return (
        db.query(func.count(CostByResourceSnapshot.id))
        .filter(
            CostByResourceSnapshot.subscription_id == sub,
            CostByResourceSnapshot.month == month,
            _COST_POSITIVE,
        )
        .scalar()
        or 0
    )


def _count_inventory_pending_cost(db: Session, subscription_id: str, month: str) -> int:
    rows = _inventory_pending_query(db, subscription_id, month).all()
    return len(_filter_inventory_batch(rows))


def _billed_total(db: Session, subscription_id: str, month: str) -> int:
    sub = subscription_id.lower()
    return cached_total(
        f"billed_total:{sub}:{month}",
        lambda: _count_billed_with_cost(db, sub, month) + _count_inventory_pending_cost(db, sub, month),
        cache_fn=cached_cost_map,
    )


def _inventory_lookup(
    db: Session,
    subscription_id: str,
    resource_ids: list[str],
) -> dict[str, ResourceSnapshot]:
    if not resource_ids:
        return {}
    sub = subscription_id.lower()
    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.resource_id.in_(resource_ids),
        )
        .all()
    )
    out: dict[str, ResourceSnapshot] = {}
    for row in _filter_inventory_batch(rows):
        rid = normalize_arm_id(row.resource_id)
        if rid:
            out[rid] = row
    return out


def _fetch_cost_slice(
    db: Session,
    subscription_id: str,
    month: str,
    *,
    offset: int,
    limit: int,
) -> list[CostByResourceSnapshot]:
    return (
        _cost_rows_query(db, subscription_id, month)
        .offset(max(0, offset))
        .limit(limit)
        .all()
    )


def _fetch_inventory_pending_slice(
    db: Session,
    subscription_id: str,
    month: str,
    *,
    offset: int,
    limit: int,
) -> list[ResourceSnapshot]:
    rows = (
        _inventory_pending_query(db, subscription_id, month)
        .offset(max(0, offset))
        .limit(limit + 4)
        .all()
    )
    return _filter_inventory_batch(rows)[:limit]


def _cost_map_for_month(
    db: Session,
    subscription_id: str,
    month: str | None,
) -> dict[str, CostByResourceSnapshot]:
    if not month:
        return {}
    sub = subscription_id.lower()
    out: dict[str, CostByResourceSnapshot] = {}
    for cost in _cost_rows_query(db, subscription_id, month).all():
        rid = normalize_arm_id(cost.resource_id)
        if rid:
            out[rid] = cost
    return out


def _sort_key(row: dict[str, Any]) -> tuple:
    """Cost-bearing rows first (desc), then inventory awaiting cost (name)."""
    cost_val = max(
        float(row.get("monthlyCostBilling") or 0.0),
        float(row.get("monthlyCostUsd") or 0.0),
    )
    if row.get("hasMtdCost"):
        return (0, -cost_val, (row.get("name") or "").lower())
    return (1, 0, (row.get("name") or "").lower())


def merge_billed_resources(
    inventory: list[ResourceSnapshot],
    cost_map: dict[str, CostByResourceSnapshot],
) -> list[dict]:
    """
    Union of Azure inventory (resource fetch) and Cost Management MTD rows.

    - Inventory + cost → show cost
    - Inventory, no cost yet → show resource (cost pending)
    - Cost only, not in inventory → show cost; ARM probe on row click
    """
    merged: list[dict] = []
    seen: set[str] = set()

    for inv in inventory:
        rid = normalize_arm_id(inv.resource_id)
        if not rid or rid in seen:
            continue
        seen.add(rid)
        cost = cost_map.get(rid)
        if cost is not None:
            merged.append(billed_row_from_cost(cost, inv))
        else:
            merged.append(billed_row_from_inventory(inv))

    for rid, cost in cost_map.items():
        if rid in seen:
            continue
        merged.append(billed_row_from_cost(cost, None))

    merged.sort(key=_sort_key)
    return merged


def list_billed_resources_db(db: Session, subscription_id: str) -> list[dict]:
    """Inventory ∪ billed costs for the resolved MTD month."""
    month = _resolve_billed_month(db, subscription_id)
    inventory = _load_inventory_snapshots(db, subscription_id)
    cost_map = _cost_map_for_month(db, subscription_id, month)
    return merge_billed_resources(inventory, cost_map)


def list_billed_resources_page(
    db: Session,
    subscription_id: str,
    *,
    limit: int = DEFAULT_RESOURCE_PAGE_SIZE,
    offset: int = 0,
) -> dict:
    """Paginated inventory ∪ cost list — DB-level slices, no full in-memory merge."""
    sub = subscription_id.lower()
    month = _resolve_billed_month(db, subscription_id)
    limit = min(max(1, int(limit)), MAX_RESOURCE_PAGE_SIZE)
    offset = max(0, int(offset))

    n_cost = _count_billed_with_cost(db, sub, month) if month else 0
    n_pending = _count_inventory_pending_cost(db, sub, month) if month else 0
    total = n_cost + n_pending

    items: list[dict] = []
    want = limit + 1

    if month and offset < n_cost and want > 0:
        cost_rows = _fetch_cost_slice(
            db,
            sub,
            month,
            offset=offset,
            limit=min(want, n_cost - offset),
        )
        inv_lookup = _inventory_lookup(
            db,
            sub,
            [normalize_arm_id(c.resource_id) for c in cost_rows if c.resource_id],
        )
        for cost in cost_rows:
            rid = normalize_arm_id(cost.resource_id)
            items.append(billed_row_from_cost(cost, inv_lookup.get(rid)))
        want -= len(cost_rows)

    pending_offset = max(0, offset - n_cost)
    if month and want > 0 and pending_offset < n_pending:
        pending_rows = _fetch_inventory_pending_slice(
            db,
            sub,
            month,
            offset=pending_offset,
            limit=want,
        )
        for inv in pending_rows:
            items.append(billed_row_from_inventory(inv))

    page_items, has_more, page_count = slice_page(items, limit)

    return {
        "items": page_items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "page_count": page_count,
        "has_more": has_more,
        "month": month,
    }


def count_billed_resources(db: Session, subscription_id: str) -> int:
    """Merged list size: inventory + cost-only rows not in inventory."""
    month = _resolve_billed_month(db, subscription_id)
    if not month:
        return len(_load_inventory_snapshots(db, subscription_id))
    return _billed_total(db, subscription_id, month)


def reconcile_billed_azure_status(db: Session, subscription_id: str, month: str) -> int:
    """
    Mark azure_exists=True for billed rows that appear in inventory.
    Does not mark missing without an ARM probe (lazy).
    """
    from datetime import datetime, timezone

    sub = subscription_id.lower()
    inventory_ids = _inventory_id_set(db, sub)
    if not inventory_ids:
        return 0
    updated = 0
    now = datetime.now(timezone.utc)
    for row in (
        db.query(CostByResourceSnapshot)
        .filter(
            CostByResourceSnapshot.subscription_id == sub,
            CostByResourceSnapshot.month == month,
        )
        .all()
    ):
        rid = normalize_arm_id(row.resource_id)
        if rid and rid in inventory_ids:
            if row.azure_exists is not True:
                row.azure_exists = True
                row.azure_checked_at = now
                updated += 1
    return updated

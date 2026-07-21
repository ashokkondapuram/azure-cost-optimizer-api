"""DB-first resource reads for API list endpoints and dashboard counts."""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import and_, func, not_, or_
from sqlalchemy.orm import Session, load_only

from app.focus_mapping import normalize_arm_id
from app.service_display import azure_service_display_name
from app.resource_page_registry import COUNT_KEY_TO_CANONICAL
from app.resources.types import sku_text
from app.cost_db import (
    resource_cost_map_from_db,
    _resolve_cost_month,
    resource_cost_overlays_from_db,
)
from app.perf_cache import cached_cost_map, cached_resource_counts
from app.pagination import cached_total, decode_cursor, encode_cursor, page_envelope, slice_page
from app.inventory_filters import apply_inventory_exclusions
from app.inventory_standalone import (
    STANDALONE_INVENTORY_EXCLUDED,
    filter_standalone_inventory_rows,
    is_standalone_inventory_type,
)
from app.vm_utils import is_scale_set_instance
from app.models import CostByResourceSnapshot, CostByResourceTypeSnapshot
from .models import ResourceSnapshot

# Short API keys → resource_snapshots.resource_type
RESOURCE_COUNTS_KEYS: dict[str, str] = {
    "vms": "compute/vm",
    "disks": "compute/disk",
    "snapshots": "compute/snapshot",
    "aks": "containers/aks",
    "acr": "containers/acr",
    "storage": "storage/account",
    "publicips": "network/publicip",
    "vnets": "network/vnet",
    "nics": "network/nic",
    "natgateways": "network/nat",
    "loadbalancers": "network/loadbalancer",
    "appgateways": "network/appgateway",
    "nsgs": "network/nsg",
    "privateendpoints": "network/privateendpoint",
    "privatelinkservices": "network/privatelinkservice",
    "privatedns": "network/privatedns",
    "sql": "database/sql",
    "cosmosdb": "database/cosmosdb",
    "postgresql": "database/postgresql",
    "redis": "database/redis",
    "appservices": "appservice/webapp",
    "appserviceplans": "appservice/plan",
    "keyvaults": "security/keyvault",
    **COUNT_KEY_TO_CANONICAL,
    "cost_resources": "cost/all",
}

# Removed: PREFIX_COUNT_KEYS — each service type has its own count key via resource_page_registry.


def _inventory_id_set(db: Session, subscription_id: str) -> set[str]:
    from app.inventory_standalone import is_standalone_inventory_snapshot, standalone_inventory_snapshot_filter

    sub = subscription_id.lower()
    ids: set[str] = set()
    for row in (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.is_cost_export_only.is_(False),
            standalone_inventory_snapshot_filter(),
        )
        .all()
    ):
        if not is_standalone_inventory_snapshot(row):
            continue
        norm = normalize_arm_id(row.resource_id)
        if norm:
            ids.add(norm)
    return ids


def _is_cost_export_snapshot(props: dict) -> bool:
    return (props or {}).get("source") == "cost_export"


def _cost_map_for_subscription(db: Session, subscription_id: str, cost_map: dict[str, dict] | None) -> dict[str, dict]:
    if cost_map is not None:
        return cost_map
    return _subscription_cost_overlays(db, subscription_id)["mtd"]


def _subscription_cost_overlays(db: Session, subscription_id: str) -> dict[str, dict]:
    sub = subscription_id.lower()
    return cached_cost_map(
        f"cost_overlays:{sub}",
        lambda: resource_cost_overlays_from_db(db, sub),
    )


def list_cost_resources_db(db: Session, subscription_id: str) -> list[dict]:
    """Azure inventory merged with MTD costs (includes resources awaiting cost sync)."""
    from app.billed_resources import list_billed_resources_db

    return list_billed_resources_db(db, subscription_id)


def _filter_azure_inventory_rows(rows: list) -> list:
    """Drop snapshots created only from the cost export (not Azure inventory sync)."""
    from app.inventory_standalone import is_standalone_inventory_snapshot

    return [
        row for row in rows
        if not getattr(row, "is_cost_export_only", False)
        and is_standalone_inventory_snapshot(row)
    ]


def get_resources_by_type_prefix_db(
    db: Session,
    subscription_id: str,
    type_prefix: str,
) -> list[dict]:
    """List Azure inventory rows whose canonical type starts with type_prefix."""
    sub = subscription_id.lower()
    prefix = type_prefix if type_prefix.endswith("/") else f"{type_prefix}/"
    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.resource_type.like(f"{prefix}%"),
            ResourceSnapshot.is_cost_export_only.is_(False),
        )
        .order_by(ResourceSnapshot.resource_name)
        .all()
    )
    result = rows_to_list(_filter_azure_inventory_rows(rows))
    cost_map = resource_cost_map_from_db(db, subscription_id)
    return _apply_resource_costs(result, cost_map, db=db, subscription_id=subscription_id)


def _standalone_vm_sql_filter():
    """Exclude VMSS instance VMs that may still be stored as compute/vm."""
    return not_(
        ResourceSnapshot.resource_id.ilike("%/virtualmachinescalesets/%/virtualmachines/%")
    )


def _filter_standalone_vm_dicts(rows: list[dict]) -> list[dict]:
    return [row for row in rows if not is_scale_set_instance(row)]


def _row_dedupe_key(row: ResourceSnapshot) -> str:
    """Prefer logical identity (type + name + RG); AKS names are unique per subscription."""
    name = (row.resource_name or "").strip().lower()
    rtype = (row.resource_type or "").strip().lower()
    rg = (row.resource_group or "").strip().lower()
    if name and rtype:
        return f"{rtype}|{name}|{rg}"
    return (row.resource_id or "").strip().lower()


def _display_state(resource_type: str, state: str | None, props: dict) -> str:
    """Derive a display state from synced properties when the DB state column is empty."""
    text = (state or "").strip()
    if text:
        return text
    props = props or {}
    if resource_type == "compute/disk":
        return (props.get("diskState") or props.get("provisioningState") or "").strip()
    if resource_type == "compute/snapshot":
        from app.vm_uptime import parse_azure_datetime
        created = parse_azure_datetime(props.get("timeCreated") or props.get("TimeCreated"))
        if created:
            return created.isoformat()
        return (props.get("provisioningState") or "").strip()
    if resource_type == "compute/vm":
        power = props.get("powerState")
        if isinstance(power, str) and power:
            return power.split("/")[-1] if "/" in power else power
        statuses = ((props.get("instanceView") or {}).get("statuses") or [])
        for status in statuses:
            code = (status or {}).get("code") or ""
            if code.lower().startswith("powerstate/"):
                return code.split("/", 1)[-1]
        return (props.get("provisioningState") or "").strip()
    if resource_type == "compute/vmss":
        from app.vm_utils import vmss_operational_state_from_props

        return vmss_operational_state_from_props(props, state)
    if resource_type == "storage/account":
        return (props.get("accessTier") or props.get("provisioningState") or "").strip()
    if resource_type == "network/publicip":
        if props.get("ipConfiguration") in (None, {}):
            return "Unassociated"
        return (props.get("provisioningState") or "").strip()
    if resource_type == "network/nic":
        if not props.get("virtualMachine"):
            return "Unattached"
        return (props.get("provisioningState") or "").strip()
    if resource_type == "appservice/webapp":
        return (props.get("state") or props.get("provisioningState") or "").strip()
    if resource_type == "appservice/plan":
        return (props.get("status") or state or props.get("provisioningState") or "").strip()
    return (props.get("provisioningState") or props.get("state") or "").strip()


def rows_to_list(rows, *, include_properties: bool = True) -> list[dict]:
    deduped: dict[str, object] = {}
    for r in rows:
        key = _row_dedupe_key(r)
        if not key:
            continue
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = r
        elif r.synced_at and (not existing.synced_at or r.synced_at > existing.synced_at):
            deduped[key] = r

    result = []
    for r in deduped.values():
        props: dict = {}
        tags: dict = {}
        sku_details: dict = {}
        analysis_summary: list = []
        if include_properties:
            try:
                props = json.loads(r.properties_json or "{}")
                tags = json.loads(r.tags_json or "{}")
                sku_details = json.loads(r.sku_json or "{}")
                analysis_summary = json.loads(r.analysis_summary_json or "[]")
            except Exception:
                props, tags, sku_details, analysis_summary = {}, {}, {}, []
        row = {
            "id": r.resource_id,
            "name": r.resource_name,
            "type": r.resource_type,
            "resourceGroup": r.resource_group,
            "location": r.location,
            "sku": sku_text(r.sku) or r.sku,
            "state": _display_state(r.resource_type, r.state, props if include_properties else {}),
            "monthlyCostUsd": r.monthly_cost_usd,
            "monthlyCostBilling": r.monthly_cost_billing,
            "billingCurrency": r.billing_currency or "CAD",
            "azureServiceName": azure_service_display_name(
                azure_service_name=r.azure_service_name,
                canonical_type=r.resource_type,
                resource_id=r.resource_id,
            ),
            "syncedAt": r.synced_at.isoformat() if r.synced_at else None,
            "analysisFindingsCount": r.analysis_findings_count or 0,
            "analysisSavingsUsd": r.analysis_savings_usd or 0,
            "analysisTopSeverity": r.analysis_top_severity,
            "analysisUpdatedAt": r.analysis_updated_at.isoformat() if r.analysis_updated_at else None,
        }
        if include_properties:
            row.update({
                "skuDetails": sku_details,
                "tags": tags,
                "properties": props,
                "analysisSummary": analysis_summary,
            })
        result.append(row)
    return result


def apply_costs_to_resources(
    rows: list[dict],
    cost_map: dict[str, dict],
    *,
    lifetime_map: dict[str, dict] | None = None,
    mom_map: dict[str, dict] | None = None,
    db: Session | None = None,
) -> list[dict]:
    """Overlay MTD, lifetime, trend, and retail costs onto resource list rows."""
    from app.cost_utils import (
        attach_cost_envelope_to_row,
        build_resource_cost_envelope,
        monthly_cost_amounts_from_entry,
        monthly_cost_amounts_from_row,
        resolve_cost_map_entry,
    )
    from app.resource_retail_cost import estimate_resource_retail_monthly

    price_cache: dict[str, dict] = {}
    for row in rows:
        rid = normalize_arm_id(row.get("id") or row.get("resource_id") or "")
        snap_billing, snap_usd = monthly_cost_amounts_from_row(row)
        detail = resolve_cost_map_entry(cost_map, rid) if rid and cost_map else None
        billing = snap_billing
        usd = snap_usd
        currency = row.get("billingCurrency") or row.get("billing_currency") or "CAD"
        if detail:
            pretax, detail_usd, detail_currency = monthly_cost_amounts_from_entry(detail)
            if pretax > 0 or detail_usd > 0:
                billing = pretax
                usd = detail_usd
                currency = detail_currency or currency
                row["monthlyCostBilling"] = pretax
                row["monthlyCostUsd"] = detail_usd
                row["billingCurrency"] = currency
                if detail.get("service_name"):
                    row["billingServiceName"] = detail["service_name"]
                    props = row.get("properties") or {}
                    if props.get("source") == "cost_export":
                        row["azureServiceName"] = detail["service_name"]
            elif snap_billing > 0 or snap_usd > 0:
                row["monthlyCostBilling"] = snap_billing
                row["monthlyCostUsd"] = snap_usd
        elif snap_billing > 0 or snap_usd > 0:
            row["monthlyCostBilling"] = snap_billing
            row["monthlyCostUsd"] = snap_usd

        if rid and lifetime_map:
            lifetime = resolve_cost_map_entry(lifetime_map, rid)
            if lifetime:
                lt_pretax, lt_usd, lt_currency = monthly_cost_amounts_from_entry(lifetime)
                if lt_pretax > 0 or lt_usd > 0:
                    row["totalCostBilling"] = lt_pretax
                    row["totalCostUsd"] = lt_usd
                    if lt_currency:
                        row["billingCurrency"] = lt_currency
                        currency = lt_currency
        if rid and mom_map:
            mom = resolve_cost_map_entry(mom_map, rid)
            if mom and mom.get("billing_delta") is not None:
                row["costTrendBilling"] = float(mom["billing_delta"])

        existing_cost = row.get("cost") if isinstance(row.get("cost"), dict) else {}
        retail_monthly = row.get("retailMonthly") or row.get("retail_monthly") or existing_cost.get("retail_monthly")
        retail_currency = row.get("retailCurrency") or row.get("retail_currency") or existing_cost.get("retail_currency")
        retail_source = row.get("retailSource") or row.get("retail_source") or existing_cost.get("retail_source")
        retail_pending = existing_cost.get("retail_pending")
        if retail_monthly is None and not retail_source:
            retail_payload = estimate_resource_retail_monthly(row, db, price_cache=price_cache)
            retail_monthly = retail_payload.get("retail_monthly")
            retail_currency = retail_payload.get("retail_currency") or currency
            retail_source = retail_payload.get("retail_source")
            retail_pending = retail_payload.get("retail_pending")

        envelope = build_resource_cost_envelope(
            billing=billing,
            usd=usd,
            currency=currency,
            retail_monthly=float(retail_monthly) if retail_monthly is not None else None,
            retail_currency=str(retail_currency) if retail_currency else currency,
            retail_source=str(retail_source) if retail_source else None,
            retail_pending=bool(retail_pending) if retail_pending is not None else retail_monthly is None,
            cost_pending=not (billing > 0 or usd > 0),
        )
        attach_cost_envelope_to_row(row, envelope)
    return rows


def enrich_resource_row_costs(
    row: dict,
    db: Session,
    subscription_id: str,
    *,
    cost_map: dict[str, dict] | None = None,
) -> dict:
    """Overlay MTD, lifetime, and trend costs onto a single inventory row."""
    enriched = _apply_resource_costs([row], cost_map, db=db, subscription_id=subscription_id)
    return enriched[0] if enriched else row


def drawer_cost_fields(row: dict[str, Any] | None) -> dict[str, Any]:
    """Slim cost block for drawer batch-lookup payloads."""
    if not row:
        return {}
    keys = (
        "monthlyCostBilling",
        "monthlyCostUsd",
        "totalCostBilling",
        "totalCostUsd",
        "costTrendBilling",
        "billingCurrency",
        "billingServiceName",
        "retailMonthly",
        "retailCurrency",
        "retailSource",
        "costPending",
        "retailPending",
        "cost",
    )
    return {key: row[key] for key in keys if row.get(key) is not None}


def _apply_resource_costs(
    rows: list[dict],
    cost_map: dict[str, dict],
    *,
    db: Session | None = None,
    subscription_id: str | None = None,
) -> list[dict]:
    overlays = None
    if db is not None and subscription_id:
        overlays = _subscription_cost_overlays(db, subscription_id)
    mtd = cost_map if cost_map is not None else (overlays or {}).get("mtd", {})
    return apply_costs_to_resources(
        rows,
        mtd,
        lifetime_map=(overlays or {}).get("lifetime"),
        mom_map=(overlays or {}).get("mom"),
        db=db,
    )


def _aks_row_score(row: dict) -> int:
    """Prefer rows with richer AKS metadata when deduping."""
    props = row.get("properties") or {}
    pools = props.get("agentPoolProfiles") or []
    pool_nodes = sum((p.get("count") or 0) for p in pools)
    score = len(pools) * 100 + pool_nodes
    if row.get("state"):
        score += 10
    if row.get("sku"):
        score += 5
    if row.get("syncedAt"):
        score += 1
    return score


def get_aks_clusters_db(db: Session, subscription_id: str) -> list[dict]:
    """AKS list with name-based dedupe and row-field enrichment for the UI."""
    rows = get_resources_db(
        db, subscription_id, "containers/aks",
        include_properties=True,
        unpaginated=True,
    )
    by_name: dict[str, dict] = {}
    for row in rows:
        name_key = (row.get("name") or "").strip().lower()
        id_key = (row.get("id") or "").strip().lower()
        key = name_key or id_key
        if not key:
            continue
        props = dict(row.get("properties") or {})
        if row.get("state") and not props.get("powerState"):
            code = row["state"]
            if code and not str(code).startswith("PowerState/"):
                code = f"PowerState/{code}"
            props["powerState"] = {"code": code}
        if row.get("sku") and not props.get("sku"):
            props["sku"] = {"name": row["sku"], "tier": row["sku"]}
        row["properties"] = props
        if not row.get("resourceGroup") and row.get("id"):
            row["resourceGroup"] = _extract_rg_from_arm(row["id"])

        existing = by_name.get(key)
        if existing is None or _aks_row_score(row) > _aks_row_score(existing):
            by_name[key] = row
    return sorted(by_name.values(), key=lambda r: (r.get("name") or "").lower())


def _extract_rg_from_arm(resource_id: str) -> str:
    try:
        parts = resource_id.split("/")
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except Exception:
        return ""


def _not_cost_export_sql():
    """Exclude rows created only from the cost export blob."""
    return ResourceSnapshot.is_cost_export_only.is_(False)


_LIST_LOAD_ONLY = (
    ResourceSnapshot.id,
    ResourceSnapshot.subscription_id,
    ResourceSnapshot.resource_id,
    ResourceSnapshot.resource_name,
    ResourceSnapshot.resource_type,
    ResourceSnapshot.resource_group,
    ResourceSnapshot.location,
    ResourceSnapshot.sku,
    ResourceSnapshot.state,
    ResourceSnapshot.monthly_cost_usd,
    ResourceSnapshot.monthly_cost_billing,
    ResourceSnapshot.billing_currency,
    ResourceSnapshot.azure_service_name,
    ResourceSnapshot.is_active,
    ResourceSnapshot.is_cost_export_only,
    ResourceSnapshot.synced_at,
    ResourceSnapshot.analysis_findings_count,
    ResourceSnapshot.analysis_savings_usd,
    ResourceSnapshot.analysis_top_severity,
    ResourceSnapshot.analysis_updated_at,
)


def _apply_list_query_options(query, *, include_properties: bool):
    if include_properties:
        return query
    return query.options(load_only(*_LIST_LOAD_ONLY))


DEFAULT_RESOURCE_PAGE_SIZE = 50
MAX_RESOURCE_PAGE_SIZE = 200


def get_resources_db(
    db: Session,
    subscription_id: str,
    resource_type: str,
    *,
    cost_map: dict[str, dict] | None = None,
    include_properties: bool = False,
    limit: int | None = None,
    offset: int = 0,
    unpaginated: bool = False,
) -> list[dict]:
    subscription_id = subscription_id.lower()
    if not is_standalone_inventory_type(resource_type):
        return []
    filters = (
        ResourceSnapshot.subscription_id == subscription_id,
        ResourceSnapshot.resource_type == resource_type,
        ResourceSnapshot.is_active.is_(True),
        _not_cost_export_sql(),
        *([_standalone_vm_sql_filter()] if resource_type == "compute/vm" else []),
    )
    query = (
        db.query(ResourceSnapshot)
        .filter(*filters)
        .order_by(ResourceSnapshot.resource_name)
    )
    query = _apply_list_query_options(query, include_properties=include_properties)
    if not unpaginated:
        page_limit = min(max(1, int(limit or MAX_RESOURCE_PAGE_SIZE)), MAX_RESOURCE_PAGE_SIZE)
        query = query.offset(max(0, int(offset))).limit(page_limit)
    rows = query.all()
    result = rows_to_list(rows, include_properties=include_properties)
    if resource_type == "compute/vm":
        result = _filter_standalone_vm_dicts(result)
    cost_map = _cost_map_for_subscription(db, subscription_id, cost_map)
    result = _apply_resource_costs(result, cost_map, db=db, subscription_id=subscription_id)
    from app.resource_enrichment import overlay_list_rows_from_enrichment

    return overlay_list_rows_from_enrichment(db, subscription_id, result)


def get_resources_db_page(
    db: Session,
    subscription_id: str,
    resource_type: str,
    *,
    limit: int = DEFAULT_RESOURCE_PAGE_SIZE,
    offset: int = 0,
    cursor: str | None = None,
    cost_map: dict[str, dict] | None = None,
    include_properties: bool = False,
) -> dict:
    """Paginated inventory read for list endpoints (offset or keyset cursor)."""
    subscription_id = subscription_id.lower()
    if not is_standalone_inventory_type(resource_type):
        return page_envelope(
            [],
            total=0,
            limit=limit,
            offset=offset,
            has_more=False,
            page_count=0,
            next_cursor=None,
            recommended_page_size=DEFAULT_RESOURCE_PAGE_SIZE,
            max_page_size=MAX_RESOURCE_PAGE_SIZE,
        )
    limit = min(max(1, int(limit)), MAX_RESOURCE_PAGE_SIZE)
    offset = max(0, int(offset))
    cursor_text = (cursor or "").strip() or None

    filters = (
        ResourceSnapshot.subscription_id == subscription_id,
        ResourceSnapshot.resource_type == resource_type,
        ResourceSnapshot.is_active.is_(True),
        _not_cost_export_sql(),
        *([_standalone_vm_sql_filter()] if resource_type == "compute/vm" else []),
    )
    total = cached_total(
        f"inv_total:{subscription_id}:{resource_type}",
        lambda: db.query(func.count(ResourceSnapshot.id)).filter(*filters).scalar() or 0,
        cache_fn=cached_cost_map,
    )
    query = (
        db.query(ResourceSnapshot)
        .filter(*filters)
        .order_by(ResourceSnapshot.resource_name, ResourceSnapshot.resource_id)
    )
    if cursor_text:
        decoded = decode_cursor(cursor_text)
        if decoded:
            cname, cid = decoded
            query = query.filter(
                or_(
                    ResourceSnapshot.resource_name > cname,
                    and_(
                        ResourceSnapshot.resource_name == cname,
                        ResourceSnapshot.resource_id > cid,
                    ),
                ),
            )
    else:
        query = query.offset(offset)
    query = query.limit(limit + 1)
    query = _apply_list_query_options(query, include_properties=include_properties)
    rows = query.all()
    page_rows, has_more, page_count = slice_page(rows, limit)
    items = rows_to_list(page_rows, include_properties=include_properties)
    if resource_type == "compute/vm":
        items = _filter_standalone_vm_dicts(items)
    cost_map = _cost_map_for_subscription(db, subscription_id, cost_map)
    items = _apply_resource_costs(items, cost_map, db=db, subscription_id=subscription_id)
    from app.resource_enrichment import overlay_list_rows_from_enrichment

    items = overlay_list_rows_from_enrichment(db, subscription_id, items)
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(last.get("name") or last.get("resource_name") or "", last.get("id") or "")
    effective_offset = offset if not cursor_text else offset + page_count
    return page_envelope(
        items,
        total=total,
        limit=limit,
        offset=effective_offset,
        has_more=has_more,
        page_count=page_count,
        next_cursor=next_cursor,
        recommended_page_size=DEFAULT_RESOURCE_PAGE_SIZE,
        max_page_size=MAX_RESOURCE_PAGE_SIZE,
    )


def get_resource_counts(db: Session, subscription_id: str) -> dict:
    """Dashboard counts: Azure inventory + billed resources with MTD cost."""
    sub = subscription_id.lower()
    return cached_resource_counts(f"counts:{sub}", lambda: _get_resource_counts_uncached(db, sub))


def _get_resource_counts_uncached(db: Session, subscription_id: str) -> dict:
    inventory_rows = (
        db.query(
            ResourceSnapshot.resource_id,
            ResourceSnapshot.resource_type,
            ResourceSnapshot.properties_json,
        )
        .filter(
            ResourceSnapshot.subscription_id == subscription_id,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.is_cost_export_only.is_(False),
        )
        .all()
    )
    inventory_ids: set[str] = set()
    inv_by_type: dict[str, int] = {}
    for rid, rtype, props_json in inventory_rows:
        try:
            props = json.loads(props_json or "{}")
        except Exception:
            props = {}
        if _is_cost_export_snapshot(props):
            continue
        if rtype == "compute/vm" and is_scale_set_instance({"id": rid, "properties": props}):
            continue
        if not is_standalone_inventory_type(rtype):
            continue
        norm = normalize_arm_id(rid)
        if norm:
            inventory_ids.add(norm)
        inv_by_type[rtype] = inv_by_type.get(rtype, 0) + 1

    findings_by_type: dict[str, int] = {}
    findings_rows = (
        db.query(
            ResourceSnapshot.resource_type,
            func.coalesce(func.sum(ResourceSnapshot.analysis_findings_count), 0),
        )
        .filter(
            ResourceSnapshot.subscription_id == subscription_id,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.is_cost_export_only.is_(False),
        )
        .group_by(ResourceSnapshot.resource_type)
        .all()
    )
    for rtype, cnt in findings_rows:
        findings_by_type[rtype] = int(cnt or 0)

    cost_billed = 0
    month = _resolve_cost_month(db, subscription_id, "MonthToDate", None)
    if month or inventory_ids:
        from app.billed_resources import count_billed_resources

        cost_billed = count_billed_resources(db, subscription_id)

    cost_by_count_key: dict[str, float] = {}
    if month:
        from app.resource_type_map import internal_resource_type

        canonical_to_count_key = {
            rtype: key
            for key, rtype in RESOURCE_COUNTS_KEYS.items()
            if rtype != "cost/all"
        }

        type_rows = (
            db.query(CostByResourceTypeSnapshot)
            .filter(
                CostByResourceTypeSnapshot.subscription_id == subscription_id,
                CostByResourceTypeSnapshot.month == month,
            )
            .all()
        )
        for row in type_rows:
            canonical = (
                row.canonical_resource_type
                or internal_resource_type("", blob_resource_type=row.arm_resource_type or "")
            )
            key = canonical_to_count_key.get((canonical or "").strip().lower())
            if not key:
                continue
            billing = float(row.cost_billing if row.cost_billing is not None else 0.0)
            usd = float(row.cost_usd or 0.0)
            amount = billing if billing > 0 else usd
            cost_by_count_key[key] = cost_by_count_key.get(key, 0.0) + amount

    breakdown: dict[str, dict[str, int | float | bool | str]] = {}
    counts: dict[str, int] = {}
    from app.azure_service_cost_catalog import classify_resource_type

    for key, rtype in RESOURCE_COUNTS_KEYS.items():
        if rtype == "cost/all":
            continue
        inv = inv_by_type.get(rtype, 0)
        cost_mtd = round(cost_by_count_key.get(key, 0.0), 2)
        findings_count = int(findings_by_type.get(rtype, 0) or 0)
        classification = classify_resource_type(canonical_type=rtype, cost_mtd=cost_mtd)
        visible = cost_mtd > 0 or findings_count > 0
        counts[key] = inv
        breakdown[key] = {
            "inventory": inv,
            "total": inv,
            "cost_mtd": cost_mtd,
            "findings_count": findings_count,
            "cost_type": classification.cost_type,
            "has_cost": visible,
        }

    counts["cost_resources"] = cost_billed
    counts["inventory_total"] = len(inventory_ids)
    counts["cost_bearing_inventory"] = sum(
        int(breakdown[key].get("inventory") or 0)
        for key in breakdown
        if breakdown[key].get("has_cost")
    )
    counts["breakdown"] = breakdown
    return counts


def list_resources_by_types_db(
    db: Session,
    subscription_id: str,
    resource_types: list[str],
    *,
    global_config: dict | None = None,
    include_costs: bool = True,
) -> list[dict]:
    """Load only selected canonical resource types (memory-efficient batch analysis)."""
    if not resource_types:
        return []
    sub = subscription_id.lower()
    types = list({t.strip().lower() for t in resource_types if t})
    q = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.is_cost_export_only.is_(False),
            ResourceSnapshot.resource_type.in_(types),
        )
    )
    q = apply_inventory_exclusions(q, global_config)
    rows = q.order_by(ResourceSnapshot.resource_name).all()
    result = rows_to_list(_filter_azure_inventory_rows(rows))
    if not include_costs:
        return result
    cost_map = resource_cost_map_from_db(db, subscription_id)
    return _apply_resource_costs(result, cost_map, db=db, subscription_id=subscription_id)


def list_resources_by_types_parallel(
    subscription_id: str,
    resource_types: list[str],
    *,
    global_config: dict | None = None,
    max_workers: int = 8,
) -> list[dict]:
    """Load resource types in parallel (one query per type, separate DB sessions)."""
    from concurrent.futures import ThreadPoolExecutor

    from app.database import SessionLocal

    types = sorted({t.strip().lower() for t in (resource_types or []) if t})
    if not types:
        return []
    if len(types) == 1:
        db = SessionLocal()
        try:
            return list_resources_by_types_db(
                db, subscription_id, types, global_config=global_config, include_costs=False,
            )
        finally:
            db.close()

    workers = min(max_workers, len(types))

    def _load_one(rtype: str) -> list[dict]:
        db = SessionLocal()
        try:
            return list_resources_by_types_db(
                db, subscription_id, [rtype], global_config=global_config, include_costs=False,
            )
        finally:
            db.close()

    merged: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for chunk in pool.map(_load_one, types):
            merged.extend(chunk)
    return merged


def list_all_resources_db(
    db: Session,
    subscription_id: str,
    resource_type: Optional[str] = None,
    *,
    global_config: dict | None = None,
) -> list[dict]:
    q = db.query(ResourceSnapshot).filter(
        ResourceSnapshot.subscription_id == subscription_id,
        ResourceSnapshot.is_active.is_(True),
        ResourceSnapshot.is_cost_export_only.is_(False),
    )
    if resource_type:
        q = q.filter(ResourceSnapshot.resource_type == resource_type)
    q = apply_inventory_exclusions(q, global_config)
    rows = q.order_by(ResourceSnapshot.resource_type, ResourceSnapshot.resource_name).all()
    result = rows_to_list(_filter_azure_inventory_rows(rows))
    cost_map = resource_cost_map_from_db(db, subscription_id)
    return _apply_resource_costs(result, cost_map, db=db, subscription_id=subscription_id)

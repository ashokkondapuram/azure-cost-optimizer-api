"""Upsert and read helpers for per-type ``resource_enrichment_*`` tables."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.assessment.normalizer import (
    build_cost_block,
    build_resource_block,
    resource_row_to_dict,
)
from app.cost_db import resource_cost_map_from_db
from app.data_store.enrichment_registry import (
    ensure_enrichment_table,
    get_enrichment_model,
    has_enrichment_table,
    iter_existing_enrichment_models,
    resolve_canonical_type,
)
from app.focus_mapping import normalize_arm_id
from app.models import CostByResourceSnapshot, ResourceSnapshot

_NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


def _safe_enrichment_read(db: Session, read_fn):
    """Return enrichment read result, or None when table/row is unavailable."""
    try:
        return read_fn()
    except (ProgrammingError, OperationalError):
        db.rollback()
        return None


def _parse_json(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


def _dump_json(value: Any) -> str:
    return json.dumps(value if value is not None else {})


def _strip_heavy_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    slim = dict(payload)
    slim.pop("metrics_raw", None)
    return slim


def _canonical_for_arm(
    db: Session,
    subscription_id: str,
    arm_id: str,
) -> str | None:
    sub = subscription_id.strip().lower()
    rid = normalize_arm_id(arm_id)
    snap = (
        db.query(ResourceSnapshot.resource_type)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            func.lower(ResourceSnapshot.resource_id) == rid,
            ResourceSnapshot.is_active.is_(True),
        )
        .first()
    )
    if not snap:
        return None
    return resolve_canonical_type(snap[0])


def get_enrichment_row(
    db: Session,
    subscription_id: str,
    arm_id: str,
    *,
    canonical_type: str | None = None,
) -> Any | None:
    sub = subscription_id.strip().lower()
    rid = normalize_arm_id(arm_id)
    ct = canonical_type or _canonical_for_arm(db, sub, rid)
    if not ct:
        return None
    bind = db.get_bind()
    if not has_enrichment_table(bind, ct):
        return None
    model = get_enrichment_model(ct)

    def _query():
        return (
            db.query(model)
            .filter(
                model.subscription_id == sub,
                model.arm_id == rid,
            )
            .first()
        )

    return _safe_enrichment_read(db, _query)


def get_enrichment_by_snapshot_id(
    db: Session,
    snapshot_id: str,
    *,
    canonical_type: str | None = None,
) -> Any | None:
    snap = db.query(ResourceSnapshot).filter(ResourceSnapshot.id == snapshot_id).first()
    if not snap:
        return None
    ct = canonical_type or resolve_canonical_type(snap.resource_type)
    model = get_enrichment_model(ct)
    return (
        db.query(model)
        .filter(model.resource_id == snapshot_id)
        .first()
    )


def load_enrichment_dict(
    row: Any,
    *,
    canonical_type: str = "",
    db: Session | None = None,
    assessment_flat: dict[str, str] | None = None,
    assessment_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    props = _parse_json(row.properties_json, {})
    flat = assessment_flat
    rows = assessment_rows
    if flat is None and db is not None:
        from app.data_store.enrichment_properties import (
            load_property_value_rows,
            property_values_to_properties_dict,
        )

        ct = canonical_type or props.get("canonical_type") or ""
        rows = load_property_value_rows(
            db,
            row.subscription_id,
            row.arm_id,
            canonical_type=ct or None,
        )
        flat = property_values_to_properties_dict(rows) if rows else {}
    if flat is None:
        cached = props.get("assessment_properties") or {}
        if isinstance(cached, dict) and cached.get("flat"):
            flat = cached.get("flat") or {}
            rows = cached.get("rows") or rows
        else:
            flat = {}
    arm_props = props.get("properties") if isinstance(props.get("properties"), dict) else {}
    if not arm_props:
        nested = _parse_json(row.properties_json, {})
        arm_props = nested.get("properties") if isinstance(nested.get("properties"), dict) else {}
    return {
        "id": row.id,
        "resource_id": row.resource_id,
        "arm_id": row.arm_id,
        "canonical_type": canonical_type,
        "subscription_id": row.subscription_id,
        "properties": arm_props,
        "assessment_properties": flat or {},
        "assessment_property_rows": rows or [],
        "metrics": _parse_json(row.metrics_json, {}),
        "cost": _parse_json(row.cost_json, {}),
        "recommendations": _parse_json(row.recommendations_json, {}),
        "enriched_at": row.enriched_at,
        "metrics_at": row.metrics_at,
        "cost_at": row.cost_at,
        "analysis_at": row.analysis_at,
    }


def load_enrichment_batch(
    db: Session,
    subscription_id: str,
    arm_ids: list[str],
) -> dict[str, dict[str, Any]]:
    from app.data_store.enrichment_properties import load_property_values_map

    sub = subscription_id.strip().lower()
    ids = sorted({normalize_arm_id(rid) for rid in arm_ids if rid})
    if not ids:
        return {}

    snapshots = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            func.lower(ResourceSnapshot.resource_id).in_(ids),
        )
        .all()
    )
    by_type: dict[str, list[str]] = {}
    type_by_arm: dict[str, str] = {}
    for snap in snapshots:
        ct = resolve_canonical_type(snap.resource_type)
        by_type.setdefault(ct, []).append(normalize_arm_id(snap.resource_id))
        type_by_arm[normalize_arm_id(snap.resource_id)] = ct

    out: dict[str, dict[str, Any]] = {}
    bind = db.get_bind()
    for ct, type_arm_ids in by_type.items():
        if not has_enrichment_table(bind, ct):
            continue
        model = get_enrichment_model(ct)
        prop_maps = load_property_values_map(db, sub, type_arm_ids, canonical_type=ct)

        def _query(model=model, type_arm_ids=type_arm_ids):
            return (
                db.query(model)
                .filter(
                    model.subscription_id == sub,
                    model.arm_id.in_(type_arm_ids),
                )
                .all()
            )

        rows = _safe_enrichment_read(db, _query) or []
        for row in rows:
            arm_key = (row.arm_id or "").lower()
            out[arm_key] = load_enrichment_dict(
                row,
                canonical_type=ct,
                assessment_flat=prop_maps.get(arm_key),
            )
    return out


def _get_or_create_enrichment(
    db: Session,
    snapshot: ResourceSnapshot,
) -> Any:
    canonical = resolve_canonical_type(snapshot.resource_type)
    ensure_enrichment_table(db.get_bind(), canonical)
    model = get_enrichment_model(canonical)
    sub = (snapshot.subscription_id or "").lower()
    arm_id = normalize_arm_id(snapshot.resource_id)
    db.flush()
    row = (
        db.query(model)
        .filter(
            model.subscription_id == sub,
            model.arm_id == arm_id,
        )
        .first()
    )
    if row:
        row.resource_id = snapshot.id
        return row
    row = model(
        id=str(uuid.uuid4()),
        resource_id=snapshot.id,
        arm_id=arm_id,
        subscription_id=sub,
        properties_json="{}",
        metrics_json="{}",
        cost_json="{}",
        recommendations_json="{}",
        created_at=_NOW(),
        updated_at=_NOW(),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        row = (
            db.query(model)
            .filter(
                model.subscription_id == sub,
                model.arm_id == arm_id,
            )
            .first()
        )
        if not row:
            raise
    row.resource_id = snapshot.id
    return row


def _properties_payload(snapshot: ResourceSnapshot) -> dict[str, Any]:
    row_dict = resource_row_to_dict(snapshot)
    return {
        "resource": build_resource_block(row_dict),
        "properties": row_dict.get("properties") or {},
        "tags": row_dict.get("tags") or {},
        "sku": row_dict.get("sku"),
        "state": row_dict.get("state"),
        "synced_at": (
            row_dict["synced_at"].isoformat()
            if row_dict.get("synced_at") is not None
            else None
        ),
    }


def _normalize_cost_overlay(overlay: dict[str, Any] | None) -> dict[str, Any]:
    if not overlay:
        return {}
    out = dict(overlay)
    if "usd" in overlay and "cost_usd" not in out:
        out["cost_usd"] = overlay["usd"]
    if "pretax" in overlay and "cost_billing" not in out:
        out["cost_billing"] = overlay["pretax"]
    if "currency" in overlay and "billing_currency" not in out:
        out["billing_currency"] = overlay["currency"]
    return out


def _cost_payload(
    snapshot: ResourceSnapshot,
    *,
    cost_overlay: dict[str, Any] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    from app.cost_utils import finalize_cost_block
    from app.resource_retail_cost import estimate_resource_retail_monthly

    row_dict = resource_row_to_dict(snapshot)
    payload = build_cost_block(row_dict)
    if cost_overlay:
        payload.update(_normalize_cost_overlay(cost_overlay))
    retail = estimate_resource_retail_monthly({
        "type": snapshot.resource_type,
        "canonical_type": resolve_canonical_type(snapshot.resource_type),
        "location": snapshot.location,
        "sku": snapshot.sku,
        "billingCurrency": snapshot.billing_currency,
        "properties": row_dict.get("properties") or {},
        "monthlyCostBilling": payload.get("monthly_cost_billing"),
    }, db)
    payload.update(retail)
    return finalize_cost_block(payload)


def upsert_properties(
    db: Session,
    snapshot: ResourceSnapshot,
) -> Any:
    from app.data_store.enrichment_properties import (
        load_property_value_rows,
        property_values_to_properties_dict,
        upsert_property_values,
    )

    row = _get_or_create_enrichment(db, snapshot)
    canonical = resolve_canonical_type(snapshot.resource_type)
    upsert_property_values(db, snapshot, canonical_type=canonical)
    payload = _properties_payload(snapshot)
    prop_rows = load_property_value_rows(
        db,
        snapshot.subscription_id,
        snapshot.resource_id,
        canonical_type=canonical,
    )
    payload["assessment_properties"] = {
        "flat": property_values_to_properties_dict(prop_rows),
        "rows": prop_rows,
    }
    row.properties_json = _dump_json(payload)
    now = _NOW()
    row.enriched_at = now
    row.updated_at = now
    return row


def upsert_metrics(
    db: Session,
    snapshot: ResourceSnapshot,
    metrics: dict[str, Any],
    *,
    metrics_payload: dict[str, Any] | None = None,
    monitor_raw: dict[str, Any] | None = None,
) -> Any:
    row = _get_or_create_enrichment(db, snapshot)
    existing = _parse_json(row.metrics_json, {})
    merged = {**existing, **(metrics or {})}
    if metrics_payload is not None:
        merged["payload"] = _strip_heavy_metrics(metrics_payload)
    if monitor_raw:
        merged["monitor_raw"] = monitor_raw
    row.metrics_json = _dump_json(merged)
    now = _NOW()
    row.metrics_at = now
    row.enriched_at = now
    row.updated_at = now
    return row


def upsert_cost(
    db: Session,
    snapshot: ResourceSnapshot,
    *,
    cost_overlay: dict[str, Any] | None = None,
) -> Any:
    row = _get_or_create_enrichment(db, snapshot)
    row.cost_json = _dump_json(_cost_payload(snapshot, cost_overlay=cost_overlay, db=db))
    now = _NOW()
    row.cost_at = now
    row.enriched_at = now
    row.updated_at = now
    return row


def _advisor_block_from_recommendations(existing: dict[str, Any]) -> dict[str, Any]:
    return {
        key: existing[key]
        for key in ("advisor", "advisor_count", "advisor_at")
        if key in existing
    }


def upsert_recommendations(
    db: Session,
    snapshot: ResourceSnapshot,
    *,
    summary: list[dict[str, Any]],
    findings_count: int = 0,
    savings_usd: float = 0.0,
    top_severity: str | None = None,
    run_id: str | None = None,
    data_source: str | None = None,
) -> Any:
    row = _get_or_create_enrichment(db, snapshot)
    existing = _parse_json(row.recommendations_json, {})
    row.recommendations_json = _dump_json({
        "summary": summary,
        "findings_count": findings_count,
        "savings_usd": savings_usd,
        "top_severity": top_severity,
        "run_id": run_id,
        "data_source": data_source,
        **_advisor_block_from_recommendations(existing),
    })
    now = _NOW()
    row.analysis_at = now
    row.enriched_at = now
    row.updated_at = now
    return row


def sync_properties_for_subscription(
    db: Session,
    subscription_id: str,
    *,
    arm_ids: set[str] | None = None,
) -> int:
    """Upsert properties for active inventory rows after inventory sync."""
    sub = subscription_id.strip().lower()
    q = db.query(ResourceSnapshot).filter(
        ResourceSnapshot.subscription_id == sub,
        ResourceSnapshot.is_active.is_(True),
        ResourceSnapshot.is_cost_export_only.is_(False),
    )
    if arm_ids:
        normalized = sorted(normalize_arm_id(rid) for rid in arm_ids)
        q = q.filter(ResourceSnapshot.resource_id.in_(normalized))
    count = 0
    for snapshot in q.yield_per(200):
        upsert_properties(db, snapshot)
        count += 1
    return count


def sync_cost_for_subscription(db: Session, subscription_id: str) -> int:
    """Upsert cost blocks after cost sync."""
    sub = subscription_id.strip().lower()
    cost_map = resource_cost_map_from_db(db, sub)
    count = 0
    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
        )
        .yield_per(200)
    )
    for snapshot in rows:
        arm = normalize_arm_id(snapshot.resource_id)
        overlay = cost_map.get(arm.lower()) or cost_map.get(arm)
        upsert_cost(db, snapshot, cost_overlay=overlay)
        count += 1
    return count


def sync_recommendations_from_snapshots(db: Session, subscription_id: str) -> int:
    """Copy denormalized analysis summaries from resource_snapshots into enrichment."""
    sub = subscription_id.strip().lower()
    count = 0
    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.analysis_updated_at.isnot(None),
        )
        .yield_per(200)
    )
    for snapshot in rows:
        summary = _parse_json(snapshot.analysis_summary_json, [])
        upsert_recommendations(
            db,
            snapshot,
            summary=summary if isinstance(summary, list) else [],
            findings_count=int(snapshot.analysis_findings_count or 0),
            savings_usd=float(snapshot.analysis_savings_usd or 0),
            top_severity=snapshot.analysis_top_severity,
            run_id=snapshot.analysis_run_id,
            data_source=snapshot.analysis_data_source,
        )
        count += 1
    return count


def advisor_items_for_resource(
    db: Session,
    subscription_id: str,
    arm_id: str,
) -> list[dict[str, Any]]:
    """Active Azure Advisor rows scoped to one ARM resource."""
    from app.advisor_sync import _serialize_advisor_row
    from app.models import AdvisorRecommendation

    sub = subscription_id.strip().lower()
    rid = normalize_arm_id(arm_id)
    rows = (
        db.query(AdvisorRecommendation)
        .filter(
            AdvisorRecommendation.subscription_id == sub,
            AdvisorRecommendation.status == "Active",
        )
        .all()
    )
    return [
        _serialize_advisor_row(row)
        for row in rows
        if normalize_arm_id(row.resource_id or "") == rid
    ]


def upsert_advisor_enrichment(
    db: Session,
    snapshot: ResourceSnapshot,
    *,
    advisor_items: list[dict[str, Any]] | None = None,
) -> Any:
    """Merge Azure Advisor recommendations into recommendations_json.advisor."""
    row = _get_or_create_enrichment(db, snapshot)
    existing = _parse_json(row.recommendations_json, {})
    items = (
        advisor_items
        if advisor_items is not None
        else advisor_items_for_resource(db, snapshot.subscription_id, snapshot.resource_id)
    )
    existing["advisor"] = items
    existing["advisor_count"] = len(items)
    existing["advisor_at"] = _NOW().isoformat()
    row.recommendations_json = _dump_json(existing)
    now = _NOW()
    row.enriched_at = now
    row.updated_at = now
    return row


def sync_advisor_enrichment_for_subscription(
    db: Session,
    subscription_id: str,
    *,
    arm_ids: set[str] | None = None,
) -> int:
    """Copy stored advisor rows into per-resource enrichment recommendations_json."""
    sub = subscription_id.strip().lower()
    q = db.query(ResourceSnapshot).filter(
        ResourceSnapshot.subscription_id == sub,
        ResourceSnapshot.is_active.is_(True),
        ResourceSnapshot.is_cost_export_only.is_(False),
    )
    if arm_ids:
        normalized = sorted(normalize_arm_id(rid) for rid in arm_ids)
        q = q.filter(ResourceSnapshot.resource_id.in_(normalized))
    count = 0
    for snapshot in q.yield_per(200):
        upsert_advisor_enrichment(db, snapshot)
        count += 1
    return count


def load_metrics_payload_from_store(
    db: Session,
    arm_id: str,
    *,
    max_age_hours: float | None = None,
    canonical_type: str | None = None,
) -> dict[str, Any] | None:
    """Return cached metrics API payload when fresh enough."""
    from datetime import timedelta

    rid = normalize_arm_id(arm_id)
    row = None
    bind = db.get_bind()
    if canonical_type:
        ct = canonical_type
    else:
        snap = (
            db.query(ResourceSnapshot)
            .filter(
                func.lower(ResourceSnapshot.resource_id) == rid,
                ResourceSnapshot.is_active.is_(True),
            )
            .first()
        )
        if not snap:
            return None
        ct = resolve_canonical_type(snap.resource_type)

    if not has_enrichment_table(bind, ct):
        return None
    model = get_enrichment_model(ct)

    def _query():
        return db.query(model).filter(model.arm_id == rid).first()

    row = _safe_enrichment_read(db, _query)
    if not row or not row.metrics_at:
        return None
    if max_age_hours is not None:
        age = _NOW() - (
            row.metrics_at.replace(tzinfo=timezone.utc)
            if row.metrics_at.tzinfo is None
            else row.metrics_at.astimezone(timezone.utc)
        )
        if age > timedelta(hours=max_age_hours):
            return None
    metrics = _parse_json(row.metrics_json, {})
    payload = metrics.get("payload")
    if not isinstance(payload, dict) or not payload.get("ok"):
        return None
    out = dict(payload)
    out["source"] = "db"
    return out


_UTILIZATION_FACT_KEYS = frozenset({
    "avg_cpu_pct",
    "avg_cpu",
    "cpu_pct",
    "max_cpu_pct",
    "memory_pct",
    "avg_memory_pct",
    "avg_mem_pct",
    "memory_usage_pct",
    "cluster_cpu_pct",
    "cluster_mem_pct",
    "normalized_ru_pct",
    "storage_pct",
    "disk_iops_utilization_pct",
    "disk_throughput_utilization_pct",
    "peak_disk_iops_utilization_pct",
})


def enrichment_max_age_hours() -> float:
    from app.resource_enrichment import enrichment_max_age_hours as _enrichment_max_age_hours

    return _enrichment_max_age_hours()


def enrichment_drawer_entry(
    enrichment: dict[str, Any] | None,
    *,
    include_metrics: bool,
    include_recommendations: bool,
) -> dict[str, Any]:
    """Build drawer batch-lookup fields from one enrichment row dict."""
    if not enrichment:
        return {}
    entry: dict[str, Any] = {}
    if include_metrics:
        metrics = enrichment.get("metrics") or {}
        payload = metrics.get("payload") if isinstance(metrics, dict) else None
        if isinstance(payload, dict) and payload.get("ok"):
            entry["metrics"] = payload
            entry["metrics_source"] = "db"
    if include_recommendations:
        recs = enrichment.get("recommendations")
        if isinstance(recs, dict) and recs.get("summary") is not None:
            entry["recommendations"] = recs
    cost = enrichment.get("cost")
    if isinstance(cost, dict) and cost:
        from app.cost_utils import monthly_cost_amounts_from_cost_block

        billing, usd, currency = monthly_cost_amounts_from_cost_block(cost)
        nested = cost.get("cost") if isinstance(cost.get("cost"), dict) else None
        if billing > 0 or usd > 0 or nested:
            entry["cost"] = nested or {
                "billed_mtd": billing if billing > 0 else usd,
                "billed_currency": currency,
                "retail_monthly": cost.get("retail_monthly"),
                "retail_currency": cost.get("retail_currency"),
                "retail_source": cost.get("retail_source"),
                "cost_pending": cost.get("cost_pending", billing <= 0 and usd <= 0),
                "retail_pending": cost.get("retail_pending", cost.get("retail_monthly") is None),
            }
            if billing > 0 or usd > 0:
                entry["monthlyCostBilling"] = billing
                entry["monthlyCostUsd"] = usd
                entry["billingCurrency"] = currency
    return entry


def _utilization_pct_from_facts(facts: dict[str, Any]) -> float | None:
    for key in _UTILIZATION_FACT_KEYS:
        if key not in facts:
            continue
        try:
            pct = float(facts[key])
        except (TypeError, ValueError):
            continue
        if key.endswith("_pct") or key in {"avg_cpu_pct", "max_cpu_pct", "memory_pct", "avg_memory_pct"}:
            if pct <= 1.0:
                pct *= 100.0
        return pct
    return None


def utilization_by_type_from_enrichment(
    db: Session,
    subscription_id: str,
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Dashboard utilization chart from persisted enrichment metrics."""
    sub = subscription_id.strip().lower()
    rows: list[tuple[Any, str]] = []
    for model in iter_existing_enrichment_models(db.get_bind()):
        chunk = (
            db.query(model, ResourceSnapshot.resource_type)
            .join(
                ResourceSnapshot,
                ResourceSnapshot.id == model.resource_id,
            )
            .filter(
                model.subscription_id == sub,
                model.metrics_at.isnot(None),
                ResourceSnapshot.is_active.is_(True),
            )
            .all()
        )
        rows.extend(chunk)
    if not rows:
        return []

    buckets: dict[str, dict[str, Any]] = {}
    seen_by_type: dict[str, set[str]] = {}
    for enrich_row, resource_type in rows:
        metrics = _parse_json(enrich_row.metrics_json, {})
        payload = metrics.get("payload") if isinstance(metrics, dict) else {}
        facts = payload.get("facts") if isinstance(payload, dict) else {}
        if not isinstance(facts, dict):
            facts = {k: v for k, v in metrics.items() if k != "payload" and not str(k).startswith("_")}
        pct = _utilization_pct_from_facts(facts if isinstance(facts, dict) else {})
        if pct is None:
            continue
        from app.dashboard.api import _utilization_buckets_to_items, _utilization_type_label

        label = _utilization_type_label(resource_type or "other")
        bucket = buckets.setdefault(label, {"count": 0, "avg_pct": None, "samples": [], "source": "enrichment"})
        rid = (enrich_row.arm_id or "").lower()
        seen = seen_by_type.setdefault(label, set())
        if rid and rid not in seen:
            seen.add(rid)
            bucket["count"] += 1
        prev_count = bucket.get("_pct_count", 0)
        prev_avg = bucket.get("avg_pct") or 0.0
        bucket["avg_pct"] = ((prev_avg * prev_count) + pct) / (prev_count + 1)
        bucket["_pct_count"] = prev_count + 1
        bucket["samples"].append(f"{pct:.1f}%")

    if not buckets:
        return []
    return _utilization_buckets_to_items(buckets, limit=limit)

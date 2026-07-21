"""Shared helpers for assessment pipeline workers — backed by per-type enrichment."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.assessment.catalog import indexed_arm_types
from app.assessment.normalizer import (
    build_normalized_record,
    merge_snapshot_json,
    resource_row_to_dict,
)
from app.data_store.enrichment_registry import ensure_enrichment_table, get_enrichment_model, iter_existing_enrichment_models, resolve_canonical_type
from app.data_store.resource_enrichment import _get_or_create_enrichment
from app.focus_mapping import normalize_arm_id
from app.models import ResourceSnapshot
from app.resource_type_map import arm_provider_type


def _now() -> datetime:
    return datetime.now(timezone.utc)


def indexed_resources_query(db: Session, subscription_id: str):
    sub = subscription_id.lower()
    return (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
        )
        .yield_per(200)
    )


def is_indexed_resource(resource_id: str) -> bool:
    arm_type = (arm_provider_type(resource_id) or "").lower()
    return arm_type in indexed_arm_types()


def _inventory_row(
    db: Session,
    *,
    subscription_id: str,
    resource_id: str,
) -> ResourceSnapshot | None:
    sub = subscription_id.lower()
    rid = normalize_arm_id(resource_id)
    return (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.resource_id == rid,
            ResourceSnapshot.is_active.is_(True),
        )
        .first()
    )


def get_or_create_snapshot(
    db: Session,
    *,
    subscription_id: str,
    resource_id: str,
    resource_type: str,
    canonical_type: str | None = None,
) -> Any:
    """Return the per-type enrichment row for a resource (pipeline snapshot)."""
    inv = _inventory_row(db, subscription_id=subscription_id, resource_id=resource_id)
    if not inv:
        inv = ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=subscription_id.lower(),
            resource_id=normalize_arm_id(resource_id),
            resource_name=resource_id.rsplit("/", 1)[-1],
            resource_type=canonical_type or resource_type or "other",
            resource_group="",
            location="",
            properties_json="{}",
            tags_json="{}",
            sku_json="{}",
            is_active=True,
            synced_at=_now(),
        )
        db.add(inv)
        db.flush()
    row = _get_or_create_enrichment(db, inv)
    if not getattr(row, "pipeline_stage", None):
        row.pipeline_stage = "pending"
    return row


def load_snapshot_dict(row: Any) -> dict[str, Any]:
    try:
        return json.loads(getattr(row, "snapshot_json", None) or "{}")
    except json.JSONDecodeError:
        return {}


def load_pipeline_resource_facts(
    db: Session,
    subscription_id: str,
) -> dict[str, dict[str, float]]:
    """Load monitor utilization facts persisted by the inventory metrics worker."""
    sub = subscription_id.lower()
    out: dict[str, dict[str, float]] = {}
    for model in iter_existing_enrichment_models(db.get_bind()):
        rows = (
            db.query(model)
            .filter(model.subscription_id == sub)
            .yield_per(200)
        )
        for row in rows:
            snap = load_snapshot_dict(row)
            metrics = snap.get("metrics") or {}
            if not isinstance(metrics, dict) or not metrics:
                metrics_block = json.loads(row.metrics_json or "{}")
                payload = metrics_block.get("payload") if isinstance(metrics_block, dict) else {}
                facts = payload.get("facts") if isinstance(payload, dict) else {}
                if isinstance(facts, dict) and facts:
                    metrics = facts
            if not isinstance(metrics, dict) or not metrics:
                continue
            facts_out: dict[str, float] = {}
            for key, value in metrics.items():
                if str(key).startswith("_"):
                    continue
                try:
                    facts_out[str(key)] = float(value)
                except (TypeError, ValueError):
                    continue
            if facts_out:
                out[(row.arm_id or "").lower()] = facts_out
    return out


def persist_normalized_snapshot(
    db: Session,
    *,
    subscription_id: str,
    row_dict: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    pipeline_stage: str | None = None,
    normalized_record: dict[str, Any] | None = None,
) -> Any:
    snap = get_or_create_snapshot(
        db,
        subscription_id=subscription_id,
        resource_id=row_dict["resource_id"],
        resource_type=row_dict.get("resource_type") or "",
        canonical_type=row_dict.get("canonical_type"),
    )
    record = normalized_record or build_normalized_record(row_dict, metrics=metrics)
    merged = merge_snapshot_json(load_snapshot_dict(snap), record)
    snap.snapshot_json = json.dumps(merged)
    if metrics is not None:
        snap.metrics_at = _now()
    if pipeline_stage:
        snap.pipeline_stage = pipeline_stage
    snap.enriched_at = _now()
    snap.updated_at = _now()
    return snap


def resources_by_canonical_for_metrics(
    db: Session,
    subscription_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """Group indexed inventory rows by canonical type for monitor_metrics loader."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in indexed_resources_query(db, subscription_id):
        row_dict = resource_row_to_dict(row)
        if not is_indexed_resource(row_dict["resource_id"]):
            continue
        canonical = row_dict.get("canonical_type") or "unknown"
        grouped.setdefault(canonical, []).append({
            "id": row_dict["resource_id"],
            "name": row_dict["resource_name"],
            "resource_group": row_dict["resource_group"],
            "location": row_dict["location"],
            "type": row_dict["canonical_type"],
            "sku": row_dict.get("sku"),
            "properties": row_dict.get("properties") or {},
        })
    return grouped


def iter_pipeline_enrichment_rows(db: Session, subscription_id: str) -> list[Any]:
    """All enrichment rows for one subscription (pipeline stage tracking)."""
    sub = subscription_id.lower()
    rows: list[Any] = []
    for model in iter_existing_enrichment_models(db.get_bind()):
        rows.extend(
            db.query(model).filter(model.subscription_id == sub).all()
        )
    return rows


def get_pipeline_row_by_arm(db: Session, resource_id: str) -> Any | None:
    rid = normalize_arm_id(resource_id)
    inv = (
        db.query(ResourceSnapshot)
        .filter(ResourceSnapshot.resource_id == rid, ResourceSnapshot.is_active.is_(True))
        .first()
    )
    if not inv:
        return None
    canonical = resolve_canonical_type(inv.resource_type)
    ensure_enrichment_table(db.get_bind(), canonical)
    model = get_enrichment_model(canonical)
    return (
        db.query(model)
        .filter(
            model.subscription_id == (inv.subscription_id or "").lower(),
            model.arm_id == rid,
        )
        .first()
    )

"""Individual assessment property values for resource enrichment (EAV, not JSON blobs)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Index, String, UniqueConstraint, inspect, text
from sqlalchemy.orm import Session

from app.assessment.normalizer import resource_row_to_dict
from app.assessment.property_registry import (
    AssessmentPropertyDef,
    property_defs_for_canonical,
    resolve_arm_path,
    serialize_property_value,
)
from app.data_store.enrichment_registry import resolve_canonical_type
from app.focus_mapping import normalize_arm_id
from app.models import Base, _now

TABLE_NAME = "resource_enrichment_property_values"


class ResourceEnrichmentPropertyValue(Base):
  __tablename__ = TABLE_NAME
  __table_args__ = (
      UniqueConstraint("subscription_id", "arm_id", "canonical_type", "property_key", name="uq_rep_sub_arm_type_key"),
      Index("ix_rep_resource", "resource_id"),
      Index("ix_rep_sub_type", "subscription_id", "canonical_type"),
  )

  id = Column(String, primary_key=True)
  resource_id = Column(String, nullable=False)
  arm_id = Column(String, nullable=False)
  subscription_id = Column(String, nullable=False)
  canonical_type = Column(String, nullable=False)
  property_key = Column(String, nullable=False)
  property_value = Column(String, nullable=True)
  value_type = Column(String, nullable=True)
  group_key = Column(String, nullable=True)
  label = Column(String, nullable=True)
  unit = Column(String, nullable=True)
  updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


def ensure_property_values_table(engine) -> None:
    ResourceEnrichmentPropertyValue.__table__.create(bind=engine, checkfirst=True)


def _extract_property_rows(
    snapshot: Any,
    *,
    canonical_type: str | None = None,
) -> list[dict[str, Any]]:
    ct = canonical_type or resolve_canonical_type(snapshot.resource_type)
    defs = property_defs_for_canonical(ct)
    if not defs:
        return []

    row_dict = resource_row_to_dict(snapshot)
    rows: list[dict[str, Any]] = []
    for prop_def in defs:
        raw = resolve_arm_path(row_dict, prop_def.arm_path)
        serialized = serialize_property_value(raw, prop_def.value_type)
        if serialized is None:
            continue
        rows.append({
            "property_key": prop_def.property_key,
            "property_value": serialized,
            "value_type": prop_def.value_type,
            "group_key": prop_def.group_key,
            "label": prop_def.label,
            "unit": prop_def.unit,
        })
    return rows


def upsert_property_values(
    db: Session,
    snapshot: Any,
    *,
    canonical_type: str | None = None,
) -> int:
    """Write assessment-defined properties as individual rows (replaces prior keys for resource)."""
    ensure_property_values_table(db.get_bind())

    ct = canonical_type or resolve_canonical_type(snapshot.resource_type)
    sub = (snapshot.subscription_id or "").lower()
    arm_id = normalize_arm_id(snapshot.resource_id)
    resource_id = snapshot.id
    extracted = _extract_property_rows(snapshot, canonical_type=ct)

    existing_keys = {
        row.property_key
        for row in db.query(ResourceEnrichmentPropertyValue.property_key)
        .filter(
            ResourceEnrichmentPropertyValue.subscription_id == sub,
            ResourceEnrichmentPropertyValue.arm_id == arm_id,
            ResourceEnrichmentPropertyValue.canonical_type == ct,
        )
        .all()
    }
    new_keys = {row["property_key"] for row in extracted}
    stale_keys = existing_keys - new_keys
    if stale_keys:
        db.query(ResourceEnrichmentPropertyValue).filter(
            ResourceEnrichmentPropertyValue.subscription_id == sub,
            ResourceEnrichmentPropertyValue.arm_id == arm_id,
            ResourceEnrichmentPropertyValue.canonical_type == ct,
            ResourceEnrichmentPropertyValue.property_key.in_(sorted(stale_keys)),
        ).delete(synchronize_session=False)

    now = datetime.now(timezone.utc)
    written = 0
    for item in extracted:
        key = item["property_key"]
        row = (
            db.query(ResourceEnrichmentPropertyValue)
            .filter(
                ResourceEnrichmentPropertyValue.subscription_id == sub,
                ResourceEnrichmentPropertyValue.arm_id == arm_id,
                ResourceEnrichmentPropertyValue.canonical_type == ct,
                ResourceEnrichmentPropertyValue.property_key == key,
            )
            .first()
        )
        if row:
            row.resource_id = resource_id
            row.property_value = item["property_value"]
            row.value_type = item["value_type"]
            row.group_key = item["group_key"]
            row.label = item["label"]
            row.unit = item.get("unit") or ""
            row.updated_at = now
        else:
            db.add(
                ResourceEnrichmentPropertyValue(
                    id=str(uuid.uuid4()),
                    resource_id=resource_id,
                    arm_id=arm_id,
                    subscription_id=sub,
                    canonical_type=ct,
                    property_key=key,
                    property_value=item["property_value"],
                    value_type=item["value_type"],
                    group_key=item["group_key"],
                    label=item["label"],
                    unit=item.get("unit") or "",
                    updated_at=now,
                )
            )
        written += 1
    return written


def load_property_values_map(
    db: Session,
    subscription_id: str,
    arm_ids: list[str],
    *,
    canonical_type: str | None = None,
) -> dict[str, dict[str, str]]:
    """Return {arm_id: {property_key: property_value}} for batch reads."""
    ensure_property_values_table(db.get_bind())
    sub = subscription_id.strip().lower()
    ids = sorted({normalize_arm_id(rid) for rid in arm_ids if rid})
    if not ids:
        return {}

    q = db.query(ResourceEnrichmentPropertyValue).filter(
        ResourceEnrichmentPropertyValue.subscription_id == sub,
        ResourceEnrichmentPropertyValue.arm_id.in_(ids),
    )
    if canonical_type:
        q = q.filter(ResourceEnrichmentPropertyValue.canonical_type == canonical_type)

    out: dict[str, dict[str, str]] = {}
    for row in q.all():
        arm_key = (row.arm_id or "").lower()
        bucket = out.setdefault(arm_key, {})
        if row.property_value is not None:
            bucket[row.property_key] = row.property_value
    return out


def load_property_value_rows(
    db: Session,
    subscription_id: str,
    arm_id: str,
    *,
    canonical_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return ordered property rows with labels for API/detail views."""
    ensure_property_values_table(db.get_bind())
    sub = subscription_id.strip().lower()
    rid = normalize_arm_id(arm_id)
    q = db.query(ResourceEnrichmentPropertyValue).filter(
        ResourceEnrichmentPropertyValue.subscription_id == sub,
        ResourceEnrichmentPropertyValue.arm_id == rid,
    )
    if canonical_type:
        q = q.filter(ResourceEnrichmentPropertyValue.canonical_type == canonical_type)
    rows = q.order_by(ResourceEnrichmentPropertyValue.group_key, ResourceEnrichmentPropertyValue.label).all()
    return [
        {
            "key": row.property_key,
            "label": row.label or row.property_key,
            "value": row.property_value,
            "group": row.group_key,
            "type": row.value_type,
            "unit": row.unit,
        }
        for row in rows
        if row.property_value is not None
    ]


def property_values_to_properties_dict(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Flat properties map for API consumers (diskSizeGB, sku, diskState, …)."""
    out: dict[str, Any] = {}
    for row in rows:
        key = row.get("key") or row.get("property_key")
        value = row.get("value") if "value" in row else row.get("property_value")
        if key and value is not None:
            out[str(key)] = value
    return out


def migrate_properties_from_enrichment_json(engine) -> int:
    """Backfill property value rows from legacy properties_json blobs."""
    from app.data_store.enrichment_registry import iter_existing_enrichment_models

    ensure_property_values_table(engine)
    insp = inspect(engine)
    if not insp.has_table(TABLE_NAME):
        return 0

    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=engine)
    session = Session()
    migrated = 0
    try:
        import json

        for model in iter_existing_enrichment_models(engine):
            table_name = model.__tablename__
            if not table_name.startswith("resource_enrichment_"):
                continue
            slug = table_name.replace("resource_enrichment_", "")
            canonical = slug.replace("_", "/") if slug != "other" else "_other"

            rows = session.query(model).all()
            for enrich_row in rows:
                payload = {}
                try:
                    payload = json.loads(enrich_row.properties_json or "{}")
                except (json.JSONDecodeError, TypeError):
                    payload = {}
                props = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
                if not props and isinstance(payload, dict):
                    props = {k: v for k, v in payload.items() if k not in {"resource", "tags", "sku", "state", "synced_at"}}

                sku = payload.get("sku")
                if sku and "sku" not in props:
                    props["sku"] = sku if isinstance(sku, str) else (sku.get("name") if isinstance(sku, dict) else sku)

                defs = {d.property_key: d for d in property_defs_for_canonical(canonical)}
                if not defs:
                    continue

                sub = (enrich_row.subscription_id or "").lower()
                arm_id = (enrich_row.arm_id or "").lower()
                for key, raw in props.items():
                    if key not in defs:
                        continue
                    prop_def: AssessmentPropertyDef = defs[key]
                    serialized = serialize_property_value(raw, prop_def.value_type)
                    if serialized is None:
                        continue
                    existing = (
                        session.query(ResourceEnrichmentPropertyValue)
                        .filter(
                            ResourceEnrichmentPropertyValue.subscription_id == sub,
                            ResourceEnrichmentPropertyValue.arm_id == arm_id,
                            ResourceEnrichmentPropertyValue.canonical_type == canonical,
                            ResourceEnrichmentPropertyValue.property_key == key,
                        )
                        .first()
                    )
                    if existing:
                        if not existing.property_value:
                            existing.property_value = serialized
                            migrated += 1
                        continue
                    session.add(
                        ResourceEnrichmentPropertyValue(
                            id=str(uuid.uuid4()),
                            resource_id=enrich_row.resource_id,
                            arm_id=arm_id,
                            subscription_id=sub,
                            canonical_type=canonical,
                            property_key=key,
                            property_value=serialized,
                            value_type=prop_def.value_type,
                            group_key=prop_def.group_key,
                            label=prop_def.label,
                            unit=prop_def.unit,
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
                    migrated += 1
        session.commit()
    finally:
        session.close()
    return migrated

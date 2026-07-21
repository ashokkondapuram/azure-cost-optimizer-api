"""Registry and dynamic ORM models for per-resource-type enrichment tables."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Index, String, UniqueConstraint, inspect
from sqlalchemy.orm import deferred

from app.db_types import JSONText
from app.models import Base, _now
from app.resources.registry import TECHNICAL_FETCH_SPECS

TABLE_PREFIX = "resource_enrichment_"
FALLBACK_CANONICAL = "_other"
PRIORITY_ENRICHMENT_TYPES: tuple[str, ...] = (
    "compute/vm",
    "compute/disk",
    "containers/aks",
    "database/cosmosdb",
    "storage/account",
    "network/loadbalancer",
)
_SLUG_RE = re.compile(r"[^a-z0-9_]+")

_MODEL_CACHE: dict[str, type] = {}


def canonical_to_slug(canonical_type: str) -> str:
    ct = (canonical_type or "").strip().lower()
    if not ct or ct in {"other", "_other"}:
        return "other"
    slug = ct.replace("/", "_").replace("-", "_")
    slug = _SLUG_RE.sub("_", slug).strip("_")
    return slug or "other"


def enrichment_table_name(canonical_type: str) -> str:
    return f"{TABLE_PREFIX}{canonical_to_slug(canonical_type)}"


def registered_enrichment_types() -> list[str]:
    return sorted(TECHNICAL_FETCH_SPECS.keys())


def all_enrichment_table_names() -> list[str]:
    names = {enrichment_table_name(ct) for ct in registered_enrichment_types()}
    names.add(enrichment_table_name(FALLBACK_CANONICAL))
    return sorted(names)


def resolve_canonical_type(snapshot_type: str | None) -> str:
    ct = (snapshot_type or "").strip().lower()
    if ct in TECHNICAL_FETCH_SPECS:
        return ct
    return FALLBACK_CANONICAL


def get_enrichment_model(canonical_type: str) -> type:
    """Return a cached SQLAlchemy mapped class for one enrichment table."""
    table_name = enrichment_table_name(canonical_type)
    cached = _MODEL_CACHE.get(table_name)
    if cached is not None:
        return cached

    slug = canonical_to_slug(canonical_type)
    uq_name = f"uq_re_{slug}_sub_arm"[:63]
    ix_snapshot = f"ix_re_{slug}_snapshot"[:63]
    ix_arm = f"ix_re_{slug}_arm"[:63]
    class_name = f"ResourceEnrichment_{slug}"

    attrs: dict[str, Any] = {
        "__tablename__": table_name,
        "__table_args__": (
            UniqueConstraint("subscription_id", "arm_id", name=uq_name),
            Index(ix_snapshot, "resource_id"),
            Index(ix_arm, "arm_id"),
        ),
        "id": Column(String, primary_key=True),
        "resource_id": Column(String, nullable=False),
        "arm_id": Column(String, nullable=False),
        "subscription_id": Column(String, nullable=False),
        "properties_json": deferred(Column(JSONText, default="{}")),
        "metrics_json": deferred(Column(JSONText, default="{}")),
        "cost_json": deferred(Column(JSONText, default="{}")),
        "recommendations_json": deferred(Column(JSONText, default="{}")),
        "snapshot_json": deferred(Column(JSONText, default="{}")),
        "pipeline_stage": Column(String, default="pending"),
        "enriched_at": Column(DateTime(timezone=True), nullable=True),
        "metrics_at": Column(DateTime(timezone=True), nullable=True),
        "cost_at": Column(DateTime(timezone=True), nullable=True),
        "analysis_at": Column(DateTime(timezone=True), nullable=True),
        "created_at": Column(DateTime(timezone=True), default=_now),
        "updated_at": Column(DateTime(timezone=True), default=_now, onupdate=_now),
    }
    cls = type(class_name, (Base,), attrs)
    _MODEL_CACHE[table_name] = cls
    return cls


def has_enrichment_table(engine, canonical_type: str) -> bool:
    """True when the per-type enrichment table exists (safe for read paths)."""
    return inspect(engine).has_table(enrichment_table_name(canonical_type))


def ensure_enrichment_table(engine, canonical_type: str) -> type:
    model = get_enrichment_model(canonical_type)
    model.__table__.create(bind=engine, checkfirst=True)
    return model


def ensure_priority_enrichment_tables(engine) -> None:
    """Pre-create high-traffic enrichment tables; others are created on first upsert."""
    for ct in PRIORITY_ENRICHMENT_TYPES:
        ensure_enrichment_table(engine, ct)
    ensure_enrichment_table(engine, FALLBACK_CANONICAL)


def migrate_enrichment_table_columns(engine) -> int:
    """Add pipeline/snapshot columns to existing per-type enrichment tables."""
    from sqlalchemy import text

    insp = inspect(engine)
    is_pg = engine.dialect.name == "postgresql"
    json_type = "JSONB DEFAULT '{}'::jsonb" if is_pg else "TEXT DEFAULT '{}'"
    altered = 0

    for table_name in all_enrichment_table_names():
        if not insp.has_table(table_name):
            continue
        cols = {c["name"] for c in insp.get_columns(table_name)}
        for col, typedef in (
            ("snapshot_json", json_type),
            ("pipeline_stage", "VARCHAR DEFAULT 'pending'"),
        ):
            if col not in cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col} {typedef}"))
                altered += 1

    return altered


def ensure_all_enrichment_tables(engine) -> None:
    for ct in registered_enrichment_types():
        ensure_enrichment_table(engine, ct)
    ensure_enrichment_table(engine, FALLBACK_CANONICAL)


def iter_existing_enrichment_models(engine) -> list[type]:
    insp = inspect(engine)
    models: list[type] = []
    for ct in registered_enrichment_types():
        if insp.has_table(enrichment_table_name(ct)):
            models.append(get_enrichment_model(ct))
    fallback_table = enrichment_table_name(FALLBACK_CANONICAL)
    if insp.has_table(fallback_table):
        models.append(get_enrichment_model(FALLBACK_CANONICAL))
    return models


def iter_enrichment_models() -> list[type]:
    return [get_enrichment_model(ct) for ct in registered_enrichment_types()] + [
        get_enrichment_model(FALLBACK_CANONICAL)
    ]


def clear_all_enrichment_tables(session) -> None:
    """Delete all rows from every per-type enrichment table (tests/admin)."""
    for model in iter_existing_enrichment_models(session.get_bind()):
        session.query(model).delete()


def _coerce_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return _now()
    return _now()


def migrate_unified_enrichment_table(engine) -> int:
    """Copy rows from legacy ``resource_enrichment`` into per-type tables, then drop it."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    insp = inspect(engine)
    if not insp.has_table("resource_enrichment"):
        return 0

    ensure_all_enrichment_tables(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    migrated = 0
    try:
        legacy_rows = session.execute(
            text(
                "SELECT id, resource_id, arm_id, canonical_type, subscription_id, "
                "properties_json, metrics_json, cost_json, recommendations_json, "
                "enriched_at, metrics_at, cost_at, analysis_at, created_at, updated_at "
                "FROM resource_enrichment"
            )
        ).mappings().all()

        for row in legacy_rows:
            canonical = resolve_canonical_type(row.get("canonical_type"))
            model = get_enrichment_model(canonical)
            arm_id = (row.get("arm_id") or "").lower()
            sub = (row.get("subscription_id") or "").lower()
            existing = (
                session.query(model)
                .filter(model.subscription_id == sub, model.arm_id == arm_id)
                .first()
            )
            if existing:
                target = existing
            else:
                target = model(
                    id=row["id"],
                    resource_id=row["resource_id"],
                    arm_id=arm_id,
                    subscription_id=sub,
                )
                session.add(target)
            target.properties_json = row.get("properties_json") or "{}"
            target.metrics_json = row.get("metrics_json") or "{}"
            target.cost_json = row.get("cost_json") or "{}"
            target.recommendations_json = row.get("recommendations_json") or "{}"
            target.enriched_at = _coerce_dt(row.get("enriched_at"))
            target.metrics_at = _coerce_dt(row.get("metrics_at"))
            target.cost_at = _coerce_dt(row.get("cost_at"))
            target.analysis_at = _coerce_dt(row.get("analysis_at"))
            target.created_at = _coerce_dt(row.get("created_at"))
            target.updated_at = _coerce_dt(row.get("updated_at"))
            migrated += 1

        session.commit()
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE resource_enrichment"))
    finally:
        session.close()

    return migrated


def drop_deprecated_tables(engine) -> None:
    """Drop legacy enrichment and pipeline tables after per-type migration."""
    from sqlalchemy import text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in (
            "resource_normalized_snapshots",
            "resource_utilization_history",
            "resource_enrichment",
        ):
            if insp.has_table(table):
                conn.execute(text(f"DROP TABLE {table}"))

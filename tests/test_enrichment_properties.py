"""Tests for individual assessment property storage (EAV)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.assessment.property_registry import property_defs_for_canonical
from app.data_store.enrichment_properties import (
    ResourceEnrichmentPropertyValue,
    ensure_property_values_table,
    load_property_value_rows,
    load_property_values_map,
    migrate_properties_from_enrichment_json,
    upsert_property_values,
)
from app.data_store.enrichment_registry import ensure_enrichment_table, get_enrichment_model
from app.data_store.resource_enrichment import (
    load_enrichment_batch,
    load_enrichment_dict,
    upsert_properties,
)
from app.models import Base, ResourceSnapshot

SUB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
DISK_ARM = (
    f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Compute/disks/disk1"
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    ensure_enrichment_table(engine, "compute/disk")
    ensure_property_values_table(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _disk_snapshot(**overrides) -> ResourceSnapshot:
    now = datetime.now(timezone.utc)
    props = {
        "diskSizeGB": 128,
        "diskState": "Attached",
        "diskIOPSReadWrite": 500,
        "diskMBpsReadWrite": 100,
        "managedBy": DISK_ARM.replace("/disks/disk1", "/virtualMachines/vm1"),
        "provisioningState": "Succeeded",
        "tier": "P10",
        "burstingEnabled": True,
    }
    data = {
        "id": str(uuid.uuid4()),
        "subscription_id": SUB,
        "resource_id": DISK_ARM,
        "resource_name": "disk1",
        "resource_type": "compute/disk",
        "resource_group": "rg",
        "location": "eastus",
        "properties_json": json.dumps(props),
        "tags_json": "{}",
        "sku_json": json.dumps({"name": "Premium_LRS", "tier": "Premium"}),
        "is_active": True,
        "synced_at": now,
    }
    data.update(overrides)
    return ResourceSnapshot(**data)


def test_property_defs_loaded_for_disk():
    defs = property_defs_for_canonical("compute/disk")
    keys = {d.property_key for d in defs}
    assert "diskSizeGB" in keys
    assert "sku" in keys
    assert "diskState" in keys


def test_upsert_property_values_writes_individual_rows(db):
    snap = _disk_snapshot()
    db.add(snap)
    db.commit()

    written = upsert_property_values(db, snap, canonical_type="compute/disk")
    db.commit()

    assert written >= 3
    rows = (
        db.query(ResourceEnrichmentPropertyValue)
        .filter(ResourceEnrichmentPropertyValue.arm_id == DISK_ARM.lower())
        .all()
    )
    by_key = {row.property_key: row for row in rows}
    assert by_key["diskSizeGB"].property_value == "128"
    assert by_key["diskState"].property_value == "Attached"
    assert by_key["sku"].property_value == "Premium_LRS"
    assert by_key["diskSizeGB"].group_key == "configuration"
    assert by_key["diskSizeGB"].label == "Disk size"


def test_upsert_properties_roundtrip_via_enrichment_dict(db):
    snap = _disk_snapshot()
    db.add(snap)
    db.commit()

    enrich_row = upsert_properties(db, snap)
    db.commit()

    loaded = load_enrichment_dict(enrich_row, canonical_type="compute/disk", db=db)
    assert loaded["assessment_properties"]["diskSizeGB"] == "128"
    assert loaded["assessment_properties"]["sku"] == "Premium_LRS"
    assert any(row["key"] == "diskSizeGB" for row in loaded["assessment_property_rows"])


def test_load_enrichment_batch_includes_assessment_properties(db):
    snap = _disk_snapshot()
    db.add(snap)
    db.commit()
    upsert_properties(db, snap)
    db.commit()

    batch = load_enrichment_batch(db, SUB, [DISK_ARM])
    payload = batch[DISK_ARM.lower()]
    assert payload["assessment_properties"]["diskState"] == "Attached"
    assert payload["canonical_type"] == "compute/disk"


def test_migrate_properties_from_legacy_json(db):
    snap = _disk_snapshot()
    db.add(snap)
    db.commit()

    disk_model = get_enrichment_model("compute/disk")
    legacy_payload = {
        "properties": {
            "diskSizeGB": 256,
            "diskState": "Unattached",
            "provisioningState": "Succeeded",
        },
        "sku": {"name": "StandardSSD_LRS"},
    }
    db.add(
        disk_model(
            id=str(uuid.uuid4()),
            resource_id=snap.id,
            arm_id=DISK_ARM.lower(),
            subscription_id=SUB,
            properties_json=json.dumps(legacy_payload),
            metrics_json="{}",
            cost_json="{}",
            recommendations_json="{}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    migrated = migrate_properties_from_enrichment_json(db.get_bind())
    assert migrated >= 2

    prop_map = load_property_values_map(db, SUB, [DISK_ARM], canonical_type="compute/disk")
    flat = prop_map[DISK_ARM.lower()]
    assert flat["diskSizeGB"] == "256"
    assert flat["diskState"] == "Unattached"
    assert flat["sku"] == "StandardSSD_LRS"


def test_load_property_value_rows_ordered_by_group(db):
    snap = _disk_snapshot()
    db.add(snap)
    db.commit()
    upsert_property_values(db, snap, canonical_type="compute/disk")
    db.commit()

    rows = load_property_value_rows(db, SUB, DISK_ARM, canonical_type="compute/disk")
    assert rows
    assert all("key" in row and "label" in row and "value" in row for row in rows)

"""Fast tests for per-type resource_enrichment store."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data_store.enrichment_registry import (
    clear_all_enrichment_tables,
    ensure_enrichment_table,
    enrichment_table_name,
    get_enrichment_model,
)
from app.data_store.resource_enrichment import (
    get_enrichment_row,
    load_enrichment_batch,
    load_enrichment_dict,
    load_metrics_payload_from_store,
    sync_cost_for_subscription,
    sync_properties_for_subscription,
    upsert_metrics,
    upsert_properties,
    upsert_recommendations,
)
from app.models import Base, CostByResourceSnapshot, ResourceSnapshot

SUB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ARM = f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    ensure_enrichment_table(engine, "compute/vm")
    ensure_enrichment_table(engine, "compute/disk")
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _snapshot(**overrides) -> ResourceSnapshot:
    now = datetime.now(timezone.utc)
    data = {
        "id": str(uuid.uuid4()),
        "subscription_id": SUB,
        "resource_id": ARM,
        "resource_name": "vm1",
        "resource_type": "compute/vm",
        "resource_group": "rg",
        "location": "eastus",
        "properties_json": '{"provisioningState":"Succeeded"}',
        "tags_json": "{}",
        "sku_json": "{}",
        "monthly_cost_usd": 42.5,
        "monthly_cost_billing": 55.0,
        "billing_currency": "CAD",
        "is_active": True,
        "synced_at": now,
    }
    data.update(overrides)
    return ResourceSnapshot(**data)


def test_enrichment_table_name_for_vm():
    assert enrichment_table_name("compute/vm") == "resource_enrichment_compute_vm"


def test_upsert_properties_creates_row_in_type_table(db):
    snap = _snapshot()
    db.add(snap)
    db.commit()

    row = upsert_properties(db, snap)
    db.commit()

    assert row.arm_id == ARM.lower()
    assert row.resource_id == snap.id
    assert row.properties_json
    assert row.enriched_at is not None
    vm_model = get_enrichment_model("compute/vm")
    assert db.query(vm_model).count() == 1


def test_upsert_metrics_merges_payload(db):
    snap = _snapshot()
    db.add(snap)
    db.commit()

    upsert_metrics(
        db,
        snap,
        {"cpu_pct": 12.5},
        metrics_payload={"ok": True, "facts": {"cpu_pct": 12.5}, "timespan": "P7D"},
    )
    db.commit()

    loaded = load_enrichment_dict(get_enrichment_row(db, SUB, ARM), canonical_type="compute/vm")
    assert loaded["metrics"]["cpu_pct"] == 12.5
    assert loaded["metrics"]["payload"]["ok"] is True
    assert loaded["metrics_at"] is not None


def test_upsert_recommendations(db):
    snap = _snapshot()
    db.add(snap)
    db.commit()

    summary = [{"rule_id": "VM_IDLE", "severity": "HIGH", "estimated_savings_usd": 100}]
    upsert_recommendations(
        db,
        snap,
        summary=summary,
        findings_count=1,
        savings_usd=100.0,
        top_severity="HIGH",
        run_id="run-1",
        data_source="db",
    )
    db.commit()

    loaded = load_enrichment_dict(get_enrichment_row(db, SUB, ARM), canonical_type="compute/vm")
    assert loaded["recommendations"]["findings_count"] == 1
    assert loaded["recommendations"]["summary"][0]["rule_id"] == "VM_IDLE"
    assert loaded["analysis_at"] is not None


def test_sync_properties_for_subscription(db):
    snap = _snapshot()
    db.add(snap)
    db.commit()

    count = sync_properties_for_subscription(db, SUB)
    db.commit()

    assert count == 1
    vm_model = get_enrichment_model("compute/vm")
    assert db.query(vm_model).count() == 1


def test_sync_cost_for_subscription_uses_cost_overlay(db):
    snap = _snapshot()
    db.add(snap)
    db.add(
        CostByResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            resource_id=ARM.lower(),
            service_name="Virtual Machines",
            month=datetime.now(timezone.utc).strftime("%Y-%m"),
            cost_usd=99.0,
            cost_billing=120.0,
            billing_currency="CAD",
        )
    )
    db.commit()

    count = sync_cost_for_subscription(db, SUB)
    db.commit()

    assert count == 1
    loaded = load_enrichment_dict(get_enrichment_row(db, SUB, ARM), canonical_type="compute/vm")
    assert loaded["cost"]["cost_usd"] == 99.0
    assert loaded["cost"]["monthly_cost_usd"] == 99.0
    assert loaded["cost"]["monthly_cost_billing"] == 120.0
    assert loaded["cost_at"] is not None


def test_per_type_routing_disk_vs_vm(db):
    vm = _snapshot()
    disk_arm = ARM.replace("virtualMachines/vm1", "disks/disk1")
    disk = _snapshot(
        id=str(uuid.uuid4()),
        resource_id=disk_arm,
        resource_name="disk1",
        resource_type="compute/disk",
    )
    db.add_all([vm, disk])
    db.commit()

    upsert_properties(db, vm)
    upsert_properties(db, disk)
    db.commit()

    vm_model = get_enrichment_model("compute/vm")
    disk_model = get_enrichment_model("compute/disk")
    assert db.query(vm_model).count() == 1
    assert db.query(disk_model).count() == 1

    batch = load_enrichment_batch(db, SUB, [ARM, disk_arm])
    assert len(batch) == 2
    assert batch[ARM.lower()]["canonical_type"] == "compute/vm"
    assert batch[disk_arm.lower()]["canonical_type"] == "compute/disk"


def test_migrate_unified_table_to_per_type(db):
    from sqlalchemy import text

    from app.data_store.enrichment_registry import migrate_unified_enrichment_table

    engine = db.get_bind()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE resource_enrichment (
                    id TEXT PRIMARY KEY,
                    resource_id TEXT NOT NULL,
                    arm_id TEXT NOT NULL,
                    canonical_type TEXT NOT NULL,
                    subscription_id TEXT NOT NULL,
                    properties_json TEXT DEFAULT '{}',
                    metrics_json TEXT DEFAULT '{}',
                    cost_json TEXT DEFAULT '{}',
                    recommendations_json TEXT DEFAULT '{}',
                    enriched_at DATETIME,
                    metrics_at DATETIME,
                    cost_at DATETIME,
                    analysis_at DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME,
                    UNIQUE (subscription_id, arm_id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO resource_enrichment (
                    id, resource_id, arm_id, canonical_type, subscription_id,
                    metrics_json, metrics_at
                ) VALUES (
                    :id, :resource_id, :arm_id, :canonical_type, :subscription_id,
                    :metrics_json, :metrics_at
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "resource_id": "legacy-snap",
                "arm_id": ARM.lower(),
                "canonical_type": "compute/vm",
                "subscription_id": SUB,
                "metrics_json": '{"cpu_pct": 7.5}',
                "metrics_at": datetime.now(timezone.utc),
            },
        )

    migrated = migrate_unified_enrichment_table(engine)
    assert migrated == 1
    vm_model = get_enrichment_model("compute/vm")
    row = db.query(vm_model).filter(vm_model.arm_id == ARM.lower()).one()
    assert '"cpu_pct": 7.5' in (row.metrics_json or "")

    insp = __import__("sqlalchemy").inspect(engine)
    assert not insp.has_table("resource_enrichment")


def test_migrate_schema_creates_per_type_tables(db):
    vm_model = get_enrichment_model("compute/vm")
    disk_model = get_enrichment_model("compute/disk")
    assert vm_model.__tablename__ == "resource_enrichment_compute_vm"
    assert disk_model.__tablename__ == "resource_enrichment_compute_disk"
    clear_all_enrichment_tables(db)
    assert db.query(vm_model).count() == 0


def test_load_metrics_payload_returns_none_when_table_missing(db):
    snap = _snapshot()
    db.add(snap)
    db.commit()

    assert load_metrics_payload_from_store(db, ARM, canonical_type="compute/vm") is None


def test_load_metrics_payload_returns_none_when_no_row(db):
    snap = _snapshot()
    db.add(snap)
    db.commit()
    ensure_enrichment_table(db.get_bind(), "compute/vm")

    assert load_metrics_payload_from_store(db, ARM, canonical_type="compute/vm") is None


def test_get_enrichment_row_returns_none_when_table_missing(db):
    snap = _snapshot()
    db.add(snap)
    db.commit()

    assert get_enrichment_row(db, SUB, ARM, canonical_type="compute/vm") is None


def test_migrate_enrichment_table_columns_adds_pipeline_fields(db):
    from sqlalchemy import text

    from app.data_store.enrichment_registry import migrate_enrichment_table_columns

    engine = db.get_bind()
    table_name = get_enrichment_model("compute/vm").__tablename__
    insp = __import__("sqlalchemy").inspect(engine)
    if insp.has_table(table_name):
        cols = {c["name"] for c in insp.get_columns(table_name)}
        with engine.begin() as conn:
            if "snapshot_json" in cols:
                conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN snapshot_json"))
            if "pipeline_stage" in cols:
                conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN pipeline_stage"))

    altered = migrate_enrichment_table_columns(engine)
    assert altered >= 2

    cols = {c["name"] for c in insp.get_columns(table_name)}
    assert "snapshot_json" in cols
    assert "pipeline_stage" in cols

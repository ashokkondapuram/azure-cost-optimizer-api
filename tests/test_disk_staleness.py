"""Tests for unattached disk staleness and ownership lineage."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, ResourceSnapshot
from app.disk_staleness import (
    augment_disk_evidence,
    disk_lineage_from_facts,
    disk_sync_state,
    enrich_disk_sync_properties,
    evaluate_unattached_disk,
    owner_display_name,
    staleness_evidence,
)
from app.finding_evidence import enrich_finding_for_api
from app.optimization_metrics import build_optimization_metrics


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_owner_display_name_from_vm_arm_id():
    rid = (
        "/subscriptions/s/resourceGroups/rg/providers/"
        "Microsoft.Compute/virtualMachines/my-vm"
    )
    assert owner_display_name(rid) == "my-vm"


def test_evaluate_stale_unattached_disk_uses_last_ownership_update():
    detached = datetime.now(timezone.utc) - timedelta(days=30)
    disk = {
        "name": "orphan-disk",
        "properties": {
            "diskState": "Unattached",
            "timeCreated": (datetime.now(timezone.utc) - timedelta(days=120)).isoformat(),
            "lastOwnershipUpdateTime": detached.isoformat(),
            "lastManagedBy": (
                "/subscriptions/s/resourceGroups/rg/providers/"
                "Microsoft.Compute/virtualMachines/old-vm"
            ),
        },
    }
    ctx = evaluate_unattached_disk(disk, max_days=14)
    assert ctx.is_stale is True
    assert ctx.is_recent is False
    assert ctx.last_owner_name == "old-vm"
    assert ctx.age_days >= 30


def test_evaluate_recent_unattached_disk_is_not_stale():
    detached = datetime.now(timezone.utc) - timedelta(days=3)
    disk = {
        "properties": {
            "diskState": "Unattached",
            "timeCreated": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
            "lastOwnershipUpdateTime": detached.isoformat(),
        },
    }
    ctx = evaluate_unattached_disk(disk, max_days=14)
    assert ctx.is_unattached is True
    assert ctx.is_stale is False
    assert ctx.is_recent is True


def test_evaluate_uses_time_created_when_no_ownership_update():
    created = datetime.now(timezone.utc) - timedelta(days=45)
    disk = {
        "properties": {
            "diskState": "Unattached",
            "timeCreated": created.isoformat(),
        },
    }
    ctx = evaluate_unattached_disk(disk, max_days=14)
    assert ctx.is_stale is True
    assert ctx.stale_since == created


def test_enrich_disk_sync_properties_preserves_last_owner_on_detach(db_session):
    rid = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/disks/d1"
    db_session.add(ResourceSnapshot(
        id="row-1",
        subscription_id="s",
        resource_id=rid.lower(),
        resource_name="d1",
        resource_type="compute/disk",
        properties_json=(
            '{"managedBy": "/subscriptions/s/resourceGroups/rg/providers/'
            'Microsoft.Compute/virtualMachines/source-vm", "diskState": "Attached"}'
        ),
    ))
    db_session.commit()

    arm_disk = {
        "id": rid,
        "name": "d1",
        "properties": {
            "diskState": "Unattached",
            "timeCreated": "2024-01-01T00:00:00Z",
            "lastOwnershipUpdateTime": "2025-06-01T00:00:00Z",
        },
    }
    props = enrich_disk_sync_properties(db_session, "s", arm_disk, {"diskState": "Unattached"})
    assert props["lastManagedBy"].endswith("/virtualMachines/source-vm")
    assert props["timeCreated"] == "2024-01-01T00:00:00Z"
    assert props["lastOwnershipUpdateTime"] == "2025-06-01T00:00:00Z"


def test_staleness_evidence_shape():
    created = datetime.now(timezone.utc) - timedelta(days=20)
    ctx = evaluate_unattached_disk({
        "properties": {
            "diskState": "Unattached",
            "timeCreated": created.isoformat(),
            "lastManagedBy": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        },
    }, max_days=14)
    evidence = staleness_evidence(ctx)
    assert evidence["is_stale"] is True
    assert evidence["last_owner_name"] == "vm1"
    assert evidence["age_days"] >= 20


def test_disk_lineage_from_facts_computes_age_from_timestamps():
    created = datetime.now(timezone.utc) - timedelta(days=40)
    detached = datetime.now(timezone.utc) - timedelta(days=22)
    lineage = disk_lineage_from_facts({
        "disk_state": "Unattached",
        "properties": {
            "timeCreated": created.isoformat(),
            "lastOwnershipUpdateTime": detached.isoformat(),
            "lastManagedBy": (
                "/subscriptions/s/resourceGroups/rg/providers/"
                "Microsoft.Compute/virtualMachines/retired-vm"
            ),
        },
    })
    assert lineage["age_days"] >= 22
    assert lineage["last_owner_name"] == "retired-vm"
    assert lineage["time_created"]
    assert lineage["last_ownership_update"]


def test_enrich_disk_sync_properties_reads_pascal_case_last_ownership(db_session):
    props = enrich_disk_sync_properties(
        db_session,
        "sub-id",
        {
            "id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
            "managedBy": None,
            "properties": {
                "diskState": "Unattached",
                "LastOwnershipUpdateTime": "2026-04-21T04:41:35.079872+00:00",
                "TimeCreated": "2026-04-20T04:41:35.079872+00:00",
            },
        },
        {},
    )
    assert props["lastOwnershipUpdateTime"] == "2026-04-21T04:41:35.079872+00:00"
    assert props["timeCreated"] == "2026-04-20T04:41:35.079872+00:00"


def test_enrich_disk_sync_properties_resolves_tier_provisioned_limits(db_session):
    props = enrich_disk_sync_properties(
        db_session,
        "sub-id",
        {
            "id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Compute/disks/data1",
            "sku": {"name": "Premium_LRS"},
            "properties": {
                "diskState": "Attached",
                "diskSizeGB": 512,
            },
        },
        {},
    )
    assert props["diskIOPSReadWrite"] == 3500
    assert props["diskMBpsReadWrite"] == 170
    assert props["provisionedPerformanceSource"] == "tier_spec"


def test_disk_lineage_from_facts_handles_pascal_case_properties():
    lineage = disk_lineage_from_facts({
        "properties": {
            "LastOwnershipUpdateTime": "2026-04-21T04:41:35.079872+00:00",
            "diskState": "Unattached",
        },
    })
    assert lineage["last_ownership_update"]


def test_augment_disk_evidence_merges_inventory_properties():
    detached = datetime.now(timezone.utc) - timedelta(days=30)
    inv = {
        "diskState": "Unattached",
        "timeCreated": (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(),
        "lastOwnershipUpdateTime": detached.isoformat(),
        "lastManagedBy": (
            "/subscriptions/s/resourceGroups/rg/providers/"
            "Microsoft.Compute/virtualMachines/prior-vm"
        ),
    }
    out = augment_disk_evidence(
        {"disk_state": "Unattached", "size_gb": 128},
        inv,
    )
    assert out["last_owner_name"] == "prior-vm"
    assert out["last_ownership_update"]


def test_enrich_finding_for_api_hydrates_disk_ownership_from_inventory():
    detached = datetime.now(timezone.utc) - timedelta(days=25)
    rid = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/disks/orphan"
    finding = enrich_finding_for_api(
        {
            "rule_id": "DISK_UNATTACHED",
            "resource_id": rid,
            "resource_type": "compute/disk",
            "estimated_savings_usd": 12.0,
            "evidence": {"disk_state": "Unattached", "size_gb": 64, "sku": "Premium_LRS"},
        },
        inventory_properties={
            "diskState": "Unattached",
            "timeCreated": (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),
            "lastOwnershipUpdateTime": detached.isoformat(),
            "lastManagedBy": (
                "/subscriptions/s/resourceGroups/rg/providers/"
                "Microsoft.Compute/virtualMachines/old-vm"
            ),
        },
    )
    metrics = build_optimization_metrics(
        finding["evidence"],
        finding=finding,
        rule_id="DISK_UNATTACHED",
        resource_type="compute/disk",
    )
    perf = {m["id"]: m for m in metrics["performance"]}
    assert perf["last_owner"]["formatted"] == "old-vm"
    assert perf["last_ownership_update"]["formatted"] != "Not available"


def test_disk_sync_state_reads_pascal_case_disk_state():
    arm_disk = {
        "properties": {"DiskState": "Unattached"},
    }
    assert disk_sync_state(arm_disk) == "Unattached"


def test_disk_sync_state_prefers_synced_props():
    arm_disk = {"properties": {}}
    assert disk_sync_state(arm_disk, {"diskState": "Attached"}) == "Attached"


def test_disk_sync_state_infers_attached_from_managed_by():
    arm_disk = {
        "managedBy": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        "properties": {},
    }
    assert disk_sync_state(arm_disk) == "Attached"

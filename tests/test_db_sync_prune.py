"""Tests for pruning resources missing from Azure during inventory sync."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db_sync import (
    _deactivate_missing_resources,
    _prune_stale_resources,
    deactivate_inventory_resources_not_found,
)
from app.models import Base, OptimizationFinding, ResourceSnapshot


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _add_vm(db, *, rid, name="vm-1", active=True):
    db.add(ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id="sub-1",
        resource_id=rid.lower(),
        resource_name=name,
        resource_type="compute/vm",
        resource_group="rg-1",
        location="eastus",
        is_active=active,
        properties_json="{}",
        synced_at=datetime.now(timezone.utc),
    ))


def test_deactivate_missing_resources_marks_stale_rows_inactive(db_session):
    kept_id = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-keep"
    stale_id = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-gone"
    _add_vm(db_session, rid=kept_id, name="vm-keep")
    _add_vm(db_session, rid=stale_id, name="vm-gone")
    db_session.commit()

    removed = _deactivate_missing_resources(
        db_session,
        "sub-1",
        "compute/vm",
        {kept_id},
    )
    db_session.commit()

    assert removed == 1
    rows = {
        row.resource_name: row.is_active
        for row in db_session.query(ResourceSnapshot).all()
    }
    assert rows["vm-keep"] is True
    assert rows["vm-gone"] is False


def test_deactivate_missing_resources_resolves_open_findings(db_session):
    rid = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-gone"
    _add_vm(db_session, rid=rid, name="vm-gone")
    finding = OptimizationFinding(
        id=str(uuid.uuid4()),
        run_id="run-1",
        rule_id="VM_IDLE",
        rule_name="Idle VM",
        category="COMPUTE",
        severity="HIGH",
        resource_id=rid.lower(),
        resource_name="vm-gone",
        resource_type="compute/vm",
        subscription_id="sub-1",
        detail="Idle",
        recommendation="Stop",
        status="open",
    )
    db_session.add(finding)
    db_session.commit()

    _deactivate_missing_resources(db_session, "sub-1", "compute/vm", set())
    db_session.commit()

    db_session.refresh(finding)
    assert finding.status == "resolved"
    assert finding.resolved_at is not None


def test_prune_stale_resources_only_for_successfully_synced_types(db_session):
    vm_id = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"
    disk_id = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-1"
    _add_vm(db_session, rid=vm_id, name="vm-1")
    db_session.add(ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id="sub-1",
        resource_id=disk_id.lower(),
        resource_name="disk-1",
        resource_type="compute/disk",
        resource_group="rg-1",
        is_active=True,
        properties_json="{}",
        synced_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    removed = _prune_stale_resources(
        db_session,
        "sub-1",
        {"compute/vm": {vm_id}},
        {"compute/vm"},
    )
    db_session.commit()

    assert removed == {}
    disk = (
        db_session.query(ResourceSnapshot)
        .filter(ResourceSnapshot.resource_name == "disk-1")
        .one()
    )
    assert disk.is_active is True


def test_deactivate_inventory_resources_not_found_by_arm_id(db_session):
    gone_id = (
        "/subscriptions/sub-1/resourcegroups/mc_rg/providers/"
        "microsoft.compute/virtualmachines/aks-loki-ondemand-8d8pr"
    )
    keep_id = (
        "/subscriptions/sub-1/resourcegroups/mc_rg/providers/"
        "microsoft.compute/virtualmachines/aks-keep"
    )
    _add_vm(db_session, rid=gone_id, name="aks-loki-ondemand-8d8pr")
    _add_vm(db_session, rid=keep_id, name="aks-keep")
    db_session.commit()

    removed = deactivate_inventory_resources_not_found(
        db_session,
        {gone_id},
        source="monitor_metrics",
    )
    db_session.commit()

    assert removed == 1
    rows = {
        row.resource_name: row.is_active
        for row in db_session.query(ResourceSnapshot).all()
    }
    assert rows["aks-keep"] is True
    assert rows["aks-loki-ondemand-8d8pr"] is False

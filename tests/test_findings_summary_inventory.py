"""Inventory-only filtering for findings summary."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.findings_summary import _filter_findings_to_inventory, build_findings_summary
from app.focus_mapping import normalize_arm_id
from app.models import Base, OptimizationFinding, ResourceSnapshot

SUB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
INV_ID = (
    f"/subscriptions/{SUB}/resourceGroups/rg-live/providers/"
    "Microsoft.Compute/virtualMachines/vm-live"
)
COST_ONLY_ID = (
    f"/subscriptions/{SUB}/resourceGroups/rg-gone/providers/"
    "Microsoft.Compute/disks/disk-deleted"
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _add_inventory(db, resource_id: str, name: str):
    db.add(
        ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            resource_id=normalize_arm_id(resource_id),
            resource_name=name,
            resource_type="compute/vm",
            resource_group="rg-live",
            location="canadacentral",
            state="running",
            properties_json='{"provisioningState":"Succeeded"}',
            tags_json="{}",
            sku_json="{}",
            is_active=True,
            synced_at=datetime.now(timezone.utc),
        )
    )


def test_filter_findings_to_inventory(db):
    _add_inventory(db, INV_ID, "vm-live")
    db.commit()

    findings = [
        OptimizationFinding(
            id="f1",
            subscription_id=SUB,
            resource_id=normalize_arm_id(INV_ID),
            status="open",
            severity="HIGH",
            estimated_savings_usd=100.0,
        ),
        OptimizationFinding(
            id="f2",
            subscription_id=SUB,
            resource_id=normalize_arm_id(COST_ONLY_ID),
            status="open",
            severity="HIGH",
            estimated_savings_usd=50.0,
        ),
    ]

    kept = _filter_findings_to_inventory(db, SUB, findings)
    assert len(kept) == 1
    assert kept[0].id == "f1"


def test_build_findings_summary_inventory_only(db):
    _add_inventory(db, INV_ID, "vm-live")
    db.add(OptimizationFinding(
        id="f1",
        subscription_id=SUB,
        resource_id=normalize_arm_id(INV_ID),
        status="open",
        severity="HIGH",
        category="COMPUTE",
        estimated_savings_usd=100.0,
    ))
    db.add(OptimizationFinding(
        id="f2",
        subscription_id=SUB,
        resource_id=normalize_arm_id(COST_ONLY_ID),
        status="open",
        severity="HIGH",
        category="COMPUTE",
        estimated_savings_usd=50.0,
    ))
    db.commit()

    all_summary = build_findings_summary(db, SUB, inventory_only=False)
    inv_summary = build_findings_summary(db, SUB, inventory_only=True)

    assert all_summary["open_findings_all"] == 2
    assert all_summary["open_findings"] == 1
    assert all_summary["excluded"]["cost_export_only"] == 1
    assert inv_summary["open_findings"] == 1
    assert inv_summary["inventory_only"] is True

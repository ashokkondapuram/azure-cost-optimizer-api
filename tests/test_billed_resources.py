"""Tests for cost-first billed resource listing."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.billed_resources import (
    billed_row_from_cost,
    list_billed_resources_db,
    list_billed_resources_page,
    reconcile_billed_azure_status,
)
from app.focus_mapping import normalize_arm_id
from app.models import Base, CostByResourceSnapshot, ResourceSnapshot


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


SUB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
MONTH = "2026-06"
INV_ID = (
    f"/subscriptions/{SUB}/resourceGroups/rg-live/providers/"
    "Microsoft.Compute/virtualMachines/vm-live"
)
MISSING_ID = (
    f"/subscriptions/{SUB}/resourceGroups/rg-gone/providers/"
    "Microsoft.Compute/disks/disk-deleted"
)


def _add_cost(db, resource_id: str, billing: float, *, azure_exists=None):
    db.add(
        CostByResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            resource_id=normalize_arm_id(resource_id),
            service_name="Virtual Machines",
            resource_group="rg-live",
            resource_type="Microsoft.Compute/virtualMachines",
            month=MONTH,
            cost_usd=billing,
            cost_billing=billing,
            billing_currency="CAD",
            azure_exists=azure_exists,
        )
    )


def _add_inventory(db, resource_id: str, name: str, *, resource_type: str = "compute/vm"):
    db.add(
        ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            resource_id=normalize_arm_id(resource_id),
            resource_name=name,
            resource_type=resource_type,
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


def test_inventory_only_excludes_cost_export_rows(db):
    _add_cost(db, INV_ID, 120.0)
    _add_cost(db, MISSING_ID, 45.0, azure_exists=False)
    _add_inventory(db, INV_ID, "vm-live")
    db.commit()

    page = list_billed_resources_page(db, SUB, limit=50, offset=0, inventory_only=True)
    assert page["total"] == 1
    assert len(page["items"]) == 1
    assert page["items"][0]["id"] == normalize_arm_id(INV_ID)
    assert page["items"][0]["inInventory"] is True
    assert page["items"][0]["costExportOnly"] is False


def test_inventory_page_without_cost_month(db):
    """Paginated Action centre list must show synced inventory before cost sync."""
    no_cost_id = (
        f"/subscriptions/{SUB}/resourceGroups/rg-live/providers/"
        "Microsoft.Storage/storageAccounts/stgnew"
    )
    _add_inventory(db, INV_ID, "vm-live")
    _add_inventory(db, no_cost_id, "stgnew", resource_type="storage/account")
    db.commit()

    page = list_billed_resources_page(db, SUB, limit=50, offset=0, inventory_only=True)
    assert page["total"] == 2
    assert len(page["items"]) == 2
    assert page["month"] is None
    assert all(item["inInventory"] is True for item in page["items"])


def test_billed_list_includes_missing_azure_resource(db):
    _add_cost(db, INV_ID, 120.0)
    _add_cost(db, MISSING_ID, 45.0, azure_exists=False)
    _add_inventory(db, INV_ID, "vm-live")
    db.commit()

    rows = list_billed_resources_db(db, SUB)
    assert len(rows) == 2
    by_id = {r["id"]: r for r in rows}
    assert by_id[normalize_arm_id(INV_ID)]["azureStatus"] == "exists"
    assert by_id[normalize_arm_id(INV_ID)]["hasMtdCost"] is True
    assert by_id[normalize_arm_id(MISSING_ID)]["azureStatus"] == "missing"
    assert by_id[normalize_arm_id(MISSING_ID)]["state"] == "Doesn't exist on Azure"
    assert by_id[normalize_arm_id(MISSING_ID)]["monthlyCostBilling"] == 45.0


def test_inventory_without_cost_is_included(db):
    no_cost_id = (
        f"/subscriptions/{SUB}/resourceGroups/rg-live/providers/"
        "Microsoft.Storage/storageAccounts/stgnew"
    )
    _add_inventory(db, no_cost_id, "stgnew", resource_type="storage/account")
    _add_cost(db, INV_ID, 50.0)
    _add_inventory(db, INV_ID, "vm-live")
    db.commit()

    rows = list_billed_resources_db(db, SUB)
    by_id = {r["id"]: r for r in rows}
    assert normalize_arm_id(no_cost_id) in by_id
    pending = by_id[normalize_arm_id(no_cost_id)]
    assert pending["azureStatus"] == "exists"
    assert pending["inInventory"] is True
    assert pending["hasMtdCost"] is False
    assert pending["costPending"] is True


def test_billed_page_lazy_pagination(db):
    for i in range(5):
        _add_cost(
            db,
            f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Compute/disks/d{i}",
            float(10 * (i + 1)),
        )
    db.commit()

    page = list_billed_resources_page(db, SUB, limit=2, offset=0)
    assert page["total"] == 5
    assert len(page["items"]) == 2
    assert page["has_more"] is True

    page2 = list_billed_resources_page(db, SUB, limit=2, offset=2)
    assert len(page2["items"]) == 2
    assert page2["has_more"] is True


def test_reconcile_marks_inventory_exists(db):
    _add_cost(db, INV_ID, 80.0)
    _add_inventory(db, INV_ID, "vm-live")
    db.commit()

    updated = reconcile_billed_azure_status(db, SUB, MONTH)
    db.commit()

    row = (
        db.query(CostByResourceSnapshot)
        .filter(CostByResourceSnapshot.resource_id == normalize_arm_id(INV_ID))
        .one()
    )
    assert updated == 1
    assert row.azure_exists is True


def test_billed_row_unknown_without_inventory(db):
    cost = CostByResourceSnapshot(
        id="c1",
        subscription_id=SUB,
        resource_id=normalize_arm_id(MISSING_ID),
        service_name="Storage",
        resource_group="rg-gone",
        resource_type="Microsoft.Compute/disks",
        month=MONTH,
        cost_usd=12.0,
        cost_billing=12.0,
        billing_currency="CAD",
    )
    row = billed_row_from_cost(cost, None)
    assert row["azureStatus"] == "unknown"
    assert row["hasMtdCost"] is True
    assert row["name"] == "disk-deleted"


def test_cost_refresh_default_is_one_hour(monkeypatch):
    monkeypatch.delenv("COST_REFRESH_HOURS", raising=False)
    monkeypatch.delenv("COST_EXPORT_REFRESH_HOURS", raising=False)
    from app.cost_explorer_worker import cost_refresh_hours

    assert cost_refresh_hours() == 1.0

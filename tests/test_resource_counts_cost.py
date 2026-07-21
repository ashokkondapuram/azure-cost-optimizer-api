"""Resource count breakdown includes Cost Management MTD per type."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import migrate_schema
from app.models import Base, CostByResourceTypeSnapshot, ResourceSnapshot
from app.resource_store import get_resource_counts


@pytest.fixture(autouse=True)
def _clear_read_caches():
    from app.perf_cache import clear_subscription_read_caches

    clear_subscription_read_caches()
    yield
    clear_subscription_read_caches()


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    migrate_schema()
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


SUB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
MONTH = date.today().strftime("%Y-%m")


def test_breakdown_marks_cost_bearing_types(db):
    db.add(
        ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            resource_id=f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
            resource_name="vm1",
            resource_type="compute/vm",
            resource_group="rg",
            location="eastus",
            properties_json='{"provisioningState":"Succeeded"}',
            tags_json="{}",
            sku_json="{}",
            is_active=True,
            synced_at=datetime.now(timezone.utc),
        )
    )
    db.add(
        ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            resource_id=(
                f"/subscriptions/{SUB}/resourceGroups/rg/providers/"
                "Microsoft.Network/privateEndpoints/pe1"
            ),
            resource_name="pe1",
            resource_type="network/privateendpoint",
            resource_group="rg",
            location="eastus",
            properties_json='{"provisioningState":"Succeeded"}',
            tags_json="{}",
            sku_json="{}",
            is_active=True,
            synced_at=datetime.now(timezone.utc),
        )
    )
    db.add(
        CostByResourceTypeSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            arm_resource_type="microsoft.compute/virtualmachines",
            canonical_resource_type="compute/vm",
            month=MONTH,
            cost_usd=50.0,
            cost_billing=50.0,
            billing_currency="CAD",
        )
    )
    db.commit()

    counts = get_resource_counts(db, SUB)
    assert counts["vms"] == 1
    assert counts["privateendpoints"] == 1
    assert counts["breakdown"]["vms"]["has_cost"] is True
    assert counts["breakdown"]["vms"]["cost_type"] == "costed"
    assert counts["breakdown"]["privateendpoints"]["has_cost"] is False
    assert counts["breakdown"]["privateendpoints"]["cost_type"] == "costed"


def test_breakdown_marks_free_types_without_cost(db):
    db.add(
        ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            resource_id=(
                f"/subscriptions/{SUB}/resourceGroups/rg/providers/"
                "Microsoft.Network/networkSecurityGroups/nsg1"
            ),
            resource_name="nsg1",
            resource_type="network/nsg",
            resource_group="rg",
            location="eastus",
            properties_json='{"provisioningState":"Succeeded"}',
            tags_json="{}",
            sku_json="{}",
            is_active=True,
            synced_at=datetime.now(timezone.utc),
        )
    )
    db.add(
        ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            resource_id=f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
            resource_name="vm1",
            resource_type="compute/vm",
            resource_group="rg",
            location="eastus",
            properties_json='{"provisioningState":"Succeeded"}',
            tags_json="{}",
            sku_json="{}",
            is_active=True,
            synced_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    counts = get_resource_counts(db, SUB)
    assert counts["nsgs"] == 1
    assert counts["vms"] == 1
    assert counts["breakdown"]["nsgs"]["has_cost"] is False
    assert counts["breakdown"]["nsgs"]["cost_type"] == "free"
    assert counts["breakdown"]["vms"]["has_cost"] is False
    assert counts["cost_bearing_inventory"] == 0


def test_breakdown_shows_type_with_findings_but_no_cost(db):
    db.add(
        ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            resource_id=(
                f"/subscriptions/{SUB}/resourceGroups/rg/providers/"
                "Microsoft.Network/virtualNetworks/vnet1"
            ),
            resource_name="vnet1",
            resource_type="network/vnet",
            resource_group="rg",
            location="eastus",
            properties_json='{"provisioningState":"Succeeded"}',
            tags_json="{}",
            sku_json="{}",
            is_active=True,
            analysis_findings_count=2,
            synced_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    counts = get_resource_counts(db, SUB)
    assert counts["vnets"] == 1
    assert counts["breakdown"]["vnets"]["findings_count"] == 2
    assert counts["breakdown"]["vnets"]["has_cost"] is True
    assert counts["cost_bearing_inventory"] == 1

"""Lifetime and MoM resource cost enrichment."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import migrate_schema
from app.cost_db import resource_lifetime_cost_map_from_db, resource_cost_mom_delta_map_from_db
from app.models import Base, CostByResourceSnapshot
from app.resource_store import apply_costs_to_resources

SUB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
RID = f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    migrate_schema()
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _add_cost_row(db, month: str, billing: float) -> None:
    db.add(
        CostByResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            resource_id=RID,
            service_name="Virtual Machines",
            resource_group="rg",
            resource_type="microsoft.compute/virtualmachines",
            month=month,
            cost_usd=billing,
            cost_billing=billing,
            billing_currency="CAD",
            synced_at=datetime.now(timezone.utc),
        )
    )


def test_lifetime_cost_sums_all_months(db):
    _add_cost_row(db, "2026-04", 10.0)
    _add_cost_row(db, "2026-05", 25.5)
    _add_cost_row(db, "2026-06", 2.62)
    db.commit()

    lifetime = resource_lifetime_cost_map_from_db(db, SUB)
    norm = RID.lower()
    assert lifetime[norm]["pretax"] == pytest.approx(38.12)


def test_apply_costs_adds_total_and_trend(db):
    _add_cost_row(db, "2026-05", 5.0)
    _add_cost_row(db, "2026-06", 8.0)
    db.commit()

    rows = apply_costs_to_resources(
        [{"id": RID, "name": "vm1"}],
        {"pretax": 8.0, "usd": 8.0, "currency": "CAD"},
        lifetime_map=resource_lifetime_cost_map_from_db(db, SUB),
        mom_map=resource_cost_mom_delta_map_from_db(db, SUB),
    )
    row = rows[0]
    assert row["totalCostBilling"] == pytest.approx(13.0)
    assert row["costTrendBilling"] == pytest.approx(3.0)

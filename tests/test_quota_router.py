"""Tests for quota router helpers."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, ResourceSnapshot
from app.routers.quota import _usage_to_dict, quota_locations


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'quota.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_usage_to_dict_critical_status():
    row = _usage_to_dict({
        "name": {"value": "cores", "localizedValue": "Total Regional vCPUs"},
        "currentValue": 95,
        "limit": 100,
    }, "compute")
    assert row["status"] == "critical"
    assert row["usage_pct"] == 95.0
    assert row["source"] == "compute"


def test_quota_locations_from_inventory(db_session):
    db_session.add(ResourceSnapshot(
        id="1",
        subscription_id="sub-1",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        resource_name="vm1",
        resource_type="Microsoft.Compute/virtualMachines",
        location="eastus",
        is_active=True,
    ))
    db_session.add(ResourceSnapshot(
        id="2",
        subscription_id="sub-1",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm2",
        resource_name="vm2",
        resource_type="Microsoft.Compute/virtualMachines",
        location="westus2",
        is_active=True,
    ))
    db_session.commit()

    result = quota_locations("sub-1", db=db_session)
    assert result["locations"] == ["eastus", "westus2"]
    assert result["source"] == "inventory"

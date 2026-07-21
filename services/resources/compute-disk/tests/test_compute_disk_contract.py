"""Contract tests for compute-disk microservice."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "costoptimizer-core"))

DISK_ID = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/disk-01"
SUBSCRIPTION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture
def client():
    from app.models import Base, CostByResourceSnapshot, ResourceSnapshot

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=SUBSCRIPTION_ID,
        resource_id=DISK_ID,
        resource_name="disk-01",
        resource_type="compute/disk",
        resource_group="rg",
        location="canadacentral",
        sku="Premium_LRS",
        is_active=True,
        synced_at=datetime.now(timezone.utc),
    ))
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    session.add(CostByResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=SUBSCRIPTION_ID,
        resource_id=DISK_ID,
        service_name="Storage",
        month=month,
        cost_billing=58.06,
        cost_usd=45.0,
        billing_currency="CAD",
    ))
    session.commit()

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    service_src = ROOT / "services" / "resources" / "compute-disk" / "src" / "service_app.py"
    spec = importlib.util.spec_from_file_location("compute-disk_service_app", service_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    from app.database import get_db

    module.app.dependency_overrides[get_db] = _get_db
    return TestClient(module.app)


def test_health_live(client):
    res = client.get("/health/live")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service_id"] == "compute-disk"


def test_meta(client):
    res = client.get("/v1/meta")
    assert res.status_code == 200
    body = res.json()
    assert body["canonical_type"] == "compute/disk"
    assert body["api_slug"] == "disks"


def test_list_resources_returns_cost_block(client):
    res = client.get(
        "/v1/resources",
        params={
            "subscription_id": SUBSCRIPTION_ID,
            "limit": 10,
            "include_costs": True,
            "include_metrics": False,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["items"]
    item = body["items"][0]
    assert item["cost"]["billed_mtd"] == pytest.approx(58.06)
    assert item["monthlyCostBilling"] == pytest.approx(58.06)
    assert item["cost"]["cost_pending"] is False

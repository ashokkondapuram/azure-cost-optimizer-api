"""Disk list API response shape — concept v2 / disk-assessment alignment."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.disk_api_enrichment import enrich_disk_api_row
from app.models import Base, CostByResourceSnapshot, ResourceSnapshot
from app.resource_store import get_resources_db_page
from app.routers.resources_inventory import _enrich_disk_list_result

DISK_ID = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/disk-01"
SUBSCRIPTION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
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
    yield session
    session.close()


def test_get_resources_db_page_attaches_cost_from_cost_by_resource(db_session):
    page = get_resources_db_page(
        db_session,
        SUBSCRIPTION_ID,
        "compute/disk",
        limit=50,
        offset=0,
    )
    assert page["items"]
    item = page["items"][0]
    assert item["cost"]["billed_mtd"] == pytest.approx(58.06)
    assert item["cost"]["cost_pending"] is False


def test_enrich_disk_list_result_handles_paginated_envelope(db_session):
    page = get_resources_db_page(
        db_session,
        SUBSCRIPTION_ID,
        "compute/disk",
        limit=50,
        offset=0,
    )
    enriched = _enrich_disk_list_result(page, include_metrics=False)
    item = enriched["items"][0]
    assert item["cost"]["billed_mtd"] == pytest.approx(58.06)
    assert "properties" in item


def _sample_disk_row() -> dict:
    return {
        "id": "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/disk-01",
        "name": "disk-01",
        "type": "compute/disk",
        "resourceGroup": "rg",
        "location": "canadacentral",
        "sku": "Premium_LRS",
        "monthlyCostBilling": 58.06,
        "billingCurrency": "CAD",
        "properties": {
            "diskSizeGB": 128,
            "tier": "P10",
            "diskState": "Unattached",
            "provisioningState": "Succeeded",
            "diskIOPSReadWrite": 500,
            "diskMBpsReadWrite": 100,
        },
        "analysisSummary": [
            {
                "rule_id": "DISK_UNUSED_EXTENDED",
                "severity": "HIGH",
                "estimated_savings_usd": 124.0,
            }
        ],
        "analysisFindingsCount": 1,
        "analysisSavingsUsd": 124.0,
        "_metrics": {
            "disk_iops_utilization_pct": 8,
            "disk_throughput_utilization_pct": 5,
            "disk_read_iops": 4,
            "disk_write_iops": 3,
        },
    }


def test_enrich_disk_api_row_cost_block():
    row = enrich_disk_api_row(_sample_disk_row(), include_metrics=True)
    cost = row["cost"]
    assert isinstance(cost, dict)
    assert cost["billed_mtd"] == 58.06
    assert "retail_monthly" in cost
    assert "cost_pending" in cost


def test_enrich_disk_api_row_metrics_block():
    row = enrich_disk_api_row(_sample_disk_row(), include_metrics=True)
    assert "metrics" in row
    assert row["metrics"]["disk_iops_utilization_pct"] == 8
    assert row["_metrics"]["disk_throughput_utilization_pct"] == 5


def test_enrich_disk_api_row_finding_summary():
    row = enrich_disk_api_row(_sample_disk_row(), include_metrics=False)
    finding = row["finding"]
    assert finding is not None
    assert finding["rule_id"] == "DISK_UNUSED_EXTENDED"
    assert finding["severity"] == "high"
    assert finding["savings"] == 124.0
    assert finding["workflow"] == "proposed"


def test_enrich_disk_api_row_properties_sku_flattened():
    row = enrich_disk_api_row(_sample_disk_row(), include_metrics=False)
    props = row["properties"]
    assert props.get("sku") == "Premium_LRS"
    assert props.get("diskSizeGB") == 128

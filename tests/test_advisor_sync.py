"""Tests for Azure Advisor sync and normalization."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.advisor_sync import (
    _resolve_resource_id,
    list_stored_advisor_recommendations,
    normalize_advisor_item,
    upsert_advisor_recommendations,
)
from app.models import AdvisorRecommendation, Base, SubscriptionCache


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _sample_advisor_item(**overrides):
    item = {
        "name": "rec-001",
        "id": "/subscriptions/sub-1/providers/Microsoft.Advisor/recommendations/rec-001",
        "type": "Microsoft.Advisor/recommendations",
        "properties": {
            "category": "Cost",
            "impact": "High",
            "lastUpdated": "2026-06-01T12:00:00Z",
            "shortDescription": {
                "problem": "Underutilized virtual machine",
                "solution": "Resize or shut down the VM",
            },
            "resourceMetadata": {
                "resourceId": "/subscriptions/Sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
            },
            "extendedProperties": {
                "savingsAmount": "120.50",
                "annualSavingsAmount": "1446.00",
            },
        },
    }
    item.update(overrides)
    return item


def test_normalize_advisor_item_maps_fields():
    row = normalize_advisor_item(_sample_advisor_item(), "sub-1")
    assert row["recommendation_id"] == "rec-001"
    assert row["resource_id"].endswith("/virtualmachines/vm1")
    assert row["category"] == "Cost"
    assert row["impact"] == "High"
    assert row["potential_savings_monthly"] == 120.50
    assert row["potential_savings_yearly"] == 1446.00
    assert row["summary"] == "Underutilized virtual machine"


def test_resolve_resource_id_from_arm_recommendation_id():
    item = _sample_advisor_item()
    item["properties"]["resourceMetadata"] = {}
    item["id"] = (
        "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/"
        "virtualMachines/vm1/providers/Microsoft.Advisor/recommendations/rec-001"
    )
    rid = _resolve_resource_id(item, item["properties"])
    assert rid.endswith("/virtualmachines/vm1")


def test_normalize_advisor_item_uses_impacted_value_arm_id():
    item = _sample_advisor_item()
    item["properties"]["resourceMetadata"] = {}
    item["properties"]["impactedValue"] = (
        "/subscriptions/Sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/disk1"
    )
    row = normalize_advisor_item(item, "sub-1")
    assert row["resource_id"].endswith("/disks/disk1")


def test_normalize_advisor_item_uses_impacted_resources():
    item = _sample_advisor_item()
    item["properties"]["resourceMetadata"] = {}
    item["properties"]["impactedValue"] = ""
    item["properties"]["impactedResources"] = [
        {"resourceId": "/subscriptions/Sub-1/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/sa1"},
    ]
    row = normalize_advisor_item(item, "sub-1")
    assert row["resource_id"].endswith("/storageaccounts/sa1")


def test_upsert_advisor_recommendations_is_idempotent(db_session):
    db_session.add(SubscriptionCache(
        subscription_id="sub-1",
        display_name="Test",
        state="Enabled",
    ))
    db_session.commit()

    counts = upsert_advisor_recommendations(db_session, "sub-1", [_sample_advisor_item()])
    assert counts["created"] == 1
    assert counts["updated"] == 0

    updated_item = _sample_advisor_item()
    updated_item["properties"]["impact"] = "Medium"
    counts2 = upsert_advisor_recommendations(db_session, "sub-1", [updated_item])
    assert counts2["created"] == 0
    assert counts2["updated"] == 1

    rows = db_session.query(AdvisorRecommendation).all()
    assert len(rows) == 1
    assert rows[0].impact == "Medium"


def test_list_stored_advisor_recommendations_filters_category(db_session):
    db_session.add(AdvisorRecommendation(
        id=str(uuid.uuid4()),
        recommendation_id="a",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        subscription_id="sub-1",
        category="Cost",
        impact="High",
        summary="Cost rec",
        potential_savings_monthly=50.0,
        status="Active",
        generated_at=datetime.now(timezone.utc),
    ))
    db_session.add(AdvisorRecommendation(
        id=str(uuid.uuid4()),
        recommendation_id="b",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm2",
        subscription_id="sub-1",
        category="Security",
        impact="Low",
        summary="Security rec",
        status="Active",
        generated_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    result = list_stored_advisor_recommendations(db_session, "sub-1", category="Cost")
    assert result["total"] == 1
    assert result["items"][0]["category"] == "Cost"


def test_sync_azure_advisor_recommendations_fetches_and_stores():
    from app.advisor_sync import sync_azure_advisor_recommendations

    db = MagicMock()
    token = "token"
    items = [_sample_advisor_item()]

    with patch("app.advisor_sync.arm_auth_context"):
        with patch("app.advisor_sync.AdvisorClient") as client_cls:
            client = MagicMock()
            client.list_recommendations.return_value = items
            client_cls.return_value = client
            with patch("app.advisor_sync.upsert_advisor_recommendations", return_value={"created": 1, "updated": 0, "skipped": 0}) as upsert:
                db.query.return_value.filter.return_value.all.return_value = []
                result = sync_azure_advisor_recommendations("sub-1", db, token)

    assert result["status"] == "ok"
    assert result["fetched"] == 1
    upsert.assert_called_once_with(db, "sub-1", items)

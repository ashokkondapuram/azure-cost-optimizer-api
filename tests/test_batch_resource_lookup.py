"""Tests for batch resource lookup API."""

import pytest
from unittest.mock import ANY, patch

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.integration_app import app
from app.data_store.enrichment_registry import clear_all_enrichment_tables
from app.models import AppUser, ResourceSnapshot
from app.user_auth import ROLE_ADMIN, hash_password

SUBSCRIPTION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
RESOURCE_ID = (
    f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/rg/providers/"
    "Microsoft.Compute/virtualMachines/vm1"
)


def _auth_client() -> TestClient:
    init_db()
    db = SessionLocal()
    try:
        db.query(AppUser).delete()
        clear_all_enrichment_tables(db)
        db.query(ResourceSnapshot).delete()
        db.commit()
        db.add(
            AppUser(
                id="admin-batch-lookup",
                username="admin",
                display_name="Administrator",
                password_hash=hash_password("password123"),
                role=ROLE_ADMIN,
                is_active=True,
            )
        )
        db.add(
            ResourceSnapshot(
                id="snap-batch-lookup",
                subscription_id=SUBSCRIPTION_ID,
                resource_id=RESOURCE_ID.lower(),
                resource_name="vm1",
                resource_type="compute/vm",
                resource_group="rg",
                location="eastus",
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    token = login.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_batch_resource_lookup_accepts_object_shaped_timespan():
    client = _auth_client()
    metrics_payload = {
        "ok": True,
        "metrics": [],
        "derived": [],
        "metrics_raw": {"value": []},
        "cost_driver_mapping": {"cost_drivers": [], "properties": []},
    }

    with patch("app.metrics_api.fetch_metrics_for_resource", return_value=metrics_payload):
        resp = client.post(
            "/optimize/resources/batch-lookup",
            json={
                "subscription_id": SUBSCRIPTION_ID,
                "resource_ids": [RESOURCE_ID],
                "timespan": {"value": "P7D", "label": "Last 7 days"},
                "include_metrics": True,
                "include_advanced_analysis": False,
                "profile": "drawer",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["count"] == 1


def test_batch_resource_lookup_uses_enrichment_when_cached():
    client = _auth_client()
    from datetime import datetime, timezone

    from app.database import SessionLocal
    from app.data_store.resource_enrichment import upsert_metrics, upsert_recommendations
    from app.models import ResourceSnapshot

    db = SessionLocal()
    try:
        snap = db.query(ResourceSnapshot).filter(
            ResourceSnapshot.resource_id == RESOURCE_ID.lower()
        ).one()
        upsert_metrics(
            db,
            snap,
            {},
            metrics_payload={
                "ok": True,
                "metrics": [{"fact_key": "avg_cpu_pct", "label": "CPU", "stats": {"average": 5}}],
                "derived": [],
                "facts": {"avg_cpu_pct": 5},
            },
        )
        db.flush()
        upsert_recommendations(
            db,
            snap,
            summary=[{"rule_id": "VM_IDLE", "severity": "HIGH"}],
            findings_count=1,
            savings_usd=10.0,
            top_severity="HIGH",
        )
        db.commit()
    finally:
        db.close()

    with patch("app.metrics_api.fetch_metrics_for_resource") as metrics_mock, patch(
        "app.resource_advanced_analysis.get_resource_advanced_analysis",
    ) as analysis_mock:
        resp = client.post(
            "/optimize/resources/batch-lookup",
            json={
                "subscription_id": SUBSCRIPTION_ID,
                "resource_ids": [RESOURCE_ID],
                "timespan": "P7D",
                "include_metrics": True,
                "include_advanced_analysis": True,
                "profile": "drawer",
            },
        )

    assert resp.status_code == 200
    entry = resp.json()["items"][RESOURCE_ID.lower()]
    assert entry["metrics_source"] == "db"
    assert entry["metrics"]["metrics"][0]["fact_key"] == "avg_cpu_pct"
    assert entry["advanced_analysis"]["insights"]["headline"]
    metrics_mock.assert_not_called()
    analysis_mock.assert_not_called()


def test_batch_resource_lookup_returns_metrics_and_analysis():
    client = _auth_client()
    metrics_payload = {
        "ok": True,
        "metrics": [{"fact_key": "avg_cpu_pct", "label": "CPU", "stats": {"average": 5}}],
        "derived": [],
        "metrics_raw": {"value": []},
        "cost_driver_mapping": {"cost_drivers": [], "properties": []},
    }
    analysis_payload = {
        "insights": {"headline": "ok"},
        "trends": None,
    }

    with patch("app.metrics_api.fetch_metrics_for_resource", return_value=metrics_payload) as metrics_mock, patch(
        "app.resource_advanced_analysis.get_resource_advanced_analysis",
        return_value=analysis_payload,
    ) as analysis_mock, patch(
        "app.metrics_api._load_inventory_row",
        return_value={"monthlyCostBilling": 55.0, "billingCurrency": "CAD"},
    ):
        resp = client.post(
            "/optimize/resources/batch-lookup",
            json={
                "subscription_id": SUBSCRIPTION_ID,
                "resource_ids": [RESOURCE_ID],
                "timespan": "P7D",
                "include_metrics": True,
                "include_advanced_analysis": True,
                "profile": "drawer",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["profile"] == "drawer"
    entry = body["items"][RESOURCE_ID.lower()]
    assert "metrics_raw" not in entry["metrics"]
    assert entry["metrics"]["metrics"][0]["fact_key"] == "avg_cpu_pct"
    assert entry["advanced_analysis"] == analysis_payload
    assert entry["cost"]["monthlyCostBilling"] == pytest.approx(55.0)
    metrics_mock.assert_called_once()
    analysis_mock.assert_called_once_with(ANY, SUBSCRIPTION_ID, RESOURCE_ID, profile="drawer")

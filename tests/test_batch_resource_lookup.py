"""Tests for batch resource lookup API."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
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


def test_batch_resource_lookup_returns_metrics_and_analysis():
    client = _auth_client()
    metrics_payload = {"ok": True, "metrics": [], "derived": []}
    analysis_payload = {"scorecard": None, "workload_profile": None}

    with patch("app.metrics_api.fetch_metrics_for_resource", return_value=metrics_payload) as metrics_mock, patch(
        "app.resource_advanced_analysis.get_resource_advanced_analysis",
        return_value=analysis_payload,
    ) as analysis_mock:
        resp = client.post(
            "/optimize/resources/batch-lookup",
            json={
                "subscription_id": SUBSCRIPTION_ID,
                "resource_ids": [RESOURCE_ID],
                "timespan": "P7D",
                "include_metrics": True,
                "include_advanced_analysis": True,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    entry = body["items"][RESOURCE_ID.lower()]
    assert entry["metrics"] == metrics_payload
    assert entry["advanced_analysis"] == analysis_payload
    metrics_mock.assert_called_once()
    analysis_mock.assert_called_once()

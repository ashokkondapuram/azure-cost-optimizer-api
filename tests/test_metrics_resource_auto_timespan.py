"""Tests for drawer metrics auto-fetch timespan coercion."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.integration_app import app
from app.models import AppUser
from app.user_auth import ROLE_ADMIN, hash_password

RESOURCE_ID = (
    "/subscriptions/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/resourceGroups/rg/providers/"
    "Microsoft.Compute/virtualMachines/vm1"
)


def _auth_client() -> TestClient:
    init_db()
    db = SessionLocal()
    try:
        db.query(AppUser).delete()
        db.commit()
        db.add(
            AppUser(
                id="admin-metrics-auto",
                username="admin",
                display_name="Administrator",
                password_hash=hash_password("password123"),
                role=ROLE_ADMIN,
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


def test_metrics_resource_auto_accepts_object_shaped_timespan_query():
    client = _auth_client()
    metrics_payload = {"ok": True, "metrics": [], "derived": []}

    with patch("app.metrics_api.fetch_metrics_for_resource", return_value=metrics_payload) as metrics_mock:
        resp = client.get(
            "/metrics/resource/auto",
            params={
                "resource_id": RESOURCE_ID,
                "timespan[value]": "P7D",
                "timespan[label]": "Last 7 days",
            },
        )

    assert resp.status_code == 200
    metrics_mock.assert_called_once()
    assert metrics_mock.call_args.kwargs["timespan"] == "P7D"

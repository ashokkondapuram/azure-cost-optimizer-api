"""Subscription allowlist on data endpoints."""
from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.models import AppUser, ResourceSnapshot, SubscriptionCache, SystemSetting
from app.user_auth import ROLE_ADMIN, ROLE_VIEWER, hash_password


def _auth_client() -> TestClient:
    init_db()
    db = SessionLocal()
    try:
        db.query(AppUser).delete()
        db.query(ResourceSnapshot).delete()
        db.query(SubscriptionCache).delete()
        db.query(SystemSetting).delete()
        db.commit()
        db.add(
            AppUser(
                id="admin-scope-test",
                username="admin",
                display_name="Administrator",
                password_hash=hash_password("password123"),
                role=ROLE_ADMIN,
                is_active=True,
            )
        )
        db.add(
            ResourceSnapshot(
                id="snap-1",
                subscription_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                resource_id="/subscriptions/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
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


def test_costs_rejects_unknown_subscription():
    client = _auth_client()
    resp = client.get(
        "/costs",
        params={"subscription_id": "00000000-0000-0000-0000-000000000099"},
    )
    assert resp.status_code == 404


def test_costs_allows_synced_subscription():
    client = _auth_client()
    resp = client.get(
        "/costs",
        params={"subscription_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
    )
    assert resp.status_code == 200


def test_cost_history_requires_subscription_id():
    client = _auth_client()
    resp = client.get("/costs/history")
    assert resp.status_code == 422


def test_cost_history_scoped_to_subscription():
    client = _auth_client()
    resp = client.get(
        "/costs/history",
        params={"subscription_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_catalog_only_subscription_rejected():
    client = _auth_client()
    db = SessionLocal()
    try:
        db.add(
            SubscriptionCache(
                subscription_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                display_name="Catalog only",
                state="Enabled",
                raw_json="{}",
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get(
        "/costs",
        params={"subscription_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"},
    )
    assert resp.status_code == 404


def test_viewer_cannot_fetch_subscription_metrics():
    from tests.auth_helpers import auth_header, seed_app_user

    _auth_client()
    seed_app_user(user_id="viewer-scope", username="viewer", role=ROLE_VIEWER)
    viewer = TestClient(app)
    viewer.headers.update(auth_header(user_id="viewer-scope", username="viewer", role=ROLE_VIEWER))
    resp = viewer.get(
        "/metrics/subscription",
        params={"subscription_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
    )
    assert resp.status_code == 403


def test_resources_all_requires_synced_subscription():
    client = _auth_client()
    resp = client.get(
        "/resources/all",
        params={"subscription_id": "00000000-0000-0000-0000-000000000099"},
    )
    assert resp.status_code == 404

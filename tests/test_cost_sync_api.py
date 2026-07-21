"""Tests for async POST /costs/sync."""

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.integration_app import app
from app.models import AppUser
from app.user_auth import ROLE_ADMIN, hash_password

SUBSCRIPTION_ID = str(uuid.uuid4())


def _auth_client() -> TestClient:
    init_db()
    db = SessionLocal()
    try:
        db.query(AppUser).filter(AppUser.username == "admin").delete()
        db.commit()
        db.add(
            AppUser(
                id="admin-cost-sync",
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


def test_cost_sync_returns_202_and_enqueues_background():
    client = _auth_client()
    sub = SUBSCRIPTION_ID.lower()
    with patch("app.routers.costs._scoped_subscription", return_value=sub):
        with patch("app.cost_explorer_worker.request_cost_sync", return_value=True) as enqueue:
            with patch("app.cost_explorer_worker.is_cost_sync_pending", return_value=True):
                res = client.post(
                    "/api/costs/sync",
                    params={"subscription_id": SUBSCRIPTION_ID},
                )
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["status"] == "accepted"
    assert body["async"] is True
    enqueue.assert_called_once_with(sub, reason="manual_api")


def test_cost_sync_wait_true_runs_inline():
    client = _auth_client()
    sub = SUBSCRIPTION_ID.lower()
    synced = {"api_rows": 3, "cost_by_service": 2}
    with patch("app.routers.costs._scoped_subscription", return_value=sub):
        with patch("app.routers.costs.sync_costs", return_value=synced) as run_sync:
            res = client.post(
                "/api/costs/sync",
                params={"subscription_id": SUBSCRIPTION_ID, "wait": "true"},
            )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ok"
    assert body["synced"] == synced
    assert body["async"] is False
    run_sync.assert_called_once()

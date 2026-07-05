"""Findings API subscription scoping."""
from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.models import AppUser
from app.user_auth import ROLE_ADMIN, hash_password


def _seed_admin(db) -> None:
    db.query(AppUser).delete()
    db.commit()
    db.add(
        AppUser(
            id="admin-findings-test",
            username="admin",
            display_name="Administrator",
            password_hash=hash_password("password123"),
            role=ROLE_ADMIN,
            is_active=True,
        )
    )
    db.commit()


def _auth_client() -> TestClient:
    init_db()
    db = SessionLocal()
    try:
        _seed_admin(db)
    finally:
        db.close()

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    token = login.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_findings_requires_subscription_id():
    client = _auth_client()
    resp = client.get("/optimize/findings")
    assert resp.status_code == 422


def test_findings_summary_requires_subscription_id():
    client = _auth_client()
    resp = client.get("/optimize/findings/summary")
    assert resp.status_code == 422


def test_findings_rejects_unknown_subscription():
    client = _auth_client()
    resp = client.get(
        "/optimize/findings",
        params={"subscription_id": "00000000-0000-0000-0000-000000000099"},
    )
    assert resp.status_code == 404

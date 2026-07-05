"""Auth coverage for dashboard alias routes."""
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
            id="admin-user-id",
            username="admin",
            display_name="Administrator",
            password_hash=hash_password("password123"),
            role=ROLE_ADMIN,
            is_active=True,
        )
    )
    db.commit()


def test_dashboard_overview_requires_auth():
    init_db()
    client = TestClient(app)
    resp = client.get(
        "/dashboard/overview",
        params={"subscription_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 401


def test_dashboard_overview_allows_authenticated_user():
    init_db()
    db = SessionLocal()
    try:
        _seed_admin(db)
    finally:
        db.close()

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    token = login.json()["access_token"]
    resp = client.get(
        "/dashboard/overview",
        params={"subscription_id": "00000000-0000-0000-0000-000000000001"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in {200, 404, 422, 500}


def test_sync_status_requires_auth():
    init_db()
    client = TestClient(app)
    resp = client.get("/sync/status")
    assert resp.status_code == 401

"""Login and session persistence tests."""

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.models import AppUser
from app.user_auth import ROLE_ADMIN, create_access_token, hash_password


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


def test_login_and_auth_me_roundtrip():
    init_db()
    db = SessionLocal()
    try:
        _seed_admin(db)
    finally:
        db.close()

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["username"] == "admin"
    assert body["role"] == ROLE_ADMIN


def test_auth_me_rejects_invalid_token():
    client = TestClient(app)
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


def test_auth_me_rejects_token_when_user_missing_from_database():
    token = create_access_token(user_id="missing-user", username="admin", role=ROLE_ADMIN)
    client = TestClient(app)
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401

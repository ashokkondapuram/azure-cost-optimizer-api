"""K8s snapshot read routes must accept JWT sessions, not only agent API keys."""
from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.integration_app import app
from app.models import AppUser
from app.user_auth import ROLE_VIEWER, hash_password


def _seed_viewer(db) -> None:
    db.query(AppUser).delete()
    db.commit()
    db.add(
        AppUser(
            id="viewer-user-id",
            username="viewer",
            display_name="Viewer",
            password_hash=hash_password("password123"),
            role=ROLE_VIEWER,
            is_active=True,
        )
    )
    db.commit()


def test_k8s_snapshots_rejects_unauthenticated():
    init_db()
    client = TestClient(app)
    resp = client.get("/api/k8s/snapshots")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Sign in required"


def test_k8s_snapshots_allows_signed_in_user():
    init_db()
    db = SessionLocal()
    try:
        _seed_viewer(db)
    finally:
        db.close()

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "viewer", "password": "password123"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    resp = client.get(
        "/api/k8s/snapshots",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

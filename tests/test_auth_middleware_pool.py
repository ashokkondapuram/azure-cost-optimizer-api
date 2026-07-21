"""Auth middleware database pool safety tests."""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.integration_app import app
from app.models import AppUser
from app.user_auth import ROLE_ADMIN, clear_auth_user_cache, create_access_token, hash_password

ROOT = Path(__file__).resolve().parents[1]


def _load_platform_main(service_name: str):
    service_src = ROOT / "services" / service_name / "src" / "main.py"
    spec = importlib.util.spec_from_file_location(f"{service_name}_main", service_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_health_live_skips_middleware_database_lookup():
    with patch("app.middleware.app_auth.resolve_authenticated_user") as mock_resolve:
        client = TestClient(app)
        res = client.get("/health/live")

    assert res.status_code == 200
    mock_resolve.assert_not_called()


def test_platform_analysis_health_skips_middleware_database_lookup():
    module = _load_platform_main("platform-analysis")
    with patch("app.middleware.app_auth.resolve_authenticated_user") as mock_resolve:
        client = TestClient(module.app)
        res = client.get("/health/live")

    assert res.status_code == 200
    assert res.json()["service"] == "platform-analysis"
    mock_resolve.assert_not_called()


def test_auth_middleware_closes_database_session_on_cache_miss():
    init_db()
    clear_auth_user_cache()

    db = SessionLocal()
    try:
        db.query(AppUser).delete()
        db.commit()
        db.add(
            AppUser(
                id="pool-test-user",
                username="pooluser",
                display_name="Pool User",
                password_hash=hash_password("password123"),
                role=ROLE_ADMIN,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    token = create_access_token(user_id="pool-test-user", username="pooluser", role=ROLE_ADMIN)
    closed = {"value": False}

    @contextmanager
    def _tracking_scoped_session():
        session = SessionLocal()
        try:
            yield session
        finally:
            closed["value"] = True
            session.close()

    with patch("app.auth.scoped_session", side_effect=_tracking_scoped_session):
        client = TestClient(app)
        res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    assert closed["value"] is True


def test_auth_middleware_uses_cached_user_without_second_database_lookup():
    init_db()
    clear_auth_user_cache()

    db = SessionLocal()
    try:
        db.query(AppUser).delete()
        db.commit()
        db.add(
            AppUser(
                id="cache-test-user",
                username="cacheuser",
                display_name="Cache User",
                password_hash=hash_password("password123"),
                role=ROLE_ADMIN,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    token = create_access_token(user_id="cache-test-user", username="cacheuser", role=ROLE_ADMIN)
    scoped_calls = {"count": 0}

    @contextmanager
    def _counting_scoped_session():
        scoped_calls["count"] += 1
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    with patch("app.auth.scoped_session", side_effect=_counting_scoped_session):
        client = TestClient(app)
        first = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        second = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert scoped_calls["count"] == 1

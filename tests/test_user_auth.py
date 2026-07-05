"""Tests for local app user bootstrap and authentication."""

import uuid

from app.database import SessionLocal, init_db
from app.models import AppUser
from app.user_auth import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    authenticate_user,
    create_app_user,
    ensure_default_admin,
    ensure_default_viewer,
    reset_app_user_password,
    verify_password,
)


def test_viewer_user_bootstrapped_with_no_admin_privileges():
    init_db()
    db = SessionLocal()
    try:
        db.query(AppUser).delete()
        db.commit()

        ensure_default_admin(db)
        ensure_default_viewer(db)

        admin = db.query(AppUser).filter(AppUser.username == "admin").first()
        viewer = db.query(AppUser).filter(AppUser.username == "viewer").first()

        assert admin is not None
        assert admin.role == ROLE_ADMIN
        assert viewer is not None
        assert viewer.role == ROLE_VIEWER

        assert authenticate_user(db, "viewer", "viewer") is not None
        assert authenticate_user(db, "viewer", "wrong") is None
    finally:
        db.close()


def test_ensure_default_viewer_is_idempotent():
    init_db()
    db = SessionLocal()
    try:
        ensure_default_viewer(db)
        count_before = db.query(AppUser).filter(AppUser.username == "viewer").count()
        ensure_default_viewer(db)
        count_after = db.query(AppUser).filter(AppUser.username == "viewer").count()
        assert count_before == count_after == 1
    finally:
        db.close()


def test_create_and_reset_user_password():
    init_db()
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]
        user = create_app_user(
            db,
            username=f"testuser_{suffix}",
            password="password123",
            display_name="Test User",
            role=ROLE_VIEWER,
        )
        assert user.role == ROLE_VIEWER
        assert authenticate_user(db, user.username, "password123") is not None

        reset_app_user_password(db, user.id, "newpassword99")
        assert authenticate_user(db, user.username, "password123") is None
        assert authenticate_user(db, user.username, "newpassword99") is not None
        assert verify_password("newpassword99", user.password_hash)
    finally:
        db.query(AppUser).filter(AppUser.username.like("testuser_%")).delete()
        db.commit()
        db.close()

"""Seed app users for JWT auth tests."""

from app.database import SessionLocal, init_db
from app.models import AppUser
from app.user_auth import ROLE_ADMIN, ROLE_VIEWER, create_access_token, hash_password


def seed_app_user(*, user_id: str, username: str, role: str = ROLE_VIEWER) -> None:
    init_db()
    db = SessionLocal()
    try:
        row = db.query(AppUser).filter(AppUser.id == user_id).first()
        if row:
            return
        existing_name = db.query(AppUser).filter(AppUser.username == username).first()
        if existing_name:
            return
        db.add(
            AppUser(
                id=user_id,
                username=username,
                display_name=username,
                password_hash=hash_password("password123"),
                role=role,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()


def auth_header(*, user_id: str, username: str, role: str) -> dict[str, str]:
    seed_app_user(user_id=user_id, username=username, role=role)
    token = create_access_token(user_id=user_id, username=username, role=role)
    return {"Authorization": f"Bearer {token}"}

"""Application user authentication (local username/password — not Azure AD)."""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
import structlog
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.models import AppUser
from app.settings import get_settings

log = structlog.get_logger()

ALGORITHM = "HS256"


def token_expire_delta() -> timedelta:
    """Absolute JWT lifetime (renewed while the user is active). Default 8 hours."""
    hours_raw = os.getenv("JWT_EXPIRE_HOURS")
    if hours_raw is not None and str(hours_raw).strip() != "":
        return timedelta(hours=int(hours_raw))
    minutes_raw = os.getenv("JWT_EXPIRE_MINUTES")
    if minutes_raw is not None and str(minutes_raw).strip() != "":
        return timedelta(minutes=int(minutes_raw))
    return timedelta(hours=8)


def session_idle_minutes() -> int:
    """Frontend inactivity logout hint — default 1 minute."""
    return max(1, int(os.getenv("SESSION_IDLE_MINUTES", "1")))
ROLE_SUPERUSER = "superuser"
ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
VALID_ROLES = {ROLE_SUPERUSER, ROLE_ADMIN, ROLE_VIEWER}
PRIVILEGED_ROLES = {ROLE_SUPERUSER, ROLE_ADMIN}
_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,64}$")

_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_LOGIN_MAX_ATTEMPTS = 8
_LOGIN_WINDOW_SECONDS = 900


def _purge_old_login_attempts(db: Session, cutoff) -> None:
    from app.models import LoginAttempt

    db.query(LoginAttempt).filter(LoginAttempt.attempted_at < cutoff).delete()
    db.commit()


def check_login_rate_limit(db: Session, client_key: str) -> bool:
    from datetime import datetime, timedelta, timezone

    from app.models import LoginAttempt

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=_LOGIN_WINDOW_SECONDS)
    _purge_old_login_attempts(db, cutoff)
    count = (
        db.query(LoginAttempt)
        .filter(LoginAttempt.client_key == client_key, LoginAttempt.attempted_at >= cutoff)
        .count()
    )
    if count >= _LOGIN_MAX_ATTEMPTS:
        return False
    # Fallback for environments without migrated login_attempts table.
    import time

    window_start = time.time() - _LOGIN_WINDOW_SECONDS
    mem_attempts = [t for t in _LOGIN_ATTEMPTS.get(client_key, []) if t >= window_start]
    return len(mem_attempts) < _LOGIN_MAX_ATTEMPTS


def record_login_failure(db: Session, client_key: str) -> None:
    from datetime import datetime, timezone

    from app.models import LoginAttempt

    db.add(LoginAttempt(client_key=client_key, attempted_at=datetime.now(timezone.utc)))
    db.commit()
    import time

    _LOGIN_ATTEMPTS.setdefault(client_key, []).append(time.time())


def clear_login_failures(db: Session, client_key: str) -> None:
    from app.models import LoginAttempt

    db.query(LoginAttempt).filter(LoginAttempt.client_key == client_key).delete()
    db.commit()
    _LOGIN_ATTEMPTS.pop(client_key, None)


def jwt_secret_configured() -> bool:
    return get_settings().jwt_configured


def _jwt_secret() -> str:
    # Read env on every call so App Service setting updates are not masked by lru_cache.
    secret = (os.getenv("JWT_SECRET") or "").strip()
    if not secret:
        secret = get_settings().jwt_secret
    if secret:
        return secret
    if get_settings().is_production:
        raise RuntimeError(
            "JWT_SECRET is required in production (set it in App Service application settings)",
        )
    return "dev-insecure-jwt-secret-change-me"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, digest = stored_hash.split("$", 1)
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000).hex()
    return secrets.compare_digest(check, digest)


def create_access_token(*, user_id: str, username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + token_expire_delta()).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def user_from_request(request: Request) -> Optional[dict[str, Any]]:
    return getattr(request.state, "user", None)


def require_authenticated_user(request: Request) -> dict[str, Any]:
    user = user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


def is_privileged_role(role: str | None) -> bool:
    return (role or "").strip().lower() in PRIVILEGED_ROLES


def is_superuser_role(role: str | None) -> bool:
    return (role or "").strip().lower() == ROLE_SUPERUSER


def require_admin_user(request: Request) -> dict[str, Any]:
    user = require_authenticated_user(request)
    if not is_privileged_role(user.get("role")):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_superuser(request: Request) -> dict[str, Any]:
    user = require_authenticated_user(request)
    if not is_superuser_role(user.get("role")):
        raise HTTPException(status_code=403, detail="Superuser access required")
    return user


def authenticate_user(db: Session, username: str, password: str) -> Optional[AppUser]:
    row = (
        db.query(AppUser)
        .filter(AppUser.username == username.strip().lower(), AppUser.is_active.is_(True))
        .first()
    )
    if not row or not verify_password(password, row.password_hash):
        return None
    return row


def _bootstrap_password(settings, *, env_password: str, dev_default: str, account: str) -> str | None:
    password = env_password
    if not password:
        if settings.is_production:
            log.warning(f"{account}_bootstrap_skipped", reason=f"{account.upper()}_PASSWORD not set")
            return None
        password = dev_default
        log.warning("dev_default_login_enabled", username=account)
    return password


def ensure_default_admin(db: Session) -> None:
    """Create the initial local admin when no users exist (not Azure AD)."""
    if db.query(AppUser).count() > 0:
        return

    settings = get_settings()
    username = (settings.admin_username or "admin").strip().lower()
    password = _bootstrap_password(
        settings,
        env_password=settings.admin_password,
        dev_default="admin",
        account=username,
    )
    if not password:
        return

    user = AppUser(
        id=str(uuid.uuid4()),
        username=username,
        display_name="Administrator",
        password_hash=hash_password(password),
        role=ROLE_ADMIN,
        is_active=True,
    )
    db.add(user)
    db.commit()
    log.info("app_user_bootstrapped", username=username, role=ROLE_ADMIN)


def ensure_default_viewer(db: Session) -> None:
    """Ensure a read-only viewer account exists (no admin privileges)."""
    settings = get_settings()
    username = (settings.viewer_username or "viewer").strip().lower()
    if not username:
        return

    existing = db.query(AppUser).filter(AppUser.username == username).first()
    if existing:
        return

    password = _bootstrap_password(
        settings,
        env_password=settings.viewer_password,
        dev_default="viewer",
        account=username,
    )
    if not password:
        return

    user = AppUser(
        id=str(uuid.uuid4()),
        username=username,
        display_name="Viewer",
        password_hash=hash_password(password),
        role=ROLE_VIEWER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    log.info("app_user_bootstrapped", username=username, role=ROLE_VIEWER)


def ensure_default_superuser(db: Session) -> None:
    """Create the initial superuser when SUPERUSER_PASSWORD is configured."""
    if db.query(AppUser).filter(AppUser.role == ROLE_SUPERUSER).first():
        return

    settings = get_settings()
    username = (os.getenv("SUPERUSER_USERNAME") or "superuser").strip().lower()
    if not username:
        return

    if db.query(AppUser).filter(AppUser.username == username).first():
        return

    password = _bootstrap_password(
        settings,
        env_password=(os.getenv("SUPERUSER_PASSWORD") or "").strip(),
        dev_default="superuser",
        account=username,
    )
    if not password:
        return

    user = AppUser(
        id=str(uuid.uuid4()),
        username=username,
        display_name="Superuser",
        password_hash=hash_password(password),
        role=ROLE_SUPERUSER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    log.info("app_user_bootstrapped", username=username, role=ROLE_SUPERUSER)


def parse_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def serialize_app_user(user: AppUser) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "role": user.role,
        "is_active": bool(user.is_active),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def list_app_users(db: Session) -> list[dict[str, Any]]:
    rows = db.query(AppUser).order_by(AppUser.username).all()
    return [serialize_app_user(row) for row in rows]


def count_active_admins(db: Session) -> int:
    return (
        db.query(AppUser)
        .filter(AppUser.role.in_([ROLE_ADMIN, ROLE_SUPERUSER]), AppUser.is_active.is_(True))
        .count()
    )


def normalize_username(username: str) -> str:
    value = (username or "").strip().lower()
    if not _USERNAME_RE.match(value):
        raise ValueError(
            "Username must be 3–64 characters and use only letters, numbers, periods, underscores, or hyphens."
        )
    return value


def validate_password(password: str) -> None:
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters.")


def create_app_user(
    db: Session,
    *,
    username: str,
    password: str,
    display_name: str | None = None,
    role: str = ROLE_VIEWER,
    actor_role: str | None = None,
) -> AppUser:
    uname = normalize_username(username)
    validate_password(password)
    role_key = (role or ROLE_VIEWER).strip().lower()
    if role_key not in VALID_ROLES:
        raise ValueError(f"Role must be one of: {', '.join(sorted(VALID_ROLES))}")
    if role_key == ROLE_SUPERUSER and not is_superuser_role(actor_role):
        raise ValueError("Only a superuser can create another superuser account.")

    existing = db.query(AppUser).filter(AppUser.username == uname).first()
    if existing:
        raise ValueError("That username is already in use.")

    user = AppUser(
        id=str(uuid.uuid4()),
        username=uname,
        display_name=(display_name or uname).strip() or uname,
        password_hash=hash_password(password),
        role=role_key,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log.info("app_user_created", username=uname, role=role_key)
    return user


def reset_app_user_password(db: Session, user_id: str, password: str) -> AppUser:
    validate_password(password)
    row = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not row:
        raise ValueError("User not found.")
    if not row.is_active:
        raise ValueError("Cannot reset password for an inactive user.")

    row.password_hash = hash_password(password)
    db.commit()
    db.refresh(row)
    log.info("app_user_password_reset", username=row.username, user_id=user_id)
    return row

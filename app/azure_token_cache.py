"""PostgreSQL-backed Azure AD token cache with expiry and encryption at rest."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import AzureTokenCache
from app.security.secrets import decrypt_value, encrypt_value

REFRESH_MARGIN_SECONDS = 60


def credential_cache_key(config: dict[str, Any], scope: str) -> str:
    """Stable key per auth mode + identity (secret fingerprint, not the secret itself)."""
    auth_mode = (config.get("auth_mode") or "managed_identity").strip()
    tenant_id = (config.get("tenant_id") or "").strip()
    client_id = (config.get("client_id") or "").strip()
    secret = config.get("client_secret") or ""
    secret_fp = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16] if secret else ""
    raw = f"{scope}|{auth_mode}|{tenant_id}|{client_id}|{secret_fp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _expires_dt(expires_on: float) -> datetime:
    return datetime.fromtimestamp(float(expires_on), tz=timezone.utc)


def _is_valid(expires_at: datetime, margin_seconds: int = REFRESH_MARGIN_SECONDS) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at.timestamp() - time.time() > margin_seconds


def read_cached_token(
    db: Session,
    cache_key: str,
    *,
    margin_seconds: int = REFRESH_MARGIN_SECONDS,
) -> tuple[str, float] | None:
    """Return (token, expires_on_unix) when a non-expired row exists."""
    row = (
        db.query(AzureTokenCache)
        .filter(AzureTokenCache.cache_key == cache_key)
        .first()
    )
    if not row:
        return None
    if not _is_valid(row.expires_at, margin_seconds):
        db.delete(row)
        db.commit()
        return None
    try:
        token = decrypt_value(row.access_token)
    except Exception:
        db.delete(row)
        db.commit()
        return None
    if not token:
        return None
    expires_on = row.expires_at.timestamp()
    return token, expires_on


def write_cached_token(
    db: Session,
    *,
    cache_key: str,
    scope: str,
    token: str,
    expires_on: float,
) -> None:
    """Upsert encrypted token; purge other expired rows."""
    now = datetime.now(timezone.utc)
    encrypted = encrypt_value(token)
    expires_at = _expires_dt(expires_on)
    row = (
        db.query(AzureTokenCache)
        .filter(AzureTokenCache.cache_key == cache_key)
        .first()
    )
    if row:
        row.scope = scope
        row.access_token = encrypted
        row.expires_at = expires_at
        row.updated_at = now
    else:
        db.add(AzureTokenCache(
            cache_key=cache_key,
            scope=scope,
            access_token=encrypted,
            expires_at=expires_at,
            updated_at=now,
        ))
    db.query(AzureTokenCache).filter(AzureTokenCache.expires_at <= now).delete(
        synchronize_session=False,
    )
    db.commit()


def clear_token_cache(db: Session, cache_key: str | None = None) -> int:
    """Delete cached token(s). Returns rows removed."""
    q = db.query(AzureTokenCache)
    if cache_key:
        q = q.filter(AzureTokenCache.cache_key == cache_key)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return deleted


def get_token_cache_status(db: Session, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """ARM token cache row for the active credential (PostgreSQL-backed)."""
    from app.auth import ARM_SCOPE, resolve_auth_config

    cfg = config if config is not None else resolve_auth_config(db)
    cache_key = credential_cache_key(cfg, ARM_SCOPE)
    row = (
        db.query(AzureTokenCache)
        .filter(AzureTokenCache.cache_key == cache_key)
        .first()
    )
    if not row:
        return {
            "cached": False,
            "freshness": "never",
            "status": "empty",
            "expires_at": None,
            "updated_at": None,
        }
    valid = _is_valid(row.expires_at)
    freshness = "fresh" if valid else "stale"
    return {
        "cached": True,
        "freshness": freshness,
        "status": "success" if valid else "expired",
        "expires_at": row.expires_at.astimezone(timezone.utc).isoformat()
        if row.expires_at and row.expires_at.tzinfo
        else (row.expires_at.isoformat() if row.expires_at else None),
        "updated_at": row.updated_at.astimezone(timezone.utc).isoformat()
        if row.updated_at and getattr(row.updated_at, "tzinfo", None)
        else (row.updated_at.isoformat() if row.updated_at else None),
    }

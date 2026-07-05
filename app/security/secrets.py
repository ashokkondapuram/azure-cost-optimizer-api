"""Encrypt/decrypt sensitive setting values at rest."""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc:"


def _derive_fernet_key(source: str) -> bytes:
    return base64.urlsafe_b64encode(
        hashlib.sha256(f"settings-encryption:{source}".encode()).digest()
    )


def _is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}


def _jwt_secret_material() -> str | None:
    raw = (os.getenv("JWT_SECRET") or "").strip()
    return raw or None


def _fernet_candidates() -> list[Fernet]:
    """Encryption keys to try — explicit env, JWT-derived, then dev-only fallback."""
    candidates: list[Fernet] = []
    seen: set[bytes] = set()

    def _add(key_bytes: bytes) -> None:
        if key_bytes in seen:
            return
        seen.add(key_bytes)
        candidates.append(Fernet(key_bytes))

    explicit = os.getenv("SETTINGS_ENCRYPTION_KEY", "").strip()
    if explicit:
        _add(explicit.encode() if isinstance(explicit, str) else explicit)

    jwt = _jwt_secret_material()
    if jwt:
        _add(_derive_fernet_key(jwt))

    if not _is_production():
        _add(_derive_fernet_key("azure-cost-optimizer-dev-key"))

    return candidates


def _primary_fernet() -> Fernet | None:
    items = _fernet_candidates()
    return items[0] if items else None


def encrypt_value(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    f = _primary_fernet()
    if not f:
        raise RuntimeError(
            "Set JWT_SECRET (or SETTINGS_ENCRYPTION_KEY) to store secrets in production"
        )
    token = f.encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{_PREFIX}{token}"


def try_decrypt_value(value: str | None) -> tuple[str | None, str | None]:
    """Return (plaintext, error). Plain values pass through without error."""
    if value is None or value == "":
        return value, None
    if not value.startswith(_PREFIX):
        return value, None

    candidates = _fernet_candidates()
    if not candidates:
        return None, "Secret encryption is not configured on this instance"

    payload = value[len(_PREFIX):].encode("utf-8")
    for f in candidates:
        try:
            return f.decrypt(payload).decode("utf-8"), None
        except InvalidToken:
            continue
    return None, "Stored secret could not be decrypted — re-save the value or use an environment variable"


def decrypt_value(value: str | None) -> str | None:
    plain, err = try_decrypt_value(value)
    if err:
        raise RuntimeError(err)
    return plain


def mask_secret(value: str | None, visible: int = 4) -> str | None:
    if not value:
        return None
    if len(value) <= visible:
        return "*" * len(value)
    return f"{'*' * (len(value) - visible)}{value[-visible:]}"


def encryption_status() -> dict:
    explicit = bool(os.getenv("SETTINGS_ENCRYPTION_KEY", "").strip())
    jwt = bool(_jwt_secret_material())
    if explicit:
        mode = "fernet"
        enabled = True
    elif jwt:
        mode = "jwt_derived"
        enabled = True
    elif _is_production():
        mode = "required"
        enabled = False
    else:
        mode = "dev_derived"
        enabled = True
    return {
        "enabled": enabled,
        "key_configured": enabled,
        "mode": mode,
        "message": (
            "Stored secrets are encrypted at rest."
            if enabled
            else "Set JWT_SECRET to encrypt stored credentials in production."
        ),
    }

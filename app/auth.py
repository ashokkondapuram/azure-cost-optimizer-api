"""Azure token management with PostgreSQL cache, in-process L1 cache, and auto-refresh."""
import contextvars
import os
import time
import threading
from contextlib import contextmanager
from typing import Optional

from azure.identity import (
    ClientSecretCredential,
    DefaultAzureCredential,
    ManagedIdentityCredential,
)
from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.azure_token_cache import (
    REFRESH_MARGIN_SECONDS,
    clear_token_cache,
    credential_cache_key,
    read_cached_token,
    write_cached_token,
)

_lock = threading.Lock()
_cache: dict = {}
_credential = None
ARM_SCOPE = "https://management.azure.com/.default"
OPENAI_SCOPE = "https://cognitiveservices.azure.com/.default"
DEFAULT_AUTH_MODE = "managed_identity"

_arm_auth_ctx: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "arm_auth_ctx", default=None,
)


@contextmanager
def scoped_session(db=None):
    """Yield a DB session, closing it only when we opened it.

    Exceptions from the caller's body propagate normally; the session is
    always closed if we own it, but we never swallow errors.
    """
    owned = db is None
    if owned:
        from app.database import SessionLocal
        db = SessionLocal()
    try:
        yield db
    except Exception:
        if owned:
            db.close()
        raise
    else:
        if owned:
            db.close()


def resolve_default_auth_mode() -> str:
    """Use managed identity on Azure App Service; credentials elsewhere unless overridden."""
    from app.platform import is_azure_app_service
    if is_azure_app_service():
        return "managed_identity"
    return os.getenv("AZURE_AUTH_MODE", DEFAULT_AUTH_MODE).strip() or DEFAULT_AUTH_MODE


def build_credential(config: dict):
    """Build an Azure credential from a settings config dict."""
    mode = (config.get("auth_mode") or DEFAULT_AUTH_MODE).strip()

    if mode == "managed_identity":
        client_id = (config.get("client_id") or "").strip()
        if client_id:
            return ManagedIdentityCredential(client_id=client_id)
        return ManagedIdentityCredential()

    if mode == "service_principal":
        tenant_id = config.get("tenant_id")
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        if tenant_id and client_id and client_secret:
            try:
                return ClientSecretCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                )
            except Exception as exc:
                raise ValueError(
                    f"Failed to build service principal credential: {exc}"
                ) from exc
        raise ValueError(
            "Service principal auth requires tenant ID, client ID, and client secret."
        )

    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


def _env_config() -> dict:
    return {
        "auth_mode": resolve_default_auth_mode(),
        "tenant_id": os.getenv("AZURE_TENANT_ID", ""),
        "client_id": os.getenv("AZURE_CLIENT_ID", ""),
        "client_secret": os.getenv("AZURE_CLIENT_SECRET", ""),
        "default_subscription_id": os.getenv("AZURE_DEFAULT_SUBSCRIPTION_ID", ""),
    }


def resolve_auth_config(db=None) -> dict:
    """Effective Azure auth settings — always prefer PostgreSQL settings when available."""
    with scoped_session(db) as session:
        config = _env_config()
        try:
            from app.services.system_settings import get_effective_config
            config = get_effective_config(session, "azure")
        except Exception:
            pass
        return config


@contextmanager
def arm_auth_context(*, db=None, token: str | None = None):
    """Pin DB session and/or bearer token for nested ARM HTTP calls (e.g. inventory sync)."""
    reset = _arm_auth_ctx.set({"db": db, "token": token})
    try:
        yield
    finally:
        _arm_auth_ctx.reset(reset)


def current_arm_auth() -> dict:
    return _arm_auth_ctx.get() or {}


def get_credential(db=None):
    """Return Azure credential from DB settings, falling back to environment.

    Thread-safe: the global _credential is built exactly once under _lock.
    """
    global _credential
    # Fast path — already built (volatile read is fine; worst case we enter the lock once extra)
    if _credential is not None:
        return _credential
    with _lock:
        # Double-checked locking: re-test inside the lock
        if _credential is not None:
            return _credential
        with scoped_session(db) as session:
            _credential = build_credential(resolve_auth_config(session))
    return _credential


def reload_credential(db=None) -> None:
    """Clear token cache and rebuild credential from latest settings.

    Both _cache and _credential are reset inside a single lock acquisition so
    no other thread can read a stale token between the two operations.
    """
    global _credential
    with scoped_session(db) as session:
        with _lock:
            _cache.clear()
            _credential = None
            clear_token_cache(session)
    # Rebuild outside the lock so token-fetch I/O does not block other threads
    get_credential(db)
    try:
        from app import azure_client
        azure_client.reset_client_cache()
    except Exception:
        pass
    try:
        from app import http_client
        http_client.clear_cache()
    except Exception:
        pass


def _cache_hit(cache_key: str, margin: int = REFRESH_MARGIN_SECONDS) -> str | None:
    # Read under lock to avoid seeing a partially-written dict entry
    with _lock:
        cached = _cache.get(cache_key)
    if cached and cached["expires_on"] - time.time() > margin:
        return cached["token"]
    return None


def _store_token(cache_key: str, token: str, expires_on: float, db, *, scope: str) -> None:
    with _lock:
        _cache[cache_key] = {"token": token, "expires_on": expires_on}
    with scoped_session(db) as session:
        write_cached_token(
            session,
            cache_key=cache_key,
            scope=scope,
            token=token,
            expires_on=expires_on,
        )


def _get_bearer_token(db=None, *, scope: str = ARM_SCOPE) -> str:
    """Return a valid bearer token — L1 memory, then PostgreSQL, then Azure AD."""
    with scoped_session(db) as session:
        config = resolve_auth_config(session)
        cache_key = credential_cache_key(config, scope)

        hit = _cache_hit(cache_key)
        if hit:
            return hit

        db_cached = read_cached_token(session, cache_key)
        if db_cached:
            token, expires_on = db_cached
            with _lock:
                _cache[cache_key] = {"token": token, "expires_on": expires_on}
            return token

        with _lock:
            # Re-check inside lock (another thread may have fetched while we waited)
            cached = _cache.get(cache_key)
            if cached and cached["expires_on"] - time.time() > REFRESH_MARGIN_SECONDS:
                return cached["token"]

            cred = get_credential(session)
            tok = cred.get_token(scope)
            _cache[cache_key] = {"token": tok.token, "expires_on": tok.expires_on}

        write_cached_token(
            session,
            cache_key=cache_key,
            scope=scope,
            token=tok.token,
            expires_on=tok.expires_on,
        )
        return tok.token


def get_token(db=None) -> str:
    """ARM management API bearer token."""
    return _get_bearer_token(db, scope=ARM_SCOPE)


def get_openai_token(db=None) -> str:
    """Azure OpenAI / Cognitive Services bearer token (same identity as ARM settings)."""
    return _get_bearer_token(db, scope=OPENAI_SCOPE)


def auth_headers(db: Optional[object] = None) -> dict:
    ctx = current_arm_auth()
    pinned = ctx.get("token")
    if pinned:
        return {
            "Authorization": f"Bearer {pinned}",
            "Content-Type": "application/json",
        }
    effective_db = db if db is not None else ctx.get("db")
    return {
        "Authorization": f"Bearer {get_token(effective_db)}",
        "Content-Type": "application/json",
    }


def arm_bearer_token(db: Session = Depends(get_db)) -> str:
    """FastAPI dependency — bearer token from PostgreSQL cache when available."""
    return get_token(db)

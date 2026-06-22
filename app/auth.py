"""Azure token management with automatic refresh and caching."""
import time
import threading
from azure.identity import DefaultAzureCredential, ClientSecretCredential
import os

_lock = threading.Lock()
_cache: dict = {}


def get_credential():
    """Return the best available credential. Prefers Service Principal env vars."""
    client_id     = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    tenant_id     = os.getenv("AZURE_TENANT_ID")
    if client_id and client_secret and tenant_id:
        return ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


_credential = get_credential()
ARM_SCOPE = "https://management.azure.com/.default"


def get_token() -> str:
    """Return a valid bearer token, refreshing if expiry within 60 s."""
    with _lock:
        cached = _cache.get(ARM_SCOPE)
        if cached and cached["expires_on"] - time.time() > 60:
            return cached["token"]
        tok = _credential.get_token(ARM_SCOPE)
        _cache[ARM_SCOPE] = {"token": tok.token, "expires_on": tok.expires_on}
        return tok.token


def auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json",
    }

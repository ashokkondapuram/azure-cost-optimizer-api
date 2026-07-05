"""Helpers for serving the React SPA alongside JSON API routes."""

from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import FileResponse

# Exact paths shared by the React router and a JSON GET handler (no query = page refresh).
_SPA_DOCUMENT_PATHS = frozenset({
    "/costs",
    "/settings",
})

# Protected app routes with no JSON handler on the exact path (refresh must load the SPA).
_SPA_EXACT_ROUTES = frozenset({
    "/",
    "/k8s",
    "/optimization-hub",
    "/engine",
    "/history",
    "/admin/optimization",
    "/admin/api-explorer",
})

_index_path: str | None = None


def configure_spa_index(index_path: str) -> None:
    global _index_path
    _index_path = index_path if os.path.isfile(index_path) else None


def normalized_path(path: str) -> str:
    return (path or "/").rstrip("/") or "/"


def is_api_client_request(request: Request) -> bool:
    """XHR/fetch/curl API calls — not a browser address-bar refresh."""
    if request.headers.get("authorization"):
        return True
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept and "text/html" not in accept:
        return True
    fetch_dest = request.headers.get("sec-fetch-dest", "")
    if fetch_dest in {"empty", "script", "style", "image", "font", "video", "audio"}:
        return True
    if request.headers.get("sec-fetch-mode") == "cors":
        return True
    if request.headers.get("x-requested-with"):
        return True
    return False


def wants_html_document(request: Request) -> bool:
    """True when Accept prefers HTML."""
    accept = request.headers.get("accept", "")
    first = accept.split(",", 1)[0].strip().lower()
    if first.startswith("text/html"):
        return True
    return first == "*/*" and normalized_path(request.url.path) in _SPA_DOCUMENT_PATHS


def is_spa_page_refresh(request: Request) -> bool:
    """True when a browser refresh should return index.html, not a JSON API error."""
    if request.method not in ("GET", "HEAD"):
        return False
    path = normalized_path(request.url.path)
    if path.startswith("/api") or path in ("/docs", "/redoc", "/openapi.json"):
        return False
    if is_api_client_request(request):
        return False
    # Dual-purpose API pages: only treat as SPA when there is no API query string.
    if path in _SPA_DOCUMENT_PATHS and not request.query_params.get("subscription_id"):
        return True
    if path in _SPA_EXACT_ROUTES:
        return True
    if request.headers.get("sec-fetch-dest") == "document":
        return True
    if request.headers.get("sec-fetch-mode") == "navigate":
        return True
    return wants_html_document(request)


def is_browser_document_navigation(request: Request) -> bool:
    """Alias used by auth middleware — same rules as SPA page refresh."""
    return is_spa_page_refresh(request)


def should_serve_spa(request: Request, *, api_query_present: bool) -> bool:
    """Decide whether a dual-purpose path should return index.html."""
    if is_api_client_request(request):
        return False
    if api_query_present:
        return False
    path = normalized_path(request.url.path)
    if path in _SPA_DOCUMENT_PATHS:
        return True
    return is_spa_page_refresh(request)


def spa_index_response() -> FileResponse | None:
    if _index_path:
        return FileResponse(_index_path)
    return None


def safe_join(base_dir: str, rel_path: str) -> str | None:
    """Resolve a relative path under base_dir; return None if it escapes base_dir."""
    base = os.path.abspath(base_dir)
    candidate = os.path.abspath(os.path.join(base, rel_path))
    if candidate == base or candidate.startswith(base + os.sep):
        return candidate
    return None

"""JWT authentication middleware for API routes."""
from __future__ import annotations

from typing import Callable

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.settings import get_settings
from app.spa_utils import is_browser_document_navigation
from app.user_auth import ROLE_ADMIN, ROLE_SUPERUSER, decode_access_token, parse_bearer_token, user_from_request, is_privileged_role

log = structlog.get_logger()

PUBLIC_API_PREFIXES = (
    "/health",
    "/auth/login",
)

PUBLIC_API_EXACT = {
    "/health",
    "/health/live",
    "/health/ready",
    "/auth/login",
    "/costs/timeframes",
}

ADMIN_ONLY_API_EXACT = {
    "/docs",
    "/openapi.json",
    "/redoc",
}

ADMIN_ONLY_API_PREFIXES = (
    "/docs/",
)


def _normalize_api_path(path: str) -> str:
    if path.startswith("/api/"):
        return path[4:] or "/"
    if path == "/api":
        return "/"
    return path


def _is_public_api_path(path: str) -> bool:
    if path in PUBLIC_API_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_API_PREFIXES if prefix.endswith("/"))


def _is_admin_only_api_path(path: str) -> bool:
    if path in ADMIN_ONLY_API_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in ADMIN_ONLY_API_PREFIXES)


def _should_protect(path: str) -> bool:
    if path.startswith("/api") or path.startswith("/auth"):
        return True
    if path in ADMIN_ONLY_API_EXACT or path.startswith("/docs"):
        return True
    protected_roots = (
        "/settings",
        "/costs",
        "/resources",
        "/metrics",
        "/optimize",
        "/events",
        "/k8s",
        "/admin",
        "/azure",
        "/dashboard",
        "/sync",
        "/advisor",
        "/alerts",
        "/outliers",
        "/budgets",
        "/idle-resources",
        "/tag-compliance",
        "/anomalies",
        "/savings",
        "/engine",
        "/reservations",
        "/security-posture",
        "/quota",
        "/carbon",
    )
    return any(path.startswith(root) for root in protected_roots)


class AppAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        settings = get_settings()
        path = request.url.path

        if request.method == "OPTIONS":
            return await call_next(request)

        # Let browser refreshes reach SPA handlers / catch-all — never return JSON 401 for page loads.
        if is_browser_document_navigation(request):
            return await call_next(request)

        if not _should_protect(path):
            return await call_next(request)

        api_path = _normalize_api_path(path)
        if _is_public_api_path(api_path):
            return await call_next(request)

        token = parse_bearer_token(request.headers.get("Authorization"))
        if token:
            payload = decode_access_token(token)
            if not payload:
                log.warning("invalid_token_provided", path=path)
            if payload:
                from app.database import SessionLocal
                from app.models import AppUser

                db = SessionLocal()
                try:
                    row = db.query(AppUser).filter(AppUser.id == payload.get("sub")).first()
                    if row and row.is_active:
                        request.state.user = {
                            "id": row.id,
                            "username": row.username,
                            "role": row.role,
                            "display_name": row.display_name or row.username,
                        }
                finally:
                    db.close()

        # K8s routes accept X-API-Key or optional JWT — parse token above, enforce in handler.
        if api_path.startswith("/k8s"):
            return await call_next(request)

        if not settings.auth_enabled:
            return await call_next(request)

        if not user_from_request(request):
            if not token:
                return JSONResponse(status_code=401, content={"detail": "Sign in required"})
            return JSONResponse(status_code=401, content={"detail": "Session expired. Sign in again."})

        user = user_from_request(request)
        if _is_admin_only_api_path(api_path) and not is_privileged_role(user.get("role")):
            return JSONResponse(status_code=403, content={"detail": "Admin access required"})

        response = await call_next(request)
        if response is None:
            return JSONResponse(
                status_code=500,
                content={"error": {"code": "internal_error", "message": "No response produced."}},
            )
        return response

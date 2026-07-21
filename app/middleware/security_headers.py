"""HTTP security response headers middleware.

Adds the following headers to every response:
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - Referrer-Policy: strict-origin-when-cross-origin
  - Permissions-Policy: geolocation=(), microphone=(), camera=()
  - Strict-Transport-Security (production only)
  - Content-Security-Policy
  - X-Request-ID  (echoes or generates a request correlation ID)

Kept intentionally simple — no external dependencies.
"""
from __future__ import annotations

import secrets
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Tight CSP for the API layer.  The SPA's own static files are served by the
# same FastAPI process, so we include 'self' for script/style.  Adjust
# connect-src if you add third-party analytics or font CDNs.
_CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# HSTS: 1 year, include subdomains. Only sent over HTTPS (production flag).
_HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security headers to every outgoing response."""

    def __init__(self, app, *, is_production: bool = False) -> None:
        super().__init__(app)
        self._is_production = is_production

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate / propagate a request correlation ID so log lines can be
        # correlated with the response the client received.
        request_id = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Correlation-ID")
            or secrets.token_hex(8)
        )
        # Stash on request state so other middleware / handlers can read it.
        request.state.request_id = request_id

        response: Response = await call_next(request)
        if response is None:
            return JSONResponse(
                status_code=500,
                content={"error": {"code": "internal_error", "message": "No response produced."}},
            )

        # ── Core security headers (all environments) ──────────────────────
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["X-Request-ID"] = request_id

        # Content-Security-Policy — skip for binary/static assets served by
        # StaticFiles (they carry their own content-type and don't need CSP).
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type or "application/json" in content_type:
            response.headers["Content-Security-Policy"] = _CSP

        # ── Production-only headers ───────────────────────────────────────
        if self._is_production:
            response.headers["Strict-Transport-Security"] = _HSTS

        return response

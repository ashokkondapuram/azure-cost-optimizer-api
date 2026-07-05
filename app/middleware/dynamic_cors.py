"""CORS middleware that reads allowed origins from runtime settings (no restart)."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.runtime_config import get_cors_origins


def _cors_headers(origin: str) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PATCH, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Vary": "Origin",
    }


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        allowed = get_cors_origins()

        if request.method == "OPTIONS" and origin and origin in allowed:
            return Response(status_code=204, headers=_cors_headers(origin))

        response = await call_next(request)

        if origin and origin in allowed:
            for key, value in _cors_headers(origin).items():
                response.headers[key] = value

        return response

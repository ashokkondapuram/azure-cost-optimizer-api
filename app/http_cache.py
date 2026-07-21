"""Cache-Control and ETag helpers for read-heavy API routes."""

from __future__ import annotations

import hashlib

from fastapi import Request, Response
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse, Response as StarletteResponse

RESOURCE_LIST_CACHE = "public, max-age=300, stale-while-revalidate=600"
COST_CACHE = "public, max-age=900, stale-while-revalidate=1800"
FINDINGS_CACHE = "public, max-age=120, stale-while-revalidate=300"
DASHBOARD_CACHE = "public, max-age=180, stale-while-revalidate=360"
NO_STORE = "no-store"

_ETAG_PATH_PREFIXES = (
    "/resources/",
    "/dashboard",
    "/optimize/findings",
)


def apply_cache_control(response: Response, policy: str) -> Response:
    response.headers["Cache-Control"] = policy
    return response


def cache_policy_for_path(path: str, *, method: str = "GET") -> str | None:
    if method != "GET":
        return None
    if "/optimize/jobs" in path or path.endswith("/sync"):
        return NO_STORE
    if path.startswith("/optimize/findings"):
        return FINDINGS_CACHE
    if path.startswith("/dashboard") or path == "/resources/counts":
        return DASHBOARD_CACHE
    if (
        path.startswith("/cost")
        or "/cost" in path
        or path.startswith("/resources/from-cost")
        or path.startswith("/resources/billed")
    ):
        return COST_CACHE
    if path.startswith("/resources/"):
        return RESOURCE_LIST_CACHE
    return None


def _etag_for_body(body: bytes) -> str:
    return f'"{hashlib.sha256(body).hexdigest()[:16]}"'


def _is_cost_path(path: str) -> bool:
    return path.startswith("/cost") or "/cost" in path


def _should_apply_etag(path: str, method: str) -> bool:
    if method != "GET":
        return False
    # Cost payloads are large and change often — skip full-body ETag buffering.
    if _is_cost_path(path):
        return False
    return any(path.startswith(prefix) or prefix in path for prefix in _ETAG_PATH_PREFIXES)


class CacheControlMiddleware:
    """Pure ASGI middleware for cache headers and selective ETag support."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path
        method = request.method
        policy = cache_policy_for_path(path, method=method)
        apply_etag = _should_apply_etag(path, method)

        if not policy and not apply_etag:
            await self.app(scope, receive, send)
            return

        if not apply_etag:
            async def send_with_cache(message):
                if message["type"] == "http.response.start" and policy:
                    headers = MutableHeaders(raw=message["headers"])
                    headers["Cache-Control"] = policy
                    message = {**message, "headers": headers.raw}
                await send(message)

            await self.app(scope, receive, send_with_cache)
            return

        await self._send_with_etag(scope, receive, send, request, policy)

    async def _send_with_etag(self, scope, receive, send, request: Request, policy: str | None):
        body = b""
        status_code = 200
        headers: list[tuple[bytes, bytes]] = []
        response_started = False

        async def send_intercept(message):
            nonlocal body, status_code, headers, response_started

            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = list(message.get("headers", []))
                return

            if message["type"] != "http.response.body":
                await send(message)
                return

            body += message.get("body", b"")
            if message.get("more_body", False):
                return

            if not response_started:
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [(b"content-type", b"application/json")],
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"error":{"code":"internal_error","message":"No response produced."}}',
                    "more_body": False,
                })
                return

            etag = _etag_for_body(body)
            out_headers = MutableHeaders(raw=headers)
            if policy:
                out_headers["Cache-Control"] = policy

            if request.headers.get("if-none-match") == etag:
                await send({
                    "type": "http.response.start",
                    "status": 304,
                    "headers": [
                        (b"etag", etag.encode()),
                        (b"cache-control", out_headers.get("cache-control", "").encode()),
                    ],
                })
                await send({"type": "http.response.body", "body": b"", "more_body": False})
                return

            out_headers["ETag"] = etag
            await send({
                "type": "http.response.start",
                "status": status_code,
                "headers": out_headers.raw,
            })
            await send({"type": "http.response.body", "body": body, "more_body": False})

        await self.app(scope, receive, send_intercept)


async def cache_control_middleware(request: Request, call_next):
    """Legacy helper for tests that still use @app.middleware('http')."""
    response = await call_next(request)
    if response is None:
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "No response produced."}},
        )
    policy = cache_policy_for_path(request.url.path, method=request.method)
    if policy:
        response.headers["Cache-Control"] = policy
    if not _should_apply_etag(request.url.path, request.method) or response.status_code != 200:
        return response

    body = b""
    async for chunk in response.body_iterator:
        body += chunk

    etag = _etag_for_body(body)
    if request.headers.get("if-none-match") == etag:
        return StarletteResponse(
            status_code=304,
            headers={
                "ETag": etag,
                "Cache-Control": response.headers.get("cache-control", ""),
            },
        )

    headers = dict(response.headers)
    headers["ETag"] = etag
    return StarletteResponse(
        content=body,
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type,
    )

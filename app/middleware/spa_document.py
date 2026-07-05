"""Serve index.html for SPA page refreshes before auth middleware runs."""

from __future__ import annotations

from starlette.requests import Request

from app.spa_utils import is_spa_page_refresh, spa_index_response


class SpaDocumentMiddleware:
    """Pure ASGI middleware — avoids BaseHTTPMiddleware response races."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        if is_spa_page_refresh(request):
            spa = spa_index_response()
            if spa is not None:
                await spa(scope, receive, send)
                return

        await self.app(scope, receive, send)

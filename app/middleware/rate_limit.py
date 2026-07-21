"""Request rate-limiting middleware using a simple sliding-window in-process counter.

For production deployments with multiple workers, replace _store with a
Redis backend.  For single-worker App Service or container deployments,
the in-process store is sufficient.

Configure via environment variables:
    RATE_LIMIT_ENABLED         0|1  (default 1)
    RATE_LIMIT_REQUESTS        max requests per window (default 60)
    RATE_LIMIT_WINDOW_SECONDS  window size in seconds (default 60)
    RATE_LIMIT_EXPENSIVE_PATHS comma-sep path prefixes with tighter limits
    RATE_LIMIT_EXPENSIVE_MAX   max requests for expensive paths (default 10)
"""
from __future__ import annotations

import os
import time
import threading
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


_store: dict[str, deque] = defaultdict(deque)
_store_lock = threading.Lock()


def _client_key(request: Request) -> str:
    """Identify caller by forwarded IP or direct host."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_allowed(key: str, limit: int, window: int) -> bool:
    """Sliding-window rate check. Returns True when the request is within limit."""
    now = time.monotonic()
    with _store_lock:
        timestamps = _store[key]
        # Drop timestamps outside the current window
        while timestamps and timestamps[0] < now - window:
            timestamps.popleft()
        if len(timestamps) >= limit:
            return False
        timestamps.append(now)
    return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter.  Attach to the FastAPI app in main.py::

        from app.middleware.rate_limit import RateLimitMiddleware
        app.add_middleware(RateLimitMiddleware)
    """

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.enabled = _env_bool("RATE_LIMIT_ENABLED", True)
        self.default_limit = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
        self.window = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
        self.expensive_limit = int(os.getenv("RATE_LIMIT_EXPENSIVE_MAX", "10"))
        raw_paths = os.getenv("RATE_LIMIT_EXPENSIVE_PATHS", "/analysis/run,/sync/start")
        self.expensive_paths = [p.strip() for p in raw_paths.split(",") if p.strip()]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)

        path = request.url.path
        key = _client_key(request)

        is_expensive = any(path.startswith(p) for p in self.expensive_paths)
        limit = self.expensive_limit if is_expensive else self.default_limit
        bucket_key = f"{key}:{'exp' if is_expensive else 'std'}"

        if not _is_allowed(bucket_key, limit, self.window):
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down.",
                    "retry_after_seconds": self.window,
                },
                headers={"Retry-After": str(self.window)},
            )
        return await call_next(request)

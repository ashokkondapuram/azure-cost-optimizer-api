"""Mirror API routes under /api so SPA calls work in production without path rewriting."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute
import structlog

log = structlog.get_logger()

_SKIP_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _iter_api_routes(routes) -> list[APIRoute]:
    """Yield APIRoute instances from app.routes and nested include_router mounts."""
    found: list[APIRoute] = []
    for route in routes:
        if isinstance(route, APIRoute):
            found.append(route)
            continue
        original = getattr(route, "original_router", None)
        if original is not None and hasattr(original, "routes"):
            found.extend(_iter_api_routes(original.routes))
    return found


def _route_method_keys(routes) -> set[tuple[str, str]]:
    """Set of (path, HTTP method) pairs already registered."""
    keys: set[tuple[str, str]] = set()
    for route in _iter_api_routes(routes):
        for method in route.methods:
            keys.add((route.path, method.upper()))
    return keys


def mirror_routes_under_api_prefix(application: FastAPI) -> int:
    """Register /api/* aliases for every route (React client uses baseURL /api).

    Returns the number of mirrored routes added.
    """
    existing = _route_method_keys(application.routes)
    added = 0

    for route in _iter_api_routes(application.routes):
        if route.path.startswith("/api") or route.path in _SKIP_PATHS:
            continue
        mirrored = f"/api{route.path}"
        methods = sorted(
            m.upper() for m in route.methods
            if (mirrored, m.upper()) not in existing
        )
        if not methods:
            continue
        application.add_api_route(
            mirrored,
            route.endpoint,
            methods=methods,
            response_model=route.response_model,
            status_code=route.status_code,
            tags=route.tags,
            dependencies=route.dependencies,
            summary=route.summary,
            include_in_schema=False,
            name=f"{route.name}_api_mirror" if route.name else None,
        )
        for method in methods:
            existing.add((mirrored, method))
        added += 1

    log.info("api_routes_mirrored", count=added)
    return added

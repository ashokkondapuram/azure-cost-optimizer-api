"""Serve the React build with reliable deep-link fallback (/vms, /acr, etc.)."""

from __future__ import annotations

import os

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.spa_utils import configure_spa_index, safe_join

log = structlog.get_logger()

# First path segment reserved for backend JSON APIs (not React routes).
# Note: /k8s is a React route; only /k8s/* API paths are blocked below.
_API_ROOT_SEGMENTS = frozenset({
    "api",
    "health",
    "settings",
    "resources",
    "metrics",
    "optimize",
    "docs",
    "openapi.json",
    "redoc",
})


def mount_spa(app: FastAPI, frontend_dir: str) -> None:
    """Mount /static assets and register a catch-all that serves index.html for SPA routes."""
    index_path = os.path.join(frontend_dir, "index.html")
    if not os.path.isfile(index_path):
        log.warning("frontend_build_missing", path=frontend_dir)
        return

    configure_spa_index(index_path)

    static_dir = os.path.join(frontend_dir, "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="frontend_static")

    @app.get("/{spa_path:path}", include_in_schema=False)
    async def serve_spa(spa_path: str = ""):
        first = spa_path.split("/", 1)[0] if spa_path else ""
        # Kubernetes utilization API lives under /k8s/*; /k8s alone is the React page.
        if spa_path.startswith("k8s/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if first in _API_ROOT_SEGMENTS:
            raise HTTPException(status_code=404, detail="Not Found")
        if spa_path:
            candidate = safe_join(frontend_dir, spa_path)
            if candidate and os.path.isfile(candidate):
                return FileResponse(candidate)
        return FileResponse(index_path)

    log.info("spa_mounted", frontend_dir=frontend_dir)

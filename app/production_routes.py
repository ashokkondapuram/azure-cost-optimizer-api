"""Wire production routing: /api mirrors + SPA static serving."""

from __future__ import annotations

import os

from fastapi import FastAPI

from app.route_mirror import mirror_routes_under_api_prefix
from app.spa_static import mount_spa


def configure_production_routes(app: FastAPI, frontend_dir: str) -> None:
    """Register /api/* aliases and the React SPA (must run after all API routes)."""
    mirror_routes_under_api_prefix(app)
    mount_spa(app, os.path.normpath(frontend_dir))

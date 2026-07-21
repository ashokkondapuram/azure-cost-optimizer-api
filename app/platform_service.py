"""Shared FastAPI factory for platform microservices (cost, analysis, inventory)."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.http_cache import CacheControlMiddleware
from app.http_client import AzureAPIError
from app.middleware.app_auth import AppAuthMiddleware
from app.middleware.dynamic_cors import DynamicCORSMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.settings import get_settings

log = structlog.get_logger()


def _default_lifecycle(
    *,
    on_startup: Callable[[], None] | None = None,
    on_shutdown: Callable[[], None] | None = None,
):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from app.database import engine, migrate_schema
        from app.logging_config import configure_logging
        from app.models import Base

        settings = get_settings()
        configure_logging(level=settings.log_level, json_logs=settings.is_production)
        Base.metadata.create_all(bind=engine)
        migrate_schema()

        if on_startup:
            on_startup()

        yield

        if on_shutdown:
            on_shutdown()

    return lifespan


def create_platform_service_app(
    *,
    title: str,
    service_id: str,
    profile: str | None = None,
    routers: tuple[Any, ...] | None = None,
    on_startup: Callable[[], None] | None = None,
    on_shutdown: Callable[[], None] | None = None,
) -> FastAPI:
    """Build a platform FastAPI app with shared middleware and optional router profile."""
    settings = get_settings()

    app = FastAPI(
        title=title,
        version="1.0.0",
        lifespan=_default_lifecycle(on_startup=on_startup, on_shutdown=on_shutdown),
    )

    app.add_middleware(SecurityHeadersMiddleware, is_production=settings.is_production)
    app.add_middleware(DynamicCORSMiddleware)
    app.add_middleware(AppAuthMiddleware)
    app.add_middleware(CacheControlMiddleware)

    if profile:
        from app.service_profiles import register_profile_routers

        count = register_profile_routers(app, profile)
        log.info("platform_service_routers_registered", service=service_id, profile=profile, count=count)
    elif routers:
        for router in routers:
            app.include_router(router)

    @app.exception_handler(AzureAPIError)
    async def azure_error_handler(request: Request, exc: AzureAPIError):
        status = 503 if exc.status in {502, 503, 504} else exc.status
        return JSONResponse(
            status_code=status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        log.exception(
            "unhandled_error",
            method=request.method,
            path=request.url.path,
            service=service_id,
        )
        message = "An unexpected error occurred."
        if not settings.is_production:
            detail = str(exc).strip()
            if detail:
                message = detail
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": message}},
        )

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok", "service": service_id}

    return app


def env_flag(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes"}

"""Combined FastAPI app for integration tests (all routers, no background workers).

Microservices run split profiles in production; this module exists only for
pytest and local API smoke tests that need every route on one process.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.__version__ import __version__
from app.azure_resources import AzureResourcesClient
from app.database import engine
from app.http_cache import CacheControlMiddleware
from app.http_client import AzureAPIError
from app.logging_config import configure_logging
from app.middleware.app_auth import AppAuthMiddleware
from app.middleware.dynamic_cors import DynamicCORSMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.models import Base
from app.router_registry import register_api_routers
from app.settings import get_settings
from app.user_auth import require_admin_user
from app.azure_live_api import register_azure_live_routes
from app.openapi_config import configure_openapi

settings = get_settings()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(level=settings.log_level, json_logs=settings.is_production)
    yield


app = FastAPI(
    title="CostOptimizer Integration Test API",
    version=__version__,
    lifespan=lifespan,
)
configure_openapi(app)

app.add_middleware(SecurityHeadersMiddleware, is_production=settings.is_production)
app.add_middleware(DynamicCORSMiddleware)
app.add_middleware(AppAuthMiddleware)
app.add_middleware(CacheControlMiddleware)

register_api_routers(app)

resource_client = AzureResourcesClient()
register_azure_live_routes(app, resource_client, require_admin_user=require_admin_user)

from app.route_mirror import mirror_routes_under_api_prefix

mirror_routes_under_api_prefix(app)


@app.exception_handler(AzureAPIError)
async def azure_error_handler(request: Request, exc: AzureAPIError):
    status = 503 if exc.status in {502, 503, 504} else exc.status
    return JSONResponse(
        status_code=status,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    log.exception("unhandled_error", method=request.method, path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "An unexpected error occurred."}},
    )


@app.get("/health/live", tags=["System"])
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["System"])
def health_ready():
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "version": __version__, "database": "ok"}
    finally:
        db.close()

"""Platform API gateway — routes all traffic to platform microservices (no monolith)."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

try:
    import httpcore
except ImportError:  # pragma: no cover
    httpcore = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "costoptimizer-core"))

from costoptimizer_core.registry import all_service_configs, get_service_by_api_slug, get_service_by_canonical

CORE_SERVICE_URL = os.getenv("CORE_SERVICE_URL", os.getenv("AUTH_SERVICE_URL", "http://127.0.0.1:8010")).rstrip("/")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://127.0.0.1:8012").rstrip("/")
METRICS_SERVICE_URL = os.getenv("METRICS_SERVICE_URL", "http://127.0.0.1:8014").rstrip("/")
COST_SERVICE_URL = os.getenv("COST_SERVICE_URL", "http://127.0.0.1:8011").rstrip("/")
GATEWAY_PORT = int(os.getenv("PORT", "8080"))
ANALYSIS_SERVICE_URL = os.getenv("ANALYSIS_SERVICE_URL", "http://127.0.0.1:8013").rstrip("/")
MICROSERVICES_ONLY = os.getenv("MICROSERVICES_ONLY", "1").lower() in {"1", "true", "yes"}


def _env_timeout_seconds(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(1.0, float(raw))
    except ValueError:
        log.warning("gateway_invalid_timeout_env", extra={"env": name, "value": raw})
        return default


GATEWAY_UPSTREAM_TIMEOUT_SECONDS = _env_timeout_seconds("GATEWAY_UPSTREAM_TIMEOUT_SECONDS", 120.0)
GATEWAY_OPTIMIZE_TIMEOUT_SECONDS = _env_timeout_seconds("GATEWAY_OPTIMIZE_TIMEOUT_SECONDS", 300.0)
GATEWAY_SYNC_ACCEPT_TIMEOUT_SECONDS = _env_timeout_seconds("GATEWAY_SYNC_ACCEPT_TIMEOUT_SECONDS", 60.0)
GATEWAY_ANALYZE_ACCEPT_TIMEOUT_SECONDS = _env_timeout_seconds("GATEWAY_ANALYZE_ACCEPT_TIMEOUT_SECONDS", 60.0)

app = FastAPI(title="CostOptimizer Platform Gateway", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_route_target(raw: str | None) -> str:
    """Expand ${INVENTORY_SERVICE_URL} placeholders from generated route YAML."""
    if not raw:
        return INVENTORY_SERVICE_URL
    text = str(raw).strip()
    env_map = {
        "INVENTORY_SERVICE_URL": INVENTORY_SERVICE_URL,
        "MONOLITH_URL": INVENTORY_SERVICE_URL,
        "CORE_SERVICE_URL": CORE_SERVICE_URL,
        "COST_SERVICE_URL": COST_SERVICE_URL,
        "ANALYSIS_SERVICE_URL": ANALYSIS_SERVICE_URL,
        "METRICS_SERVICE_URL": METRICS_SERVICE_URL,
    }
    if text.startswith("${") and text.endswith("}"):
        key = text[2:-1]
        return env_map.get(key, INVENTORY_SERVICE_URL)
    return text


def _load_routes() -> list[dict[str, Any]]:
    generated = Path(__file__).resolve().parent / "routes.generated.yaml"
    manual = Path(__file__).resolve().parent / "routes.yaml"
    path = generated if generated.is_file() else manual
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("routes") or [])


def _resource_route_table() -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for row in _load_routes():
        prefix = (row.get("path_prefix") or "").rstrip("/")
        if prefix:
            table[prefix] = {
                **row,
                "target": _resolve_route_target(row.get("target")),
            }
    for cfg in all_service_configs():
        prefix = f"/api/resources/{cfg.api_slug}"
        table.setdefault(prefix, {
            "path_prefix": prefix,
            "target": cfg.base_url if cfg.migrated else INVENTORY_SERVICE_URL,
            "migrated": cfg.migrated,
            "service_id": cfg.service_id,
        })
    return table


# Longest-prefix wins. Every entry maps to exactly one microservice upstream base.
PLATFORM_ROUTES: dict[str, str] = {
  # Core — auth, settings, admin, k8s
    "/api/auth": CORE_SERVICE_URL,
    "/auth": CORE_SERVICE_URL,
    "/api/settings": CORE_SERVICE_URL,
    "/settings": CORE_SERVICE_URL,
    "/api/admin": CORE_SERVICE_URL,
    "/admin": CORE_SERVICE_URL,
    "/api/k8s": CORE_SERVICE_URL,
    "/k8s": CORE_SERVICE_URL,
    "/api/maintenance": CORE_SERVICE_URL,
    "/maintenance": CORE_SERVICE_URL,
    "/api/global-health": CORE_SERVICE_URL,
    "/global-health": CORE_SERVICE_URL,
    "/api/quota": CORE_SERVICE_URL,
    "/quota": CORE_SERVICE_URL,
    "/api/security-posture": CORE_SERVICE_URL,
    "/security-posture": CORE_SERVICE_URL,
    # Inventory — resources, sync, dashboard slices, Azure ARM proxy
    "/api/resources/detail": INVENTORY_SERVICE_URL,
    "/resources/detail": INVENTORY_SERVICE_URL,
    "/api/dashboard": INVENTORY_SERVICE_URL,
    "/dashboard": INVENTORY_SERVICE_URL,
    "/api/sync/status": INVENTORY_SERVICE_URL,
    "/sync/status": INVENTORY_SERVICE_URL,
    "/api/sync/pipeline": INVENTORY_SERVICE_URL,
    "/sync/pipeline": INVENTORY_SERVICE_URL,
    "/api/sync/progress": INVENTORY_SERVICE_URL,
    "/sync/progress": INVENTORY_SERVICE_URL,
    "/api/sync/full": INVENTORY_SERVICE_URL,
    "/sync/full": INVENTORY_SERVICE_URL,
    "/api/advisor": INVENTORY_SERVICE_URL,
    "/advisor": INVENTORY_SERVICE_URL,
    "/api/alerts": INVENTORY_SERVICE_URL,
    "/alerts": INVENTORY_SERVICE_URL,
    "/api/outliers": INVENTORY_SERVICE_URL,
    "/outliers": INVENTORY_SERVICE_URL,
    "/api/resource-types": INVENTORY_SERVICE_URL,
    "/resource-types": INVENTORY_SERVICE_URL,
    "/api/azure": INVENTORY_SERVICE_URL,
    "/azure": INVENTORY_SERVICE_URL,
    "/api/scheduler": INVENTORY_SERVICE_URL,
    "/scheduler": INVENTORY_SERVICE_URL,
    # Cost
    "/api/cost": COST_SERVICE_URL,
    "/cost": COST_SERVICE_URL,
    "/api/costs": COST_SERVICE_URL,
    "/costs": COST_SERVICE_URL,
    "/api/budgets": COST_SERVICE_URL,
    "/budgets": COST_SERVICE_URL,
    "/api/anomalies": COST_SERVICE_URL,
    "/anomalies": COST_SERVICE_URL,
    "/api/reservations": COST_SERVICE_URL,
    "/reservations": COST_SERVICE_URL,
    "/api/savings-planner": COST_SERVICE_URL,
    "/savings-planner": COST_SERVICE_URL,
    "/api/carbon": COST_SERVICE_URL,
    "/carbon": COST_SERVICE_URL,
    # Analysis — optimization engine, findings, actions
    "/api/optimize": ANALYSIS_SERVICE_URL,
    "/optimize": ANALYSIS_SERVICE_URL,
    "/api/events": ANALYSIS_SERVICE_URL,
    "/events": ANALYSIS_SERVICE_URL,
    "/api/activity": ANALYSIS_SERVICE_URL,
    "/activity": ANALYSIS_SERVICE_URL,
    "/api/engine": ANALYSIS_SERVICE_URL,
    "/engine": ANALYSIS_SERVICE_URL,
    "/api/idle-resources": ANALYSIS_SERVICE_URL,
    "/idle-resources": ANALYSIS_SERVICE_URL,
    "/api/pipeline": ANALYSIS_SERVICE_URL,
    "/pipeline": ANALYSIS_SERVICE_URL,
    # Metrics
    "/api/metrics": METRICS_SERVICE_URL,
    "/metrics": METRICS_SERVICE_URL,
    "/api/azure/metrics": METRICS_SERVICE_URL,
    "/azure/metrics": METRICS_SERVICE_URL,
}


def _hop_headers(request: Request) -> dict[str, str]:
    """Forward auth and content negotiation headers required for JSON POST bodies."""
    out: dict[str, str] = {}
    for key in (
        "authorization",
        "content-type",
        "accept",
        "x-correlation-id",
        "x-request-id",
    ):
        if key in request.headers:
            out[key] = request.headers[key]
    return out


def _is_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException)):
        return True
    if httpcore is not None and isinstance(exc, httpcore.ReadTimeout):
        return True
    return False


def _is_sync_accept_path(method: str, upstream_path: str) -> bool:
    if method.upper() != "POST":
        return False
    normalized = upstream_path.rstrip("/").lower()
    return normalized in {
        "/resources/sync",
        "/sync/full",
        "/sync/enrich",
        "/costs/sync",
    } or normalized.endswith("/sync")


def _is_analyze_accept_path(method: str, upstream_path: str) -> bool:
    if method.upper() != "POST":
        return False
    normalized = upstream_path.rstrip("/").lower()
    return normalized in {
        "/optimize/analyze",
        "/optimize/analyze/batch",
        "/optimize/resources/analyze",
    }


def _is_accept_path(method: str, upstream_path: str) -> bool:
    return _is_sync_accept_path(method, upstream_path) or _is_analyze_accept_path(method, upstream_path)


def _client_timeout(method: str, upstream_path: str) -> httpx.Timeout | float:
    """Per-route upstream timeouts; sync/analyze POST accepts return 202 quickly."""
    normalized = upstream_path.lower()
    if normalized.startswith("/events") or normalized.startswith("/sync/progress/stream"):
        return httpx.Timeout(connect=30.0, read=None, write=30.0, pool=30.0)
    if _is_sync_accept_path(method, upstream_path):
        return GATEWAY_SYNC_ACCEPT_TIMEOUT_SECONDS
    if _is_analyze_accept_path(method, upstream_path):
        return GATEWAY_ANALYZE_ACCEPT_TIMEOUT_SECONDS
    if normalized.startswith("/optimize") or normalized.startswith("/engine/analysis"):
        return GATEWAY_OPTIMIZE_TIMEOUT_SECONDS
    return GATEWAY_UPSTREAM_TIMEOUT_SECONDS


async def _proxy(request: Request, upstream_base: str, upstream_path: str) -> Response:
    url = f"{upstream_base.rstrip('/')}{upstream_path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    request_id = request.headers.get("x-request-id") or request.headers.get("x-correlation-id")
    accept_route = _is_accept_path(request.method, upstream_path)
    started = time.monotonic()
    log.debug(
        "gateway_proxy",
        extra={
            "method": request.method,
            "incoming_path": request.url.path,
            "upstream_base": upstream_base,
            "upstream_path": upstream_path,
            "request_id": request_id,
        },
    )
    body = await request.body()
    timeout = _client_timeout(request.method, upstream_path)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            upstream = await client.request(
                request.method,
                url,
                headers=_hop_headers(request),
                content=body if body else None,
            )
    except Exception as exc:
        if _is_timeout_error(exc):
            log.warning(
                "gateway_upstream_timeout",
                extra={
                    "upstream_path": upstream_path,
                    "upstream_base": upstream_base,
                    "error_type": type(exc).__name__,
                },
            )
            return JSONResponse(
                status_code=504,
                content={
                    "detail": "Upstream service timed out",
                    "upstream": upstream_path,
                },
            )
        if isinstance(exc, httpx.RemoteProtocolError):
            log.warning(
                "gateway_upstream_protocol_error",
                extra={
                    "upstream_path": upstream_path,
                    "upstream_base": upstream_base,
                    "error_type": type(exc).__name__,
                },
            )
            return JSONResponse(
                status_code=502,
                content={
                    "detail": "Upstream service unavailable",
                    "upstream": upstream_path,
                    "error_type": type(exc).__name__,
                },
            )
        if isinstance(exc, httpx.ConnectError):
            log.warning(
                "gateway_upstream_connect_error",
                extra={
                    "upstream_path": upstream_path,
                    "upstream_base": upstream_base,
                    "error_type": type(exc).__name__,
                },
            )
            return JSONResponse(
                status_code=502,
                content={
                    "detail": "Upstream service unavailable",
                    "upstream": upstream_path,
                    "error_type": type(exc).__name__,
                },
            )
        raise

    if accept_route:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log.info(
            "gateway_accept_proxy",
            extra={
                "method": request.method,
                "incoming_path": request.url.path,
                "upstream_base": upstream_base,
                "upstream_path": upstream_path,
                "status_code": upstream.status_code,
                "elapsed_ms": elapsed_ms,
                "request_id": request_id,
            },
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={
            k: v
            for k, v in upstream.headers.items()
            if k.lower() not in {"content-encoding", "transfer-encoding", "connection"}
        },
        media_type=upstream.headers.get("content-type"),
    )


def _unrouted_response(path: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "detail": "No microservice route registered for this path",
            "path": path,
            "microservices_only": MICROSERVICES_ONLY,
            "hint": "Check GET /v1/routes on the gateway for the route table",
        },
    )


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok", "service": "platform-gateway"}


@app.get("/v1/routes")
def list_routes() -> dict[str, Any]:
    return {
        "microservices_only": MICROSERVICES_ONLY,
        "resource_routes": _resource_route_table(),
        "platform_routes": PLATFORM_ROUTES,
        "core_service_url": CORE_SERVICE_URL,
        "inventory_service_url": INVENTORY_SERVICE_URL,
        "cost_service_url": COST_SERVICE_URL,
        "analysis_service_url": ANALYSIS_SERVICE_URL,
        "metrics_service_url": METRICS_SERVICE_URL,
    }


def _parse_resource_path(path: str) -> tuple[str, str] | None:
    """Return (api_slug, remainder) for /resources/* and /api/resources/* paths."""
    normalized = path.rstrip("/") or path
    for prefix in ("/api/resources/", "/resources/"):
        if normalized == prefix.rstrip("/"):
            return None
        if normalized.startswith(prefix):
            rest = normalized[len(prefix):]
            if not rest:
                return None
            slug, _, remainder = rest.partition("/")
            return slug, remainder
    return None


def _resolve_resource_service(api_slug: str, path: str) -> tuple[Any | None, str]:
    """Map gateway resource segment to microservice config and remainder path."""
    if path:
        head, _, tail = path.partition("/")
        canonical = f"{api_slug}/{head}".lower()
        cfg = get_service_by_canonical(canonical)
        if cfg:
            return cfg, tail
    cfg = get_service_by_api_slug(api_slug)
    return cfg, path


def _resolve_resource_upstream(path: str) -> tuple[str, str] | None:
    """Resolve a resource inventory path to (upstream_base, upstream_path)."""
    parsed = _parse_resource_path(path)
    if not parsed:
        return None
    api_slug, remainder = parsed
    if api_slug == "detail" and not remainder:
        return INVENTORY_SERVICE_URL, "/resources/detail"

    cfg, tail = _resolve_resource_service(api_slug, remainder)
    prefix = f"/api/resources/{cfg.api_slug if cfg else api_slug}"
    route = _resource_route_table().get(prefix, {})
    migrated = bool(route.get("migrated") or (cfg and cfg.migrated))

    if migrated and cfg:
        upstream_path = "/v1/resources"
        if tail:
            upstream_path = f"/v1/resources/{tail}"
        return cfg.base_url, upstream_path

    inventory_path = f"/resources/{api_slug}"
    if remainder:
        inventory_path = f"{inventory_path}/{remainder}"
    return INVENTORY_SERVICE_URL, inventory_path


async def _handle_resource_proxy(api_slug: str, request: Request, path: str = "") -> Response:
    if api_slug == "detail" and not path:
        return await _proxy(request, INVENTORY_SERVICE_URL, "/resources/detail")

    cfg, remainder = _resolve_resource_service(api_slug, path)
    prefix = f"/api/resources/{cfg.api_slug if cfg else api_slug}"
    route = _resource_route_table().get(prefix, {})
    migrated = bool(route.get("migrated") or (cfg and cfg.migrated))

    if migrated and cfg:
        upstream_base = cfg.base_url
        upstream_path = "/v1/resources"
        if remainder:
            upstream_path = f"/v1/resources/{remainder}"
        if request.method == "POST" and remainder == "sync":
            upstream_path = "/v1/sync"
        return await _proxy(request, upstream_base, upstream_path)

    inventory_path = f"/resources/{api_slug}"
    if path:
        inventory_path = f"{inventory_path}/{path}"
    return await _proxy(request, INVENTORY_SERVICE_URL, inventory_path)


@app.api_route("/api/resources/{api_slug}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.api_route("/api/resources/{api_slug}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.api_route("/resources/{api_slug}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.api_route("/resources/{api_slug}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_resources(api_slug: str, request: Request, path: str = "") -> Response:
    return await _handle_resource_proxy(api_slug, request, path)


def _strip_api_prefix(path: str) -> str:
    """Platform services mount routers without /api (frontend proxy strips it too)."""
    if path == "/api":
        return "/"
    if path.startswith("/api/"):
        return path[4:]
    return path


def _rewrite_azure_metrics_path(path: str) -> str:
    """Map legacy /azure/metrics/* callers to metrics-service /metrics/* routes."""
    for prefix in ("/api/azure/metrics", "/azure/metrics"):
        if path == prefix:
            return "/metrics"
        if path.startswith(f"{prefix}/"):
            return f"/metrics{path[len(prefix):]}"
    return _strip_api_prefix(path)


def _upstream_path_for_match(path: str, prefix: str, base: str) -> str:
    if prefix.endswith("/azure/metrics") or prefix == "/azure/metrics":
        return _rewrite_azure_metrics_path(path)
    if prefix.startswith("/api"):
        return _strip_api_prefix(path)
    return path


def _resolve_platform_upstream(path: str) -> tuple[str, str] | None:
    """Return (upstream_base, upstream_path) for platform routes, or None."""
    for prefix, base in sorted(PLATFORM_ROUTES.items(), key=lambda item: len(item[0]), reverse=True):
        if path == prefix or path.startswith(f"{prefix}/"):
            upstream_path = _upstream_path_for_match(path, prefix, base)
            return base, upstream_path
    return None


@app.api_route("/api/{platform}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_platform(platform: str, request: Request, path: str = "") -> Response:
    full_path = f"/api/{platform}" + (f"/{path}" if path else "")
    resolved = _resolve_platform_upstream(full_path)
    if resolved:
        upstream_base, upstream_path = resolved
        return await _proxy(request, upstream_base, upstream_path)
    return _unrouted_response(full_path)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_fallback(request: Request, path: str) -> Response:
    full_path = f"/{path}"
    resolved = _resolve_platform_upstream(full_path)
    if resolved:
        upstream_base, upstream_path = resolved
        return await _proxy(request, upstream_base, upstream_path)
    return _unrouted_response(full_path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=GATEWAY_PORT,
        reload=os.getenv("RELOAD", "") == "1",
    )

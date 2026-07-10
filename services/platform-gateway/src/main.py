"""Platform API gateway — strangler proxy to resource microservices and monolith."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "costoptimizer-core"))

from costoptimizer_core.registry import all_service_configs, get_service_by_api_slug

MONOLITH_URL = os.getenv("MONOLITH_URL", "http://127.0.0.1:8000").rstrip("/")
GATEWAY_PORT = int(os.getenv("PORT", "8080"))

app = FastAPI(title="CostOptimizer Platform Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
            table[prefix] = row
    for cfg in all_service_configs():
        prefix = f"/api/resources/{cfg.api_slug}"
        table.setdefault(prefix, {
            "path_prefix": prefix,
            "target": cfg.base_url if cfg.migrated else MONOLITH_URL,
            "migrated": cfg.migrated,
            "service_id": cfg.service_id,
        })
    return table


PLATFORM_ROUTES = {
    "/api/auth": os.getenv("AUTH_SERVICE_URL", "http://127.0.0.1:8010"),
    "/api/costs": os.getenv("COST_SERVICE_URL", "http://127.0.0.1:8011"),
    "/api/optimize": os.getenv("ORCHESTRATOR_URL", "http://127.0.0.1:8012"),
}


def _hop_headers(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in ("authorization", "x-correlation-id", "x-request-id"):
        if key in request.headers:
            out[key] = request.headers[key]
    return out


async def _proxy(request: Request, upstream_base: str, upstream_path: str) -> Response:
    url = f"{upstream_base.rstrip('/')}{upstream_path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    body = await request.body()
    async with httpx.AsyncClient(timeout=120.0) as client:
        upstream = await client.request(
            request.method,
            url,
            headers=_hop_headers(request),
            content=body if body else None,
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


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok", "service": "platform-gateway"}


@app.get("/v1/routes")
def list_routes() -> dict[str, Any]:
    return {
        "resource_routes": _resource_route_table(),
        "platform_routes": PLATFORM_ROUTES,
        "monolith_url": MONOLITH_URL,
    }


@app.api_route("/api/resources/{api_slug}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.api_route("/api/resources/{api_slug}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_resources(api_slug: str, request: Request, path: str = "") -> Response:
    cfg = get_service_by_api_slug(api_slug)
    prefix = f"/api/resources/{api_slug}"
    route = _resource_route_table().get(prefix, {})
    migrated = bool(route.get("migrated") or (cfg and cfg.migrated))

    if migrated and cfg:
        upstream_base = cfg.base_url
        upstream_path = "/v1/resources"
        if path:
            upstream_path = f"/v1/resources/{path}"
        if request.method == "POST" and path == "sync":
            upstream_path = "/v1/sync"
        return await _proxy(request, upstream_base, upstream_path)

    monolith_path = f"/resources/{api_slug}"
    if path:
        monolith_path = f"{monolith_path}/{path}"
    return await _proxy(request, MONOLITH_URL, monolith_path)


@app.api_route("/api/{platform}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_platform(platform: str, request: Request, path: str = "") -> Response:
    base = PLATFORM_ROUTES.get(f"/api/{platform}")
    if base:
        upstream_path = f"/{path}" if path else ""
        if platform == "auth":
            upstream_path = f"/auth/{path}" if path else "/auth"
        elif platform == "costs":
            upstream_path = f"/costs/{path}" if path else "/costs"
        elif platform == "optimize":
            upstream_path = f"/optimize/{path}" if path else "/optimize"
        return await _proxy(request, base, upstream_path)
    return await _proxy(request, MONOLITH_URL, request.url.path)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_fallback(request: Request, path: str) -> Response:
    if path.startswith("api/"):
        return await _proxy(request, MONOLITH_URL, f"/{path}")
    return JSONResponse(status_code=404, content={"detail": "Not found"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=GATEWAY_PORT,
        reload=os.getenv("RELOAD", "") == "1",
    )

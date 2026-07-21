"""Microservice registry and gateway tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "costoptimizer-core"))


def test_service_registry_has_all_resource_types():
    from costoptimizer_core.registry import all_service_configs

    configs = all_service_configs()
    assert len(configs) >= 40
    ids = {c.service_id for c in configs}
    assert "compute-disk" in ids
    assert "security-keyvault" in ids


def test_migrated_services_marked():
    from costoptimizer_core.registry import MIGRATED_SERVICES, get_service_config

    for sid in MIGRATED_SERVICES:
        cfg = get_service_config(sid)
        assert cfg.migrated is True


def test_gateway_health():
    import importlib.util
    from fastapi.testclient import TestClient

    gateway_src = ROOT / "services" / "platform-gateway" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("platform_gateway_main", gateway_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    client = TestClient(module.app)
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json()["service"] == "platform-gateway"


def test_gateway_platform_route_table_includes_analysis():
    import importlib.util

    gateway_src = ROOT / "services" / "platform-gateway" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("platform_gateway_main_routes", gateway_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert "/api/optimize" in module.PLATFORM_ROUTES
    assert "/api/events" in module.PLATFORM_ROUTES
    assert "/api/activity" in module.PLATFORM_ROUTES
    assert "/optimize" in module.PLATFORM_ROUTES
    assert "/events" in module.PLATFORM_ROUTES
    assert "/api/costs" in module.PLATFORM_ROUTES
    assert "/api/metrics" in module.PLATFORM_ROUTES
    assert module.PLATFORM_ROUTES["/api/metrics"] == module.METRICS_SERVICE_URL
    assert "/api/engine" in module.PLATFORM_ROUTES
    assert module.PLATFORM_ROUTES["/api/engine"] == module.ANALYSIS_SERVICE_URL
    assert module.PLATFORM_ROUTES["/api/costs"] == module.COST_SERVICE_URL
    assert module.PLATFORM_ROUTES["/api/auth"] == module.CORE_SERVICE_URL
    assert module.MICROSERVICES_ONLY is True


def test_gateway_strips_api_prefix_for_cost_upstream():
    import importlib.util

    gateway_src = ROOT / "services" / "platform-gateway" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("platform_gateway_main_cost", gateway_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    resolved = module._resolve_platform_upstream("/api/costs/summary")
    assert resolved == (module.COST_SERVICE_URL, "/costs/summary")


def test_gateway_routes_resource_detail_to_inventory():
    import importlib.util

    gateway_src = ROOT / "services" / "platform-gateway" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("platform_gateway_main_detail", gateway_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    resolved = module._resolve_platform_upstream("/resources/detail")
    assert resolved == (module.INVENTORY_SERVICE_URL, "/resources/detail")
    assert "/api/metrics" in module.PLATFORM_ROUTES
    assert module.PLATFORM_ROUTES["/api/metrics"] == module.METRICS_SERVICE_URL


def test_gateway_routes_dashboard_to_inventory():
    import importlib.util

    gateway_src = ROOT / "services" / "platform-gateway" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("platform_gateway_main_dashboard", gateway_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    resolved = module._resolve_platform_upstream("/dashboard/overview")
    assert resolved == (module.INVENTORY_SERVICE_URL, "/dashboard/overview")
    resolved_api = module._resolve_platform_upstream("/api/dashboard/overview")
    assert resolved_api == (module.INVENTORY_SERVICE_URL, "/dashboard/overview")


def test_gateway_strips_api_prefix_for_metrics_upstream():
    import importlib.util

    gateway_src = ROOT / "services" / "platform-gateway" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("platform_gateway_main_strip", gateway_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    resolved = module._resolve_platform_upstream("/api/metrics/resource/auto")
    assert resolved is not None
    upstream_base, upstream_path = resolved
    assert upstream_path == "/metrics/resource/auto"
    assert upstream_base == module.METRICS_SERVICE_URL


def test_platform_metrics_health():
    from fastapi.testclient import TestClient

    module = _load_platform_main("platform-metrics")
    client = TestClient(module.app)
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json()["service"] == "platform-metrics"


def _load_platform_main(service_name: str):
    import importlib.util

    service_src = ROOT / "services" / service_name / "src" / "main.py"
    spec = importlib.util.spec_from_file_location(f"{service_name}_main", service_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_platform_cost_health():
    from fastapi.testclient import TestClient

    module = _load_platform_main("platform-cost")
    client = TestClient(module.app)
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json()["service"] == "platform-cost"


def test_platform_analysis_health():
    from fastapi.testclient import TestClient

    module = _load_platform_main("platform-analysis")
    client = TestClient(module.app)
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json()["service"] == "platform-analysis"


def test_platform_core_health():
    from fastapi.testclient import TestClient

    module = _load_platform_auth_main()
    client = TestClient(module.app)
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json()["service"] == "platform-core"


def _load_platform_auth_main():
    import importlib.util

    service_src = ROOT / "services" / "platform-auth" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("platform_auth_main", service_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_service_app(service_id: str):
    import importlib.util

    service_src = ROOT / "services" / "resources" / service_id / "src" / "service_app.py"
    spec = importlib.util.spec_from_file_location(f"{service_id}_service_app", service_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.app


def test_gateway_routes_canonical_disk_path_to_inventory():
    import importlib.util

    gateway_src = ROOT / "services" / "platform-gateway" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("platform_gateway_main_canonical", gateway_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    cfg, remainder = module._resolve_resource_service("compute", "disk")
    assert cfg is not None
    assert cfg.service_id == "compute-disk"
    assert remainder == ""


def test_compute_disk_contract_health():
    from fastapi.testclient import TestClient

    client = TestClient(_load_service_app("compute-disk"))
    res = client.get("/v1/meta")
    assert res.status_code == 200
    body = res.json()
    assert body["canonical_type"] == "compute/disk"
    assert body["api_slug"] == "disks"


def test_security_keyvault_contract_health():
    from fastapi.testclient import TestClient

    client = TestClient(_load_service_app("security-keyvault"))
    res = client.get("/v1/meta")
    assert res.status_code == 200
    body = res.json()
    assert body["canonical_type"] == "security/keyvault"
    assert body["api_slug"] == "keyvaults"


def _load_gateway_module():
    import importlib.util

    gateway_src = ROOT / "services" / "platform-gateway" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("platform_gateway_main_timeout", gateway_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_gateway_resolve_events_to_analysis_service():
    module = _load_gateway_module()
    resolved = module._resolve_platform_upstream("/api/events/jobs/sub-a")
    assert resolved is not None
    upstream_base, upstream_path = resolved
    assert upstream_base == module.ANALYSIS_SERVICE_URL
    assert upstream_path == "/events/jobs/sub-a"


def test_gateway_resolve_activity_to_analysis_service():
    module = _load_gateway_module()
    resolved = module._resolve_platform_upstream("/api/activity/finding/f1")
    assert resolved is not None
    upstream_base, upstream_path = resolved
    assert upstream_base == module.ANALYSIS_SERVICE_URL
    assert upstream_path == "/activity/finding/f1"


@pytest.mark.parametrize(
    "path,expected_service_attr,expected_path",
    [
        ("/api/scheduler/status", "INVENTORY_SERVICE_URL", "/scheduler/status"),
        ("/api/cost/topspend", "COST_SERVICE_URL", "/cost/topspend"),
        ("/cost/daily", "COST_SERVICE_URL", "/cost/daily"),
        ("/api/budgets", "COST_SERVICE_URL", "/budgets"),
        ("/api/anomalies/recent", "COST_SERVICE_URL", "/anomalies/recent"),
        ("/api/optimize/findings", "ANALYSIS_SERVICE_URL", "/optimize/findings"),
        ("/api/engine/analysis/sub-a/combined", "ANALYSIS_SERVICE_URL", "/engine/analysis/sub-a/combined"),
        ("/api/pipeline/status", "ANALYSIS_SERVICE_URL", "/pipeline/status"),
        ("/api/metrics/profiles", "METRICS_SERVICE_URL", "/metrics/profiles"),
        ("/api/azure/metrics/resource/auto", "METRICS_SERVICE_URL", "/metrics/resource/auto"),
        ("/azure/subscriptions", "INVENTORY_SERVICE_URL", "/azure/subscriptions"),
        ("/sync/pipeline", "INVENTORY_SERVICE_URL", "/sync/pipeline"),
        ("/api/sync/pipeline", "INVENTORY_SERVICE_URL", "/sync/pipeline"),
        ("/sync/progress", "INVENTORY_SERVICE_URL", "/sync/progress"),
        ("/api/sync/progress", "INVENTORY_SERVICE_URL", "/sync/progress"),
        ("/sync/progress/stream", "INVENTORY_SERVICE_URL", "/sync/progress/stream"),
        ("/api/sync/progress/stream", "INVENTORY_SERVICE_URL", "/sync/progress/stream"),
        ("/sync/full", "INVENTORY_SERVICE_URL", "/sync/full"),
        ("/api/sync/full", "INVENTORY_SERVICE_URL", "/sync/full"),
        ("/sync/status", "INVENTORY_SERVICE_URL", "/sync/status"),
        ("/api/auth/me", "CORE_SERVICE_URL", "/auth/me"),
        ("/auth/me", "CORE_SERVICE_URL", "/auth/me"),
        ("/api/admin/optimization/overview", "CORE_SERVICE_URL", "/admin/optimization/overview"),
        ("/optimize/jobs", "ANALYSIS_SERVICE_URL", "/optimize/jobs"),
        ("/optimize/trends", "ANALYSIS_SERVICE_URL", "/optimize/trends"),
        ("/optimize/findings/summary", "ANALYSIS_SERVICE_URL", "/optimize/findings/summary"),
        ("/optimize/actions/list", "ANALYSIS_SERVICE_URL", "/optimize/actions/list"),
        ("/advisor", "INVENTORY_SERVICE_URL", "/advisor"),
        ("/alerts", "INVENTORY_SERVICE_URL", "/alerts"),
        ("/outliers/underutil", "INVENTORY_SERVICE_URL", "/outliers/underutil"),
        ("/dashboard/overview", "INVENTORY_SERVICE_URL", "/dashboard/overview"),
        ("/costs/sync", "COST_SERVICE_URL", "/costs/sync"),
    ],
)
def test_gateway_routes_traffic_to_expected_service(path, expected_service_attr, expected_path):
    module = _load_gateway_module()
    resolved = module._resolve_platform_upstream(path)
    assert resolved is not None
    upstream_base, upstream_path = resolved
    assert upstream_base == getattr(module, expected_service_attr)
    assert upstream_path == expected_path


@pytest.mark.parametrize(
    "path,expected_service_id,expected_upstream_path",
    [
        ("/resources/disks", "compute-disk", "/v1/resources"),
        ("/api/resources/disks", "compute-disk", "/v1/resources"),
        ("/resources/compute/disk", "compute-disk", "/v1/resources"),
        ("/resources/keyvaults", "security-keyvault", "/v1/resources"),
    ],
)
def test_gateway_routes_migrated_resources(path, expected_service_id, expected_upstream_path):
    from costoptimizer_core.registry import get_service_config

    module = _load_gateway_module()
    cfg = get_service_config(expected_service_id)
    resolved = module._resolve_resource_upstream(path)
    assert resolved is not None
    upstream_base, upstream_path = resolved
    assert upstream_base.rstrip("/") == cfg.base_url.rstrip("/")
    assert upstream_path == expected_upstream_path


def test_gateway_routes_non_migrated_resources_to_inventory():
    module = _load_gateway_module()
    for path, expected in (
        ("/resources/vms", "/resources/vms"),
        ("/resources/sync", "/resources/sync"),
        ("/resources/subscriptions", "/resources/subscriptions"),
        ("/resources/subscriptions/validate", "/resources/subscriptions/validate"),
    ):
        resolved = module._resolve_resource_upstream(path)
        assert resolved == (module.INVENTORY_SERVICE_URL, expected)


def test_gateway_hop_headers_forwards_content_type():
    module = _load_gateway_module()
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/optimize/resources/analyze",
        "headers": [
            (b"authorization", b"Bearer test-token"),
            (b"content-type", b"application/json"),
            (b"accept", b"application/json"),
        ],
    }

    async def receive():
        return {"type": "http.request", "body": b'{"subscription_id":"a"}', "more_body": False}

    request = Request(scope, receive)
    headers = module._hop_headers(request)
    assert headers["authorization"] == "Bearer test-token"
    assert headers["content-type"] == "application/json"
    assert headers["accept"] == "application/json"


def test_gateway_optimize_timeout_longer_than_default():
    module = _load_gateway_module()
    default_timeout = module._client_timeout("GET", "/metrics/profiles")
    optimize_timeout = module._client_timeout("GET", "/optimize/findings")
    sync_timeout = module._client_timeout("POST", "/resources/sync")
    assert optimize_timeout == module.GATEWAY_OPTIMIZE_TIMEOUT_SECONDS
    assert default_timeout == module.GATEWAY_UPSTREAM_TIMEOUT_SECONDS
    assert sync_timeout == module.GATEWAY_SYNC_ACCEPT_TIMEOUT_SECONDS
    assert optimize_timeout >= default_timeout


def test_gateway_resource_handler_routes_stripped_api_paths():
    """Frontend proxy strips /api — migrated resources must not fall through to inventory."""
    from unittest.mock import AsyncMock, patch

    from fastapi.testclient import TestClient

    module = _load_gateway_module()
    client = TestClient(module.app)
    captured: dict[str, str] = {}

    async def _capture_proxy(request, upstream_base, upstream_path):
        captured["upstream_base"] = upstream_base
        captured["upstream_path"] = upstream_path
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": True})

    with patch.object(module, "_proxy", side_effect=_capture_proxy):
        res = client.get("/resources/disks?subscription_id=test")
    assert res.status_code == 200
    assert captured["upstream_path"] == "/v1/resources"
    assert "compute-disk" in captured["upstream_base"]


def test_gateway_resource_handler_routes_inventory_paths():
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    module = _load_gateway_module()
    client = TestClient(module.app)
    captured: dict[str, str] = {}

    async def _capture_proxy(request, upstream_base, upstream_path):
        captured["upstream_base"] = upstream_base
        captured["upstream_path"] = upstream_path
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": True})

    with patch.object(module, "_proxy", side_effect=_capture_proxy):
        res = client.get("/resources/vms?subscription_id=test")
    assert res.status_code == 200
    assert captured["upstream_base"] == module.INVENTORY_SERVICE_URL
    assert captured["upstream_path"] == "/resources/vms"


def test_gateway_unrouted_path_returns_404():
    from fastapi.testclient import TestClient

    module = _load_gateway_module()
    client = TestClient(module.app)
    res = client.get("/unknown-microservice-route")
    assert res.status_code == 404
    body = res.json()
    assert body["microservices_only"] is True
    assert "No microservice route" in body["detail"]


def test_analysis_service_exposes_critical_optimize_routes():
    from fastapi.testclient import TestClient

    module = _load_platform_main("platform-analysis")
    client = TestClient(module.app, raise_server_exceptions=False)
    for path in (
        "/optimize/jobs",
        "/optimize/trends",
        "/optimize/findings",
        "/optimize/findings/summary",
        "/optimize/actions/list",
    ):
        res = client.get(path)
        assert res.status_code != 404, path


def test_gateway_proxy_read_timeout_returns_504(monkeypatch):
    import asyncio
    import httpx
    from fastapi import Request

    module = _load_gateway_module()

    class _TimeoutClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, *args, **kwargs):
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: _TimeoutClient())

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/optimize/findings",
        "query_string": b"",
        "headers": [],
    }
    request = Request(scope)

    async def _empty_body():
        return b""

    monkeypatch.setattr(request, "body", _empty_body)

    response = asyncio.run(
        module._proxy(request, "http://analysis:8013", "/optimize/findings")
    )
    assert response.status_code == 504
    payload = __import__("json").loads(response.body)
    assert payload["detail"] == "Upstream service timed out"
    assert payload["upstream"] == "/optimize/findings"


def test_gateway_proxy_connect_error_returns_502(monkeypatch):
    import asyncio
    import httpx
    from fastapi import Request

    module = _load_gateway_module()

    class _ConnectErrorClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, *args, **kwargs):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: _ConnectErrorClient())

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/auth/me",
        "query_string": b"",
        "headers": [],
    }
    request = Request(scope)

    async def _empty_body():
        return b""

    monkeypatch.setattr(request, "body", _empty_body)

    response = asyncio.run(module._proxy(request, "http://core:8010", "/auth/me"))
    assert response.status_code == 502
    payload = __import__("json").loads(response.body)
    assert payload["detail"] == "Upstream service unavailable"
    assert payload["upstream"] == "/auth/me"


def _optimize_jobs_client():
    from fastapi.testclient import TestClient

    from app.database import SessionLocal, init_db
    from app.integration_app import app
    from app.models import AppUser
    from app.user_auth import ROLE_ADMIN, hash_password

    init_db()
    db = SessionLocal()
    try:
        db.query(AppUser).delete()
        db.commit()
        db.add(
            AppUser(
                id="optimize-jobs-test",
                username="admin",
                display_name="Administrator",
                password_hash=hash_password("password123"),
                role=ROLE_ADMIN,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(app, raise_server_exceptions=False)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    token = login.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_optimize_jobs_returns_empty_for_unregistered_subscription():
    client = _optimize_jobs_client()
    sub = "93ca908b-5732-440d-b712-f6d7951951c0"
    res = client.get(
        "/optimize/jobs",
        params={"subscription_id": sub, "active_only": True, "limit": 5},
    )
    assert res.status_code == 200
    assert res.json() == []


def test_optimize_jobs_returns_200_for_registered_subscription():
    from app.database import SessionLocal
    from app.models import SubscriptionCache

    sub = "93ca908b-5732-440d-b712-f6d7951951c0"
    db = SessionLocal()
    try:
        db.query(SubscriptionCache).filter(SubscriptionCache.subscription_id == sub).delete()
        db.add(
            SubscriptionCache(
                subscription_id=sub,
                display_name="Prod",
                state="Enabled",
                raw_json="{}",
            )
        )
        db.commit()
    finally:
        db.close()

    client = _optimize_jobs_client()
    res = client.get(
        "/optimize/jobs",
        params={"subscription_id": sub, "active_only": True, "limit": 5},
    )
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_gateway_routes_optimize_jobs_to_analysis():
    module = _load_gateway_module()
    resolved = module._resolve_platform_upstream("/optimize/jobs")
    assert resolved is not None
    upstream_base, upstream_path = resolved
    assert upstream_base == module.ANALYSIS_SERVICE_URL
    assert upstream_path == "/optimize/jobs"

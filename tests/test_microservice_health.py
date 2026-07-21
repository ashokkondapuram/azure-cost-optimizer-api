"""Health checks and gateway route smoke tests for platform microservices."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "costoptimizer-core"))


def _load_main(service_name: str):
    service_src = ROOT / "services" / service_name / "src" / "main.py"
    spec = importlib.util.spec_from_file_location(f"{service_name}_health_main", service_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_core_main():
    service_src = ROOT / "services" / "platform-auth" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("platform_core_health_main", service_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_gateway():
    return _load_main("platform-gateway")


@pytest.mark.parametrize(
    "service_name,service_id",
    [
        ("platform-gateway", "platform-gateway"),
        ("platform-inventory", "platform-inventory"),
        ("platform-cost", "platform-cost"),
        ("platform-analysis", "platform-analysis"),
        ("platform-metrics", "platform-metrics"),
    ],
)
def test_service_health_live(service_name, service_id):
    module = _load_main(service_name)
    client = TestClient(module.app)
    res = client.get("/health/live")
    assert res.status_code == 200
    body = res.json()
    assert body.get("status") == "ok"
    assert body.get("service") == service_id


def test_platform_core_health_live():
    module = _load_core_main()
    client = TestClient(module.app)
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json()["service"] == "platform-core"


@pytest.mark.parametrize(
    "path,expected_path",
    [
        ("/api/admin/optimization/overview", "/admin/optimization/overview"),
    ],
)
def test_gateway_core_advanced_routes(path, expected_path):
    module = _load_gateway()
    resolved = module._resolve_platform_upstream(path)
    assert resolved is not None
    upstream_base, upstream_path = resolved
    assert upstream_base == module.CORE_SERVICE_URL
    assert upstream_path == expected_path


def test_gateway_v1_routes_lists_platform_routes():
    module = _load_gateway()
    client = TestClient(module.app)
    res = client.get("/v1/routes")
    assert res.status_code == 200
    body = res.json()
    assert body["microservices_only"] is True
    assert "/api/optimize" in body["platform_routes"]
    assert body["core_service_url"]
    assert "monolith_url" not in body

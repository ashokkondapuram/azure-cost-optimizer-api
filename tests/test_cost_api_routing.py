"""Fast smoke tests for cost API routing and gateway proxy paths."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "costoptimizer-core"))


def _load_gateway():
    gateway_src = ROOT / "services" / "platform-gateway" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("platform_gateway_cost_routing", gateway_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_cost_service():
    cost_src = ROOT / "services" / "platform-cost" / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("platform_cost_routing", cost_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "path,expected_upstream",
    [
        ("/api/costs/summary", "/costs/summary"),
        ("/costs/summary", "/costs/summary"),
        ("/api/costs/timeframes", "/costs/timeframes"),
        ("/api/cost/topspend", "/cost/topspend"),
        ("/cost/topspend", "/cost/topspend"),
        ("/api/dashboard/overview", "/dashboard/overview"),
    ],
)
def test_gateway_resolves_cost_and_dashboard_paths(path, expected_upstream):
    module = _load_gateway()
    resolved = module._resolve_platform_upstream(path)
    assert resolved is not None
    upstream_base, upstream_path = resolved
    assert upstream_path == expected_upstream
    if path.startswith("/api/costs") or path.startswith("/costs"):
        assert upstream_base == module.PLATFORM_ROUTES["/api/costs"]
    elif path.startswith("/api/cost/") or path.startswith("/cost/"):
        assert upstream_base == module.COST_SERVICE_URL
    else:
        assert upstream_base == module.INVENTORY_SERVICE_URL


def test_cost_service_exposes_public_timeframes():
    module = _load_cost_service()
    client = TestClient(module.app)
    res = client.get("/costs/timeframes")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body.get("timeframes"), list)
    assert any(tf.get("id") == "MonthToDate" for tf in body["timeframes"])


def test_cost_service_health():
    module = _load_cost_service()
    client = TestClient(module.app)
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json()["service"] == "platform-cost"

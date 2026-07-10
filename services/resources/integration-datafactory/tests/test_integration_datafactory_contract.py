"""Contract tests for integration-datafactory microservice."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "costoptimizer-core"))


@pytest.fixture
def client():
    import importlib.util

    service_src = ROOT / "services" / "resources" / "integration-datafactory" / "src" / "service_app.py"
    spec = importlib.util.spec_from_file_location("integration-datafactory_service_app", service_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return TestClient(module.app)


def test_health_live(client):
    res = client.get("/health/live")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service_id"] == "integration-datafactory"


def test_meta(client):
    res = client.get("/v1/meta")
    assert res.status_code == 200
    body = res.json()
    assert body["canonical_type"] == "integration/datafactory"
    assert body["api_slug"] == "datafactory"

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


def _load_service_app(service_id: str):
    import importlib.util

    service_src = ROOT / "services" / "resources" / service_id / "src" / "service_app.py"
    spec = importlib.util.spec_from_file_location(f"{service_id}_service_app", service_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.app


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

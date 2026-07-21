"""HTTP route tests for action centre endpoints on platform microservices."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.focus_mapping import normalize_arm_id
from app.models import Base, OptimizationFinding, ResourceSnapshot

SUB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
VM_ID = (
    f"/subscriptions/{SUB}/resourceGroups/rg/providers/"
    "Microsoft.Compute/virtualMachines/vm-live"
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _load_platform_main(service_name: str):
    import importlib.util

    service_src = ROOT / "services" / service_name / "src" / "main.py"
    spec = importlib.util.spec_from_file_location(f"{service_name}_main", service_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _add_snapshot(db, *, resource_id: str, name: str, resource_type: str):
    db.add(
        ResourceSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=SUB,
            resource_id=normalize_arm_id(resource_id),
            resource_name=name,
            resource_type=resource_type,
            resource_group="rg",
            location="eastus",
            state="running",
            properties_json='{"provisioningState":"Succeeded"}',
            tags_json="{}",
            sku_json="{}",
            is_active=True,
            synced_at=datetime.now(timezone.utc),
        )
    )


def _auth_patches():
    from contextlib import ExitStack

    from app.user_auth import ROLE_VIEWER

    auth_user = {
        "id": "viewer-1",
        "username": "viewer-1",
        "display_name": "Viewer",
        "role": ROLE_VIEWER,
    }
    stack = ExitStack()
    stack.enter_context(patch("app.middleware.app_auth.decode_access_token", return_value={"sub": "viewer-1"}))
    stack.enter_context(patch("app.middleware.app_auth.resolve_authenticated_user", return_value=auth_user))
    return stack


def test_platform_analysis_actions_list_inventory_only(db, monkeypatch):
    from app.optimization_actions import list_optimization_actions

    _add_snapshot(db, resource_id=VM_ID, name="vm-live", resource_type="compute/vm")
    db.commit()

    module = _load_platform_main("platform-analysis")
    monkeypatch.setattr("app.validators.ensure_subscription_known", lambda _db, sub: sub.lower())

    def _override_db():
        yield db

    module.app.dependency_overrides[get_db] = _override_db
    try:
        with _auth_patches():
            client = TestClient(module.app)
            resp = client.get(
                "/optimize/actions/list",
                params={"subscription_id": SUB, "inventory_only": True},
                headers={"Authorization": "Bearer test-token"},
            )
        assert resp.status_code == 200
        assert resp.json()["total"] == list_optimization_actions(db, SUB, inventory_only=True)["total"]
    finally:
        module.app.dependency_overrides.clear()


def test_platform_analysis_findings_tolerates_malformed_evidence_json(db, monkeypatch):
    _add_snapshot(db, resource_id=VM_ID, name="vm-live", resource_type="compute/vm")
    db.add(OptimizationFinding(
        id="f-bad-evidence",
        subscription_id=SUB,
        resource_id=normalize_arm_id(VM_ID),
        status="open",
        severity="HIGH",
        category="COMPUTE",
        estimated_savings_usd=25.0,
        evidence_json="[object Object]",
    ))
    db.commit()

    module = _load_platform_main("platform-analysis")
    monkeypatch.setattr("app.validators.ensure_subscription_known", lambda _db, sub: sub.lower())

    def _override_db():
        yield db

    module.app.dependency_overrides[get_db] = _override_db
    try:
        with _auth_patches():
            client = TestClient(module.app)
            resp = client.get(
                "/optimize/findings",
                params={"subscription_id": SUB, "inventory_only": True, "status": "open"},
                headers={"Authorization": "Bearer test-token"},
            )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert isinstance(items[0]["evidence"], dict)
    finally:
        module.app.dependency_overrides.clear()


def test_platform_inventory_from_cost_inventory_only(db, monkeypatch):
    _add_snapshot(db, resource_id=VM_ID, name="vm-live", resource_type="compute/vm")
    db.commit()

    module = _load_platform_main("platform-inventory")
    monkeypatch.setattr("app.validators.ensure_subscription_known", lambda _db, sub: sub.lower())

    def _override_db():
        yield db

    module.app.dependency_overrides[get_db] = _override_db
    try:
        with _auth_patches():
            client = TestClient(module.app)
            resp = client.get(
                "/resources/from-cost",
                params={"subscription_id": SUB, "inventory_only": True, "limit": 50},
                headers={"Authorization": "Bearer test-token"},
            )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["id"].lower() == normalize_arm_id(VM_ID)
    finally:
        module.app.dependency_overrides.clear()


def test_list_findings_coerces_malformed_evidence_json(db, monkeypatch):
    from app.integration_app import app
    from app.routers.optimize import _coerce_evidence_dict

    _add_snapshot(db, resource_id=VM_ID, name="vm-live", resource_type="compute/vm")
    db.add(OptimizationFinding(
        id="f-bad-evidence",
        subscription_id=SUB,
        resource_id=normalize_arm_id(VM_ID),
        status="open",
        severity="HIGH",
        category="COMPUTE",
        estimated_savings_usd=25.0,
        evidence_json="[object Object]",
    ))
    db.commit()

    assert _coerce_evidence_dict("[object Object]") == {}

    monkeypatch.setattr("app.validators.ensure_subscription_known", lambda _db, sub: sub.lower())

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        with _auth_patches():
            client = TestClient(app)
            resp = client.get(
                "/optimize/findings",
                params={"subscription_id": SUB, "inventory_only": True, "status": "open"},
                headers={"Authorization": "Bearer test-token"},
            )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert isinstance(items[0]["evidence"], dict)
    finally:
        app.dependency_overrides.clear()

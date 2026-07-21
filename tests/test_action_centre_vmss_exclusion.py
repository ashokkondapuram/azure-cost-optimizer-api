"""Action centre endpoints must not surface standalone VMSS resources."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.billed_resources import list_billed_resources_page
from app.findings_summary import _filter_findings_to_inventory, build_findings_summary
from app.focus_mapping import normalize_arm_id
from app.models import Base, OptimizationAction, OptimizationFinding, ResourceSnapshot
from app.optimization_actions import list_optimization_actions
from app.resource_store import _inventory_id_set

SUB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
VMSS_ID = (
    f"/subscriptions/{SUB}/resourceGroups/MC_rg/providers/"
    "Microsoft.Compute/virtualMachineScaleSets/aks-system-vmss"
)
AKS_ID = (
    f"/subscriptions/{SUB}/resourceGroups/rg/providers/"
    "Microsoft.ContainerService/managedClusters/prod-aks"
)
VM_ID = (
    f"/subscriptions/{SUB}/resourceGroups/rg/providers/"
    "Microsoft.Compute/virtualMachines/vm-live"
)


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


def test_inventory_id_set_excludes_vmss(db):
    _add_snapshot(db, resource_id=VM_ID, name="vm-live", resource_type="compute/vm")
    _add_snapshot(db, resource_id=VMSS_ID, name="aks-system-vmss", resource_type="compute/vmss")
    _add_snapshot(db, resource_id=AKS_ID, name="prod-aks", resource_type="containers/aks")
    db.commit()

    ids = _inventory_id_set(db, SUB)
    assert normalize_arm_id(VM_ID) in ids
    assert normalize_arm_id(AKS_ID) in ids
    assert normalize_arm_id(VMSS_ID) not in ids


def test_billed_inventory_page_excludes_vmss(db):
    _add_snapshot(db, resource_id=VM_ID, name="vm-live", resource_type="compute/vm")
    _add_snapshot(db, resource_id=VMSS_ID, name="aks-system-vmss", resource_type="compute/vmss")
    db.commit()

    page = list_billed_resources_page(db, SUB, limit=50, offset=0, inventory_only=True)
    returned_ids = {item["id"] for item in page["items"]}
    assert normalize_arm_id(VMSS_ID) not in returned_ids
    assert normalize_arm_id(VM_ID) in returned_ids


def test_findings_summary_inventory_only_excludes_vmss_findings(db):
    _add_snapshot(db, resource_id=VM_ID, name="vm-live", resource_type="compute/vm")
    _add_snapshot(db, resource_id=VMSS_ID, name="aks-system-vmss", resource_type="compute/vmss")
    db.add(OptimizationFinding(
        id="f-vm",
        subscription_id=SUB,
        resource_id=normalize_arm_id(VM_ID),
        status="open",
        severity="HIGH",
        category="COMPUTE",
        estimated_savings_usd=100.0,
    ))
    db.add(OptimizationFinding(
        id="f-vmss",
        subscription_id=SUB,
        resource_id=normalize_arm_id(VMSS_ID),
        resource_type="compute/vmss",
        status="open",
        severity="HIGH",
        category="COMPUTE",
        estimated_savings_usd=80.0,
    ))
    db.commit()

    kept = _filter_findings_to_inventory(db, SUB, db.query(OptimizationFinding).all())
    kept_ids = {row.id for row in kept}
    assert "f-vm" in kept_ids
    assert "f-vmss" not in kept_ids

    summary = build_findings_summary(db, SUB, inventory_only=True)
    assert summary["open_findings"] == 1


def test_actions_list_inventory_only_excludes_vmss(db):
    _add_snapshot(db, resource_id=VM_ID, name="vm-live", resource_type="compute/vm")
    _add_snapshot(db, resource_id=VMSS_ID, name="aks-system-vmss", resource_type="compute/vmss")
    db.add(OptimizationAction(
        id="act-vm",
        resource_id=normalize_arm_id(VM_ID),
        subscription_id=SUB,
        resource_type="compute/vm",
        resource_name="vm-live",
        action_type="resize_down",
        confidence="High",
        performance_risk="Low",
        estimated_monthly_savings=50.0,
        workflow_status="proposed",
    ))
    db.add(OptimizationAction(
        id="act-vmss",
        resource_id=normalize_arm_id(VMSS_ID),
        subscription_id=SUB,
        resource_type="compute/vmss",
        resource_name="aks-system-vmss",
        action_type="resize_down",
        confidence="High",
        performance_risk="Low",
        estimated_monthly_savings=40.0,
        workflow_status="proposed",
    ))
    db.commit()

    listed = list_optimization_actions(db, SUB, inventory_only=True)
    action_ids = {item["id"] for item in listed["items"]}
    assert "act-vm" in action_ids
    assert "act-vmss" not in action_ids
    assert listed["total"] == 1


def test_optimize_findings_route_inventory_only_excludes_vmss(db, monkeypatch):
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.integration_app import app
    from app.user_auth import ROLE_VIEWER

    _add_snapshot(db, resource_id=VM_ID, name="vm-live", resource_type="compute/vm")
    _add_snapshot(db, resource_id=VMSS_ID, name="aks-system-vmss", resource_type="compute/vmss")
    db.add(OptimizationFinding(
        id="f-vm",
        subscription_id=SUB,
        resource_id=normalize_arm_id(VM_ID),
        status="open",
        severity="HIGH",
        category="COMPUTE",
        estimated_savings_usd=100.0,
    ))
    db.add(OptimizationFinding(
        id="f-vmss",
        subscription_id=SUB,
        resource_id=normalize_arm_id(VMSS_ID),
        status="open",
        severity="HIGH",
        category="COMPUTE",
        estimated_savings_usd=80.0,
    ))
    db.commit()

    def _override_db():
        yield db

    monkeypatch.setattr("app.validators.ensure_subscription_known", lambda _db, sub: sub.lower())
    app.dependency_overrides[get_db] = _override_db
    auth_user = {
        "id": "viewer-1",
        "username": "viewer-1",
        "display_name": "Viewer",
        "role": ROLE_VIEWER,
    }
    try:
        with (
            patch("app.middleware.app_auth.decode_access_token", return_value={"sub": "viewer-1"}),
            patch("app.middleware.app_auth.resolve_authenticated_user", return_value=auth_user),
        ):
            client = TestClient(app)
            resp = client.get(
                "/optimize/findings",
                params={"subscription_id": SUB, "inventory_only": True, "status": "open"},
                headers={"Authorization": "Bearer test-token"},
            )
        assert resp.status_code == 200
        items = resp.json()["items"]
        resource_ids = {item["resource_id"].lower() for item in items}
        assert normalize_arm_id(VMSS_ID) not in resource_ids
        assert normalize_arm_id(VM_ID) in resource_ids
    finally:
        app.dependency_overrides.clear()

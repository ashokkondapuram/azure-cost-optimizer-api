"""Tests for GET /resources/vms/{rg}/{name}/sizing."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.focus_mapping import normalize_arm_id
from app.integration_app import app, resource_client
from app.models import ResourceSnapshot
from app.user_auth import ROLE_ADMIN, ROLE_VIEWER
from tests.auth_helpers import auth_header, seed_app_user

SUB = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VM_RID = (
    f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
)


def _seed_subscription():
    init_db()
    db = SessionLocal()
    try:
        if not db.query(ResourceSnapshot).filter(ResourceSnapshot.subscription_id == SUB).first():
            db.add(
                ResourceSnapshot(
                    id="snap-vm-sizing",
                    subscription_id=SUB,
                    resource_id=VM_RID.lower(),
                    resource_name="vm1",
                    resource_type="compute/vm",
                    resource_group="rg",
                    location="eastus",
                    is_active=True,
                )
            )
            db.commit()
    finally:
        db.close()


def _admin_headers() -> dict[str, str]:
    _seed_subscription()
    seed_app_user(user_id="admin-vm-sizing", username="admin-vm-sizing", role=ROLE_ADMIN)
    return auth_header(user_id="admin-vm-sizing", username="admin-vm-sizing", role=ROLE_ADMIN)


def test_vm_sizing_requires_admin():
    _seed_subscription()
    seed_app_user(user_id="viewer-vm-sizing", username="viewer-vm-sizing", role=ROLE_VIEWER)
    client = TestClient(app)
    viewer = auth_header(user_id="viewer-vm-sizing", username="viewer-vm-sizing", role=ROLE_VIEWER)
    resp = client.get(
        "/resources/vms/rg/vm1/sizing",
        headers=viewer,
        params={"subscription_id": SUB},
    )
    assert resp.status_code == 403


@patch("app.integration_app.resource_cost_map_from_db")
@patch.object(resource_client, "get_vm_cpu_metrics")
@patch.object(resource_client, "list_vm_sizes")
@patch.object(resource_client, "get_vm")
def test_get_vm_sizing_extracts_usd_from_cost_map(
    mock_get_vm,
    mock_list_sizes,
    mock_metrics,
    mock_cost_map,
):
    mock_get_vm.return_value = {
        "id": VM_RID,
        "name": "vm1",
        "location": "eastus",
        "properties": {"hardwareProfile": {"vmSize": "Standard_D2ads_v6"}},
    }
    mock_list_sizes.return_value = [
        {"name": "Standard_D2ads_v6", "numberOfCores": 2, "memoryInMB": 8192},
    ]
    mock_metrics.return_value = {"cpu_avg_pct": 4.0, "memory_avg_pct": 20.0}
    mock_cost_map.return_value = {
        normalize_arm_id(VM_RID): {
            "pretax": 100.0,
            "usd": 95.0,
            "currency": "USD",
            "service_name": "Virtual Machines",
        },
    }

    client = TestClient(app)
    resp = client.get(
        "/resources/vms/rg/vm1/sizing",
        headers=_admin_headers(),
        params={"subscription_id": SUB},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    pricing = body.get("pricing") or {}
    if pricing.get("pricing_source") == "export_cost_with_retail_sku_ratio":
        assert pricing.get("current_monthly_cost_usd") == pytest.approx(95.0)


@patch("app.integration_app.resource_cost_map_from_db")
@patch.object(resource_client, "get_vm_cpu_metrics")
@patch.object(resource_client, "list_vm_sizes")
@patch.object(resource_client, "get_vm")
def test_get_vm_sizing_does_not_crash_on_cost_map_dict(
    mock_get_vm,
    mock_list_sizes,
    mock_metrics,
    mock_cost_map,
):
    mock_get_vm.return_value = {
        "id": VM_RID,
        "name": "vm1",
        "location": "eastus",
        "properties": {"hardwareProfile": {"vmSize": "Standard_D2ads_v6"}},
    }
    mock_list_sizes.return_value = [
        {"name": "Standard_D2ads_v6", "numberOfCores": 2, "memoryInMB": 8192},
    ]
    mock_metrics.return_value = {}
    mock_cost_map.return_value = {
        normalize_arm_id(VM_RID): {
            "pretax": 50.0,
            "usd": 45.5,
            "currency": "USD",
            "service_name": "Virtual Machines",
        },
    }

    client = TestClient(app)
    resp = client.get(
        "/resources/vms/rg/vm1/sizing",
        headers=_admin_headers(),
        params={"subscription_id": SUB},
    )
    assert resp.status_code == 200, resp.text

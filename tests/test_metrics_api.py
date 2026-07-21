"""Tests for profile-driven metrics API."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.integration_app import app
from app.metrics_api import (
    fetch_metrics_for_resource,
    monitor_profiles_catalog,
    plan_for_resource,
)
from app.user_auth import ROLE_ADMIN, ROLE_VIEWER, create_access_token

VM_RID = (
    "/subscriptions/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    "/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/vm1"
)


from tests.auth_helpers import auth_header as build_auth_header


def _auth_header(role: str) -> dict[str, str]:
    return build_auth_header(
        user_id=f"user-{role}",
        username=f"test-{role}",
        role=role,
    )


def test_plan_for_resource_vm():
    plan = plan_for_resource(VM_RID)
    assert plan["ok"] is True
    assert plan["canonical_type"] == "compute/vm"
    assert any(m["metric_name"] == "Percentage CPU" for m in plan["metrics"])


def test_plan_for_resource_unknown_type():
    rid = "/subscriptions/x/resourceGroups/rg/providers/Microsoft.Unknown/widgets/w1"
    plan = plan_for_resource(rid)
    assert plan["ok"] is False
    assert "profile" in plan["error"].lower()


def test_monitor_profiles_catalog_nonempty():
    catalog = monitor_profiles_catalog()
    assert catalog["count"] > 0
    assert isinstance(catalog["profiles"], list)
    assert catalog["profiles"][0]["canonical_type"]


def test_fetch_metrics_for_resource_rejects_standalone_vmss():
    vmss_rid = (
        "/subscriptions/sub-a/resourceGroups/MC_rg/providers/"
        "Microsoft.Compute/virtualMachineScaleSets/aks-airflow-system-vmss"
    )
    result = fetch_metrics_for_resource(vmss_rid, timespan="P7D")
    assert result["ok"] is False
    assert result["canonical_type"] == "compute/vmss"
    assert "AKS cluster" in result["error"]


@patch("app.azure_resources.AzureResourcesClient")
def test_fetch_metrics_for_resource_success(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.get_resource_metrics.return_value = {
        "value": [{"name": {"value": "Percentage CPU"}, "timeseries": []}],
    }

    result = fetch_metrics_for_resource(VM_RID, timespan="P7D")
    assert result["ok"] is True
    assert result["source"] == "azure"
    assert result["canonical_type"] == "compute/vm"
    assert "Percentage CPU" in result["metric_names"]
    assert isinstance(result.get("metrics_summary"), list)
    mock_client.get_resource_metrics.assert_called_once()


def test_metrics_resource_auto_route_requires_auth():
    client = TestClient(app)
    assert client.get("/metrics/resource/auto", params={"resource_id": VM_RID}).status_code == 401


@patch("app.metrics_api.fetch_metrics_for_resource")
def test_metrics_resource_auto_route_admin(mock_fetch):
    mock_fetch.return_value = {
        "ok": True,
        "source": "azure",
        "resource_id": VM_RID,
        "canonical_type": "compute/vm",
        "facts": {},
        "metrics": {},
    }
    client = TestClient(app)
    admin = _auth_header(ROLE_ADMIN)
    res = client.get("/metrics/resource/auto", params={"resource_id": VM_RID}, headers=admin)
    assert res.status_code == 200
    assert res.json()["canonical_type"] == "compute/vm"


@patch("app.metrics_api.fetch_metrics_for_resource")
def test_metrics_resource_auto_route_authenticated(mock_fetch):
    mock_fetch.return_value = {
        "ok": True,
        "source": "azure",
        "resource_id": VM_RID,
        "canonical_type": "compute/vm",
        "facts": {},
        "metrics": [],
        "data_quality": "azure_monitor",
    }
    client = TestClient(app)
    viewer = _auth_header(ROLE_VIEWER)
    res = client.get("/metrics/resource/auto", params={"resource_id": VM_RID}, headers=viewer)
    assert res.status_code == 200
    assert res.json()["canonical_type"] == "compute/vm"


@patch("app.metrics_api.fetch_metrics_for_resource")
def test_azure_metrics_resource_auto_admin(mock_fetch):
    mock_fetch.return_value = {
        "ok": True,
        "source": "azure",
        "resource_id": VM_RID,
        "canonical_type": "compute/vm",
        "facts": {"avg_cpu_pct": 12.5},
        "metrics": {},
    }
    client = TestClient(app)
    admin = _auth_header(ROLE_ADMIN)
    res = client.get("/azure/metrics/resource/auto", params={"resource_id": VM_RID}, headers=admin)
    assert res.status_code == 200
    body = res.json()
    assert body["canonical_type"] == "compute/vm"
    assert body["facts"]["avg_cpu_pct"] == 12.5


def test_inventory_baseline_response_with_synced_row():
    from app.metrics_api import _inventory_baseline_response

    rid = (
        "/subscriptions/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        "/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip1"
    )
    db = MagicMock()
    with patch("app.metrics_api._load_inventory_row") as mock_row:
        mock_row.return_value = {
            "id": rid,
            "type": "network/publicip",
            "name": "pip1",
            "location": "eastus",
            "resourceGroup": "rg",
            "state": "Associated",
            "properties": {"publicIPAllocationMethod": "Static", "sku": {"name": "Standard"}},
            "monthlyCostUsd": 12.5,
        }
        result = _inventory_baseline_response(db, rid, timespan="P7D")

    assert result["ok"] is True
    assert result["inventory_properties"]
    assert result["cost_driver_mapping"]["cost_drivers"]
    assert result["facts"].get("monthly_cost_usd") == 12.5


def test_format_fact_display_value_available_memory_bytes():
    from app.resources.types import format_fact_display_value

    assert format_fact_display_value("avg_available_memory_bytes", 62_262_717_653.0656) == "57.99 GB"


def test_inventory_properties_format_memory_bytes():
    from app.metrics_api import _inventory_properties_from_facts

    props = _inventory_properties_from_facts(
        {"avg_available_memory_bytes": 62_262_717_653.0656, "avg_cpu_pct": 12.4},
        "compute/vm",
    )
    memory = next(p for p in props if p["fact_key"] == "avg_available_memory_bytes")
    cpu = next(p for p in props if p["fact_key"] == "avg_cpu_pct")
    assert memory["formatted"] == "57.99 GB"
    assert memory["unit"] == "bytes"
    assert cpu["formatted"] == "12.4%"


def test_inventory_properties_from_facts_skips_meta():
    from app.metrics_api import _inventory_properties_from_facts
    props = _inventory_properties_from_facts(
        {
            "data_source": "synced_inventory",
            "sku": "Standard_D2s_v5",
            "disk_size_gb": 128,
        },
        "compute/vm",
    )
    keys = {p["fact_key"] for p in props}
    assert "data_source" not in keys
    assert "sku" in keys
    assert props[0]["formatted"]


def test_inventory_properties_shorten_arm_resource_ids():
    from app.metrics_api import _inventory_properties_from_facts

    disk_id = (
        "/subscriptions/93ca908b-5732-440d-b712-f6d7951951c0/resourceGroups/"
        "MC_ziov2rg1eu2_ziov2rg1eu2_eastus2/providers/Microsoft.Compute/disks/cso-54802-pgcore"
    )
    props = _inventory_properties_from_facts(
        {"source_disk_id": disk_id},
        "compute/snapshot",
    )
    row = next(p for p in props if p["fact_key"] == "source_disk_id")
    assert row["label"] == "Source disk"
    assert row["formatted"] == "cso-54802-pgcore"
    assert row["value"] == disk_id


def test_openapi_includes_metrics_api_paths():
    client = TestClient(app)
    admin = _auth_header(ROLE_ADMIN)
    schema = client.get("/openapi.json", headers=admin).json()
    assert "/api/azure/metrics/resource/auto" in schema["paths"]
    assert "/api/azure/metrics/subscription" in schema["paths"]
    tag_names = {t["name"] for t in schema["tags"]}
    assert "Metrics API" in tag_names

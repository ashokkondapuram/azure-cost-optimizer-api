"""Tests for /azure/* live ARM routes."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app, resource_client
from app.user_auth import ROLE_ADMIN, ROLE_VIEWER
from tests.auth_helpers import auth_header as build_auth_header


def _auth_header(role: str) -> dict[str, str]:
    return build_auth_header(
        user_id=f"user-{role}",
        username=f"test-{role}",
        role=role,
    )


def test_azure_subscriptions_requires_admin():
    client = TestClient(app)
    assert client.get("/azure/subscriptions").status_code == 401
    viewer = _auth_header(ROLE_VIEWER)
    assert client.get("/azure/subscriptions", headers=viewer).status_code == 403


@patch.object(resource_client, "list_subscriptions")
def test_azure_subscriptions_returns_live_source(mock_list_subs):
    mock_list_subs.return_value = [
        {"subscriptionId": "sub-1", "displayName": "Prod"},
    ]
    client = TestClient(app)
    admin = _auth_header(ROLE_ADMIN)
    res = client.get("/azure/subscriptions", headers=admin)
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "azure"
    assert body["count"] == 1
    assert body["value"][0]["subscriptionId"] == "sub-1"


def test_openapi_includes_arm_paths_and_proxy_config():
    client = TestClient(app)
    admin = _auth_header(ROLE_ADMIN)
    schema = client.get("/openapi.json", headers=admin).json()
    assert "/subscriptions" in schema["paths"]
    assert "/subscriptions/{subscriptionId}/providers/Microsoft.Compute/virtualMachines" in schema["paths"]
    assert schema["servers"][0]["url"] == ""
    assert "routes" in schema["x-proxy-config"]


@patch("app.azure_live_api.fetch_live_resources")
def test_azure_vms_wraps_live_response(mock_fetch):
    mock_fetch.return_value = [{"name": "vm-1"}]
    client = TestClient(app)
    admin = _auth_header(ROLE_ADMIN)
    res = client.get(
        "/azure/vms",
        headers=admin,
        params={"subscription_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "azure"
    assert body["subscription_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert body["count"] == 1

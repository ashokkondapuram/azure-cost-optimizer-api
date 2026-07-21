"""Azure ARM OpenAPI schema tests."""

from fastapi.testclient import TestClient

from app.azure_arm_openapi import build_azure_arm_openapi_schema
from app.integration_app import app
from app.user_auth import ROLE_ADMIN
from tests.auth_helpers import auth_header


def test_arm_openapi_uses_proxied_server():
    schema = build_azure_arm_openapi_schema()
    assert schema["servers"][0]["url"] == ""
    assert "management.azure.com" in schema["servers"][0]["description"]
    assert schema["info"]["title"] == "Azure Resource Manager"
    assert "/subscriptions/{subscriptionId}/providers/Microsoft.Compute/virtualMachines" in schema["paths"]
    assert "x-proxy-config" in schema


def test_openapi_json_matches_arm_schema():
    client = TestClient(app)
    headers = auth_header(user_id="admin-openapi", username="admin-openapi", role=ROLE_ADMIN)
    res = client.get("/openapi.json", headers=headers)
    assert res.status_code == 200
    schema = res.json()
    assert schema["servers"][0]["url"] == ""
    assert "/resources/vms" not in schema["paths"]
    assert schema["paths"]["/subscriptions"]["get"]["tags"] == ["Azure Resource Manager"]

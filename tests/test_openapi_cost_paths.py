"""OpenAPI schema includes Cost Management app APIs."""

from fastapi.testclient import TestClient

from app.integration_app import app
from app.openapi_config import merge_cost_management_paths
from app.user_auth import ROLE_ADMIN
from tests.auth_helpers import auth_header


def test_merge_cost_management_paths_maps_to_api_prefix():
    arm = {"paths": {"/subscriptions": {"get": {}}}, "tags": [], "info": {"description": "ARM"}}
    native = {
        "paths": {
            "/costs/explorer": {"get": {"tags": ["Cost Management"], "summary": "Explorer bundle"}},
            "/costs/sync": {"post": {"tags": ["Cost Management"], "summary": "Sync costs"}},
            "/health/live": {"get": {"tags": ["Health"]}},
        },
        "tags": [{"name": "Cost Management", "description": "Costs"}],
        "components": {"schemas": {"HTTPValidationError": {"type": "object"}}},
    }
    merged = merge_cost_management_paths(arm, native)
    assert "/api/costs/explorer" in merged["paths"]
    assert "/api/costs/sync" in merged["paths"]
    assert "/health/live" not in merged["paths"]
    assert "/subscriptions" in merged["paths"]
    assert any(t["name"] == "Cost Management" for t in merged["tags"])
    assert "HTTPValidationError" in merged["components"]["schemas"]


def test_openapi_includes_cost_management_paths():
    client = TestClient(app)
    admin = auth_header(
        user_id="admin-cost-openapi",
        username="test-admin-cost-openapi",
        role=ROLE_ADMIN,
    )
    res = client.get("/openapi.json", headers=admin)
    assert res.status_code == 200, res.text
    schema = res.json()

    expected = (
        "/api/costs/explorer",
        "/api/costs",
        "/api/costs/summary",
        "/api/costs/by-service",
        "/api/costs/sync",
        "/api/costs/timeframes",
    )
    for path in expected:
        assert path in schema["paths"], f"missing {path}"

    tag_names = {t["name"] for t in schema["tags"]}
    assert "Cost Management" in tag_names
    assert "Cost Management" in schema["info"]["description"]

    explorer_get = schema["paths"]["/api/costs/explorer"]["get"]
    assert explorer_get["tags"] == ["Cost Management"]
    param_names = {p["name"] for p in explorer_get.get("parameters", [])}
    assert "subscription_id" in param_names
    assert "prefer_live" in param_names

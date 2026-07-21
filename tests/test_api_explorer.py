"""OpenAPI and API explorer tests."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api_explorer import build_api_explorer_context, resolve_explorer_subscription_id
from app.integration_app import app
from app.user_auth import ROLE_ADMIN, ROLE_VIEWER, create_access_token


from tests.auth_helpers import auth_header as build_auth_header


def _auth_header(role: str) -> dict[str, str]:
    return build_auth_header(
        user_id=f"user-{role}",
        username=f"test-{role}",
        role=role,
    )


@patch("app.services.system_settings.get_effective_config")
@patch("app.subscription_store._default_subscription_from_settings")
@patch("app.subscription_store.list_subscriptions_db")
def test_resolve_explorer_subscription_prefers_default_setting(mock_list, mock_default, mock_cfg):
    mock_cfg.return_value = {"auth_mode": "managed_identity"}
    mock_default.return_value = "aaa-bbb-ccc"
    mock_list.return_value = [
        {"subscriptionId": "aaa-bbb-ccc", "displayName": "Production", "state": "Enabled"},
    ]
    db = MagicMock()
    result = resolve_explorer_subscription_id(db)
    assert result["subscription_id"] == "aaa-bbb-ccc"
    assert result["display_name"] == "Production"
    assert result["source"] == "default_subscription_id"


@patch("app.services.system_settings.get_effective_config", return_value={"auth_mode": "managed_identity"})
@patch("app.subscription_store._default_subscription_from_settings", return_value=None)
@patch("app.subscription_store.list_subscriptions_db")
def test_resolve_explorer_subscription_uses_cache(mock_list, _mock_default, _mock_cfg):
    mock_list.return_value = [
        {"subscriptionId": "ddd-eee-fff", "displayName": "Dev", "state": "Enabled"},
    ]
    db = MagicMock()
    result = resolve_explorer_subscription_id(db)
    assert result["subscription_id"] == "ddd-eee-fff"
    assert result["source"] == "subscription_cache"


def test_api_explorer_context_includes_subscription_fields():
    client = TestClient(app)
    admin = _auth_header(ROLE_ADMIN)
    res = client.get("/admin/api-explorer/context", headers=admin)
    assert res.status_code == 200
    body = res.json()
    assert "subscription_id" in body
    assert "subscription" in body
    assert "subscriptions" in body
    assert body["hints"]["subscription_id"].startswith("subscriptionId is prefilled")


def test_build_api_explorer_context_shape():
    db = MagicMock()
    with patch("app.api_explorer.get_token_cache_status", return_value={"cached": False}), \
         patch("app.api_explorer.resolve_explorer_subscription_id", return_value={
             "subscription_id": "sub-1",
             "display_name": "Sub One",
             "source": "managed_identity",
             "auth_mode": "managed_identity",
         }), \
         patch("app.subscription_store.list_subscriptions_db", return_value=[]):
        ctx = build_api_explorer_context(db)
    assert ctx["subscription_id"] == "sub-1"
    assert ctx["subscription"]["source"] == "managed_identity"


def test_openapi_requires_authentication():
    client = TestClient(app)
    assert client.get("/openapi.json").status_code == 401
    assert client.get("/api/openapi.json").status_code == 401


def test_openapi_requires_admin_role():
    client = TestClient(app)
    viewer = _auth_header(ROLE_VIEWER)
    assert client.get("/openapi.json", headers=viewer).status_code == 403
    assert client.get("/api/openapi.json", headers=viewer).status_code == 403


def test_openapi_available_to_admin():
    client = TestClient(app)
    admin = _auth_header(ROLE_ADMIN)
    res = client.get("/openapi.json", headers=admin)
    assert res.status_code == 200
    schema = res.json()
    assert schema["info"]["title"] == "Azure Resource Manager"
    assert schema["servers"][0]["url"] == ""
    assert "management.azure.com" in schema["servers"][0]["description"]
    assert "BearerAuth" in schema["components"]["securitySchemes"]
    assert "/resources/vms" not in schema["paths"]
    assert "/subscriptions/{subscriptionId}/providers/Microsoft.Compute/virtualMachines" in schema["paths"]
    tag_names = [t["name"] for t in schema["tags"]]
    assert "Azure Resource Manager" in tag_names
    assert "x-proxy-config" in schema

    mirrored = client.get("/api/openapi.json", headers=admin)
    assert mirrored.status_code == 200


def test_swagger_ui_requires_admin():
    client = TestClient(app)
    assert client.get("/docs").status_code == 401
    viewer = _auth_header(ROLE_VIEWER)
    assert client.get("/docs", headers=viewer).status_code == 403
    admin = _auth_header(ROLE_ADMIN)
    assert client.get("/docs", headers=admin).status_code == 200


def test_api_explorer_context_requires_auth():
    client = TestClient(app)
    res = client.get("/admin/api-explorer/context")
    assert res.status_code == 401


def test_api_explorer_context_requires_admin():
    client = TestClient(app)
    viewer = _auth_header(ROLE_VIEWER)
    assert client.get("/admin/api-explorer/context", headers=viewer).status_code == 403

"""Tests for subscription validate/add API."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.integration_app import app
from app.user_auth import ROLE_ADMIN, ROLE_VIEWER
from tests.auth_helpers import auth_header as build_auth_header

SUB_A = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _auth_header(role: str) -> dict[str, str]:
    return build_auth_header(
        user_id=f"user-{role}",
        username=f"test-{role}",
        role=role,
    )


@patch("app.services.subscription_validation.validate_subscription_access")
def test_validate_subscription_requires_admin(mock_validate):
    mock_validate.return_value = {"connected": True, "subscription_id": SUB_A}
    client = TestClient(app)
    assert client.post(
        "/resources/subscriptions/validate",
        json={"subscription_id": SUB_A},
    ).status_code == 401

    viewer = _auth_header(ROLE_VIEWER)
    assert client.post(
        "/resources/subscriptions/validate",
        json={"subscription_id": SUB_A},
        headers=viewer,
    ).status_code == 403


@patch("app.services.subscription_validation.validate_subscription_access")
def test_validate_subscription_returns_structured_result(mock_validate):
    mock_validate.return_value = {
        "connected": True,
        "subscription_id": SUB_A,
        "display_name": "Production",
        "state": "Enabled",
        "tenant_id": "tenant-1",
        "auth_mode": "service_principal",
        "message": "Your Service principal can access Production.",
        "error_code": None,
    }
    client = TestClient(app)
    admin = _auth_header(ROLE_ADMIN)
    res = client.post(
        "/resources/subscriptions/validate",
        json={"subscription_id": SUB_A},
        headers=admin,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["connected"] is True
    assert body["display_name"] == "Production"
    assert body["auth_mode"] == "service_principal"


def test_validate_subscription_rejects_invalid_guid():
    client = TestClient(app)
    admin = _auth_header(ROLE_ADMIN)
    res = client.post(
        "/resources/subscriptions/validate",
        json={"subscription_id": "not-a-guid"},
        headers=admin,
    )
    assert res.status_code == 422


@patch("app.auth.reload_credential")
@patch("app.services.system_settings.save_category_settings")
@patch("app.subscription_store.upsert_subscription_cache")
@patch("app.subscription_store.subscriptions_list_payload")
@patch("app.services.subscription_validation.validate_subscription_access")
def test_add_subscription_persists_cache(
    mock_validate,
    mock_payload,
    mock_upsert,
    mock_save,
    _mock_reload,
):
    mock_validate.return_value = {
        "connected": True,
        "subscription_id": SUB_A,
        "display_name": "Production",
        "state": "Enabled",
        "tenant_id": "tenant-1",
        "auth_mode": "service_principal",
        "message": "ok",
        "error_code": None,
    }
    mock_payload.return_value = {
        "subscriptions": [{"subscriptionId": SUB_A, "displayName": "Production"}],
        "default_subscription_id": SUB_A,
    }

    client = TestClient(app)
    admin = _auth_header(ROLE_ADMIN)
    res = client.post(
        "/resources/subscriptions",
        json={
            "subscription_id": SUB_A,
            "display_name": "Production",
            "set_as_default": True,
        },
        headers=admin,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["subscription_id"] == SUB_A
    mock_upsert.assert_called_once()
    mock_save.assert_called_once()


@patch("app.services.subscription_validation.validate_subscription_access")
def test_add_subscription_rejects_failed_validation(mock_validate):
    mock_validate.return_value = {
        "connected": False,
        "subscription_id": SUB_A,
        "message": "Your Service principal does not have access to this subscription.",
        "error_code": "forbidden",
        "auth_mode": "service_principal",
    }
    client = TestClient(app)
    admin = _auth_header(ROLE_ADMIN)
    res = client.post(
        "/resources/subscriptions",
        json={"subscription_id": SUB_A},
        headers=admin,
    )
    assert res.status_code == 403
    assert "does not have access" in res.json()["detail"]


@patch("app.services.subscription_validation.az_cli_available", return_value=False)
@patch("app.services.subscription_validation.auth_headers", return_value={"Authorization": "Bearer test"})
@patch("app.services.subscription_validation._get")
@patch("app.services.subscription_validation.get_effective_config")
@patch("app.services.subscription_validation.get_token", return_value="token")
@patch("app.services.subscription_validation.arm_auth_context")
def test_validate_subscription_access_success(mock_ctx, _mock_token, mock_cfg, _mock_get, _mock_headers, _mock_az):
    mock_cfg.return_value = {
        "auth_mode": "managed_identity",
        "tenant_id": "tenant-1",
    }
    mock_ctx.return_value.__enter__ = MagicMock(return_value=None)
    mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
    _mock_get.return_value = {
        "subscriptionId": SUB_A,
        "displayName": "Production",
        "state": "Enabled",
        "tenantId": "tenant-1",
    }

    from app.services.subscription_validation import validate_subscription_access

    result = validate_subscription_access(MagicMock(), SUB_A)
    assert result["connected"] is True
    assert result["valid"] is True
    assert result["display_name"] == "Production"
    assert result["error_code"] is None
    assert result["validation_method"] == "arm_api"


@patch("app.services.subscription_validation.az_cli_available", return_value=False)
@patch("app.services.subscription_validation.auth_headers", return_value={"Authorization": "Bearer test"})
@patch("app.services.subscription_validation._get")
@patch("app.services.subscription_validation.get_effective_config")
@patch("app.services.subscription_validation.get_token", return_value="token")
@patch("app.services.subscription_validation.arm_auth_context")
def test_validate_subscription_access_tenant_mismatch(mock_ctx, _mock_token, mock_cfg, mock_get, _mock_headers, _mock_az):
    mock_cfg.return_value = {
        "auth_mode": "managed_identity",
        "tenant_id": "configured-tenant",
    }
    mock_ctx.return_value.__enter__ = MagicMock(return_value=None)
    mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
    mock_get.return_value = {
        "subscriptionId": SUB_A,
        "displayName": "Production",
        "state": "Enabled",
        "tenantId": "other-tenant",
    }

    from app.services.subscription_validation import validate_subscription_access

    result = validate_subscription_access(MagicMock(), SUB_A)
    assert result["connected"] is False
    assert result["error_code"] == "tenant_mismatch"


@patch("app.services.subscription_validation.validate_subscription_access")
def test_add_subscription_rejects_forbidden_with_403(mock_validate):
    mock_validate.return_value = {
        "connected": False,
        "valid": False,
        "subscription_id": SUB_A,
        "message": "Your Service principal does not have access to this subscription.",
        "error": "Your Service principal does not have access to this subscription.",
        "error_code": "forbidden",
        "auth_mode": "service_principal",
    }
    client = TestClient(app)
    admin = _auth_header(ROLE_ADMIN)
    res = client.post(
        "/resources/subscriptions",
        json={"subscription_id": SUB_A},
        headers=admin,
    )
    assert res.status_code == 403


@patch("app.services.subscription_validation.az_cli_available", return_value=True)
@patch("app.services.subscription_azure_cli.run_az")
@patch("app.services.subscription_validation.get_effective_config")
def test_validate_subscription_access_via_azure_cli(mock_cfg, mock_run_az, _mock_az_available):
    import json

    from app.services.subscription_validation import validate_subscription_access

    mock_cfg.return_value = {
        "auth_mode": "service_principal",
        "tenant_id": "tenant-1",
        "client_id": "client-1",
        "client_secret": "secret-1",
    }
    mock_run_az.side_effect = [
        (0, "", ""),  # az login
        (
            0,
            json.dumps(
                {
                    "id": SUB_A,
                    "name": "Production",
                    "tenantId": "tenant-1",
                    "state": "Enabled",
                }
            ),
            "",
        ),
    ]

    result = validate_subscription_access(MagicMock(), SUB_A)
    assert result["valid"] is True
    assert result["connected"] is True
    assert result["validation_method"] == "azure_cli"
    assert result["display_name"] == "Production"
    assert mock_run_az.call_count == 2


@patch("app.services.subscription_validation.az_cli_available", return_value=True)
@patch("app.services.subscription_azure_cli.run_az")
@patch("app.services.subscription_validation.get_effective_config")
def test_validate_subscription_access_cli_forbidden(mock_cfg, mock_run_az, _mock_az_available):
    from app.services.subscription_validation import validate_subscription_access

    mock_cfg.return_value = {
        "auth_mode": "service_principal",
        "tenant_id": "tenant-1",
        "client_id": "client-1",
        "client_secret": "secret-1",
    }
    mock_run_az.side_effect = [
        (0, "", ""),
        (1, "", "AuthorizationFailed: does not have authorization"),
    ]

    result = validate_subscription_access(MagicMock(), SUB_A)
    assert result["valid"] is False
    assert result["error_code"] == "forbidden"


@patch("app.services.subscription_validation.az_cli_available", return_value=True)
@patch("app.services.subscription_azure_cli.run_az")
@patch("app.services.subscription_validation.get_effective_config")
def test_add_subscription_saves_after_cli_validation(mock_cfg, mock_run_az, _mock_az_available):
    import json

    from app.database import SessionLocal, init_db
    from app.models import AppUser, SubscriptionCache
    from app.user_auth import ROLE_ADMIN, hash_password

    mock_cfg.return_value = {
        "auth_mode": "service_principal",
        "tenant_id": "tenant-1",
        "client_id": "client-1",
        "client_secret": "secret-1",
    }
    mock_run_az.side_effect = [
        (0, "", ""),
        (
            0,
            json.dumps(
                {
                    "id": SUB_A,
                    "name": "Production",
                    "tenantId": "tenant-1",
                    "state": "Enabled",
                }
            ),
            "",
        ),
    ]

    init_db()
    db = SessionLocal()
    try:
        db.query(SubscriptionCache).filter(SubscriptionCache.subscription_id == SUB_A).delete()
        db.query(AppUser).delete()
        db.commit()
        db.add(
            AppUser(
                id="admin-cli-add",
                username="admin",
                display_name="Administrator",
                password_hash=hash_password("password123"),
                role=ROLE_ADMIN,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    token = login.json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/resources/subscriptions",
        json={"subscription_id": SUB_A, "display_name": "Production", "set_as_default": False},
        headers=admin,
    )
    assert res.status_code == 200, res.text

    verify = SessionLocal()
    try:
        row = verify.query(SubscriptionCache).filter(SubscriptionCache.subscription_id == SUB_A).first()
        assert row is not None
        assert row.display_name == "Production"
        from app.subscription_store import registered_subscription_ids

        assert SUB_A in registered_subscription_ids(verify)
    finally:
        verify.close()


@patch("app.auth.reload_credential")
@patch("app.services.subscription_validation.validate_subscription_access")
def test_add_subscription_persists_subscription_cache_row(mock_validate, _mock_reload):
    from app.database import SessionLocal, init_db
    from app.models import AppUser, SubscriptionCache
    from app.user_auth import ROLE_ADMIN, hash_password

    mock_validate.return_value = {
        "connected": True,
        "subscription_id": SUB_A,
        "display_name": "Production",
        "state": "Enabled",
        "tenant_id": "tenant-1",
        "auth_mode": "service_principal",
        "message": "ok",
        "error_code": None,
    }

    init_db()
    db = SessionLocal()
    try:
        db.query(SubscriptionCache).filter(SubscriptionCache.subscription_id == SUB_A).delete()
        db.query(AppUser).delete()
        db.commit()
        db.add(
            AppUser(
                id="admin-sub-add",
                username="admin",
                display_name="Administrator",
                password_hash=hash_password("password123"),
                role=ROLE_ADMIN,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    token = login.json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/resources/subscriptions",
        json={
            "subscription_id": SUB_A,
            "display_name": "Production",
            "set_as_default": False,
        },
        headers=admin,
    )
    assert res.status_code == 200, res.text

    verify = SessionLocal()
    try:
        row = (
            verify.query(SubscriptionCache)
            .filter(SubscriptionCache.subscription_id == SUB_A)
            .first()
        )
        assert row is not None
        assert row.display_name == "Production"
    finally:
        verify.close()

    costs = client.get("/costs", params={"subscription_id": SUB_A}, headers=admin)
    assert costs.status_code == 200, costs.text

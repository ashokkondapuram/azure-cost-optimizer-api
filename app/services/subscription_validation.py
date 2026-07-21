"""Validate credential access to a single Azure subscription (inventory service)."""
from __future__ import annotations

from typing import Any

import structlog

from app.arm_api_versions import SUBSCRIPTIONS_LIST_API_VERSION
from app.auth import arm_auth_context, auth_headers, get_token
from app.http_client import BASE, AzureAPIError, _get
from app.services.subscription_azure_cli import (
    az_cli_available,
    validate_subscription_via_az_cli,
)
from app.services.system_settings import get_effective_config
from app.subscription_store import normalize_arm_subscription
from app.validators import validate_subscription_id

log = structlog.get_logger()

_AUTH_MODE_LABELS = {
    "managed_identity": "Managed identity",
    "service_principal": "Service principal",
    "default_credential": "Default credential",
}


def auth_mode_label(mode: str) -> str:
    return _AUTH_MODE_LABELS.get(mode, mode.replace("_", " ").title())


def _failure(
    base: dict[str, Any],
    *,
    error_code: str,
    message: str,
    validation_method: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    base["error_code"] = error_code
    base["message"] = message
    base["error"] = message
    base["valid"] = False
    base["connected"] = False
    if validation_method:
        base["validation_method"] = validation_method
    base.update(extra)
    return base


def _success(
    base: dict[str, Any],
    *,
    display_name: str,
    state: str,
    tenant_id: str | None,
    validation_method: str,
    auth_mode: str,
) -> dict[str, Any]:
    sid = base["subscription_id"]
    base.update(
        {
            "connected": True,
            "valid": True,
            "display_name": display_name,
            "state": state,
            "tenant_id": tenant_id,
            "validation_method": validation_method,
            "error_code": None,
            "error": None,
            "message": (
                f"Your {auth_mode_label(auth_mode)} can access {display_name} ({sid})."
            ),
        }
    )
    return base


def _missing_sp_fields(azure_cfg: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not (azure_cfg.get("client_id") or "").strip():
        missing.append("client_id")
    if not (azure_cfg.get("client_secret") or "").strip():
        missing.append("client_secret")
    if not (azure_cfg.get("tenant_id") or "").strip():
        missing.append("tenant_id")
    return missing


def _map_arm_error(base: dict[str, Any], exc: AzureAPIError, auth_mode: str) -> dict[str, Any]:
    mode_label = auth_mode_label(auth_mode)
    if exc.status == 401:
        return _failure(
            base,
            error_code="auth_failed",
            message=(
                f"Authentication failed for {mode_label}. "
                "Check your credentials in Settings → Azure connection."
            ),
            validation_method="arm_api",
        )
    if exc.status == 403:
        return _failure(
            base,
            error_code="forbidden",
            message=(
                f"Your {mode_label} does not have access to this subscription. "
                "Assign Reader (or higher) on the subscription in Azure."
            ),
            validation_method="arm_api",
        )
    if exc.status == 404:
        return _failure(
            base,
            error_code="not_found",
            message=(
                "Subscription not found or your credentials cannot see it. "
                "Check the subscription ID and access permissions."
            ),
            validation_method="arm_api",
        )
    return _failure(
        base,
        error_code="azure_error",
        message=f"Azure returned {exc.status}: {exc.message}",
        validation_method="arm_api",
    )


def _validate_via_arm_api(db, sid: str, azure_cfg: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    auth_mode = azure_cfg.get("auth_mode") or "managed_identity"
    configured_tenant = (azure_cfg.get("tenant_id") or "").strip().lower()

    try:
        with arm_auth_context(db=db, token=get_token(db)):
            url = f"{BASE}/subscriptions/{sid}"
            raw = _get(url, auth_headers(db), {"api-version": SUBSCRIPTIONS_LIST_API_VERSION})
    except AzureAPIError as exc:
        return _map_arm_error(base, exc, auth_mode)
    except Exception as exc:
        log.warning("subscription_validation_failed", subscription_id=sid, error=str(exc))
        return _failure(
            base,
            error_code="auth_failed",
            message=f"Could not connect to Azure. {exc}",
            validation_method="arm_api",
        )

    normalized = normalize_arm_subscription(raw) or {}
    display_name = normalized.get("displayName") or sid
    sub_tenant = (normalized.get("tenantId") or "").strip().lower()
    state = normalized.get("state") or "Unknown"

    if configured_tenant and sub_tenant and configured_tenant != sub_tenant:
        return _failure(
            base,
            error_code="tenant_mismatch",
            message=(
                f"Subscription belongs to tenant {sub_tenant}, "
                f"but your configured tenant is {configured_tenant}. "
                "Update the tenant ID in Settings → Azure connection."
            ),
            validation_method="arm_api",
            display_name=display_name,
            state=state,
            tenant_id=sub_tenant or None,
        )

    return _success(
        base,
        display_name=display_name,
        state=state,
        tenant_id=sub_tenant or None,
        validation_method="arm_api",
        auth_mode=auth_mode,
    )


def validate_subscription_access(db, subscription_id: str) -> dict[str, Any]:
    """Validate that configured Azure credentials can access the subscription."""
    sid = validate_subscription_id(subscription_id)
    azure_cfg = get_effective_config(db, "azure")
    auth_mode = azure_cfg.get("auth_mode") or "managed_identity"
    configured_tenant = (azure_cfg.get("tenant_id") or "").strip().lower()

    base: dict[str, Any] = {
        "connected": False,
        "valid": False,
        "subscription_id": sid,
        "display_name": None,
        "state": None,
        "tenant_id": None,
        "auth_mode": auth_mode,
        "message": "",
        "error": None,
        "error_code": None,
        "validation_method": None,
    }

    if auth_mode == "service_principal":
        missing = _missing_sp_fields(azure_cfg)
        if missing:
            return _failure(
                base,
                error_code="creds_missing",
                message=(
                    "Service principal credentials are not configured. "
                    "Set client ID, client secret, and tenant in Settings → Azure connection."
                ),
            )

    if az_cli_available():
        cli_result = validate_subscription_via_az_cli(azure_cfg, sid)
        if cli_result.get("ok"):
            fields = cli_result.get("fields") or {}
            sub_tenant = fields.get("tenant_id")
            if configured_tenant and sub_tenant and configured_tenant != sub_tenant:
                return _failure(
                    base,
                    error_code="tenant_mismatch",
                    message=(
                        f"Subscription belongs to tenant {sub_tenant}, "
                        f"but your configured tenant is {configured_tenant}. "
                        "Update the tenant ID in Settings → Azure connection."
                    ),
                    validation_method="azure_cli",
                    display_name=fields.get("display_name"),
                    state=fields.get("state"),
                    tenant_id=sub_tenant,
                )
            return _success(
                base,
                display_name=fields.get("display_name") or sid,
                state=fields.get("state") or "Unknown",
                tenant_id=sub_tenant,
                validation_method="azure_cli",
                auth_mode=auth_mode,
            )

        error_code = cli_result.get("error_code") or "azure_error"
        if error_code != "cli_unavailable":
            mode_label = auth_mode_label(auth_mode)
            message = cli_result.get("error") or f"{mode_label} could not access this subscription."
            if error_code == "forbidden":
                message = (
                    f"Your {mode_label} does not have access to this subscription. "
                    "Assign Reader (or higher) on the subscription in Azure."
                )
            return _failure(
                base,
                error_code=error_code,
                message=message,
                validation_method="azure_cli",
            )

        log.info("subscription_validation_cli_unavailable_fallback_arm", subscription_id=sid)
    else:
        log.info("subscription_validation_az_cli_missing_fallback_arm", subscription_id=sid)

    return _validate_via_arm_api(db, sid, azure_cfg, base)

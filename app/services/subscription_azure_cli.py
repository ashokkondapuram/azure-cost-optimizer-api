"""Validate subscription access using the Azure CLI (inventory service)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_AZ_TIMEOUT_SEC = 90


def az_cli_available() -> bool:
    return shutil.which("az") is not None


def run_az(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = _AZ_TIMEOUT_SEC,
) -> tuple[int, str, str]:
    """Run `az` subprocess. Returns (returncode, stdout, stderr)."""
    cmd = ["az", *args]
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=proc_env,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _parse_account_json(stdout: str) -> dict[str, Any] | None:
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _account_fields(account: dict[str, Any], subscription_id: str) -> dict[str, Any]:
    sid = (account.get("id") or subscription_id).strip().lower()
    return {
        "subscription_id": sid,
        "display_name": account.get("name") or sid,
        "tenant_id": (account.get("tenantId") or "").strip().lower() or None,
        "state": account.get("state") or "Unknown",
    }


def _login_with_service_principal(azure_cfg: dict[str, Any]) -> tuple[bool, str]:
    client_id = (azure_cfg.get("client_id") or "").strip()
    client_secret = (azure_cfg.get("client_secret") or "").strip()
    tenant_id = (azure_cfg.get("tenant_id") or "").strip()
    if not client_id or not client_secret or not tenant_id:
        return False, "Service principal credentials are incomplete. Set client ID, secret, and tenant in Settings → Azure connection."

    code, _out, err = run_az(
        [
            "login",
            "--service-principal",
            "-u",
            client_id,
            "-p",
            client_secret,
            "--tenant",
            tenant_id,
            "--output",
            "none",
            "--only-show-errors",
        ],
    )
    if code != 0:
        message = (err or _out or "Azure CLI login failed.").strip()
        log.warning("az_sp_login_failed", exit_code=code)
        return False, message
    return True, ""


def _login_for_auth_mode(azure_cfg: dict[str, Any]) -> tuple[bool, str]:
    auth_mode = (azure_cfg.get("auth_mode") or "managed_identity").strip()
    if auth_mode == "service_principal":
        return _login_with_service_principal(azure_cfg)
    if auth_mode == "managed_identity":
        code, _out, err = run_az(["login", "--identity", "--output", "none", "--only-show-errors"])
        if code != 0:
            return False, (err or "Managed identity login failed.").strip()
        return True, ""
    # default_credential — try existing az session first
    code, _out, _err = run_az(["account", "show", "--output", "none"])
    if code == 0:
        return True, ""
    return False, "No active Azure CLI session. Configure service principal credentials or sign in with az login."


def validate_subscription_via_az_cli(
    azure_cfg: dict[str, Any],
    subscription_id: str,
) -> dict[str, Any]:
    """
    Validate subscription access with Azure CLI.

    Returns dict with keys: ok, fields (subscription metadata), error, error_code.
    """
    if not az_cli_available():
        return {
            "ok": False,
            "fields": None,
            "error": "Azure CLI is not installed on this host.",
            "error_code": "cli_unavailable",
        }

    ok_login, login_error = _login_for_auth_mode(azure_cfg)
    if not ok_login:
        return {
            "ok": False,
            "fields": None,
            "error": login_error,
            "error_code": "auth_failed",
        }

    code, out, err = run_az(
        [
            "account",
            "show",
            "--subscription",
            subscription_id,
            "--output",
            "json",
            "--only-show-errors",
        ],
    )
    if code != 0:
        message = (err or out or "Subscription is not accessible with the configured credentials.").strip()
        lowered = message.lower()
        if "authorizationfailed" in lowered or "403" in lowered or "does not have authorization" in lowered:
            error_code = "forbidden"
        elif "not found" in lowered or "subscriptionnotfound" in lowered or "404" in lowered:
            error_code = "not_found"
        else:
            error_code = "azure_error"
        log.warning(
            "az_subscription_show_failed",
            subscription_id=subscription_id,
            exit_code=code,
            error_code=error_code,
        )
        return {
            "ok": False,
            "fields": None,
            "error": message,
            "error_code": error_code,
        }

    account = _parse_account_json(out)
    if not account:
        return {
            "ok": False,
            "fields": None,
            "error": "Azure CLI returned an unexpected response for account show.",
            "error_code": "azure_error",
        }

    return {
        "ok": True,
        "fields": _account_fields(account, subscription_id),
        "error": None,
        "error_code": None,
    }

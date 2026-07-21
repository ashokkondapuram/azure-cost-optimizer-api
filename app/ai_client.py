"""Azure OpenAI client for analysis enrichment."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlparse

import requests
import structlog

log = structlog.get_logger(__name__)

DEFAULT_API_VERSION = "2024-08-01-preview"
DEFAULT_TIMEOUT_SEC = 60
AI_AUTH_API_KEY = "api_key"
AI_AUTH_AZURE_AD = "azure_ad"


def _normalize_endpoint(endpoint: str) -> str:
    text = (endpoint or "").strip().rstrip("/")
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("OpenAI endpoint must start with https://")
    # App settings sometimes include the /openai path segment; chat URL adds it again.
    if text.lower().endswith("/openai"):
        text = text[: -len("/openai")].rstrip("/")
    return text


def _resolve_openai_key(cfg: dict[str, Any]) -> str:
    return (
        (cfg.get("openai_key") or "").strip()
        or (os.getenv("OPENAI_KEY") or "").strip()
        or (os.getenv("OPENAI_API_KEY") or "").strip()
    )


def _resolve_ai_auth_mode(cfg: dict[str, Any], *, has_api_key: bool) -> str:
    explicit = (cfg.get("ai_auth_mode") or "").strip().lower()
    if explicit in {AI_AUTH_API_KEY, AI_AUTH_AZURE_AD}:
        if explicit == AI_AUTH_API_KEY and not has_api_key:
            return AI_AUTH_AZURE_AD
        return explicit
    if has_api_key:
        return AI_AUTH_API_KEY
    env_mode = (os.getenv("AI_AUTH_MODE") or AI_AUTH_AZURE_AD).strip().lower()
    if env_mode not in {AI_AUTH_API_KEY, AI_AUTH_AZURE_AD}:
        env_mode = AI_AUTH_AZURE_AD
    return env_mode


def build_ai_headers(config: dict[str, Any], db: Any | None = None) -> dict[str, str]:
    """Build request headers for Azure OpenAI (API key or Azure AD bearer token)."""
    mode = config.get("ai_auth_mode", AI_AUTH_API_KEY)
    if mode == AI_AUTH_AZURE_AD:
        from app.auth import get_openai_token

        return {
            "Authorization": f"Bearer {get_openai_token(db)}",
            "Content-Type": "application/json",
        }
    return {
        "api-key": (config.get("openai_key") or "").strip(),
        "Content-Type": "application/json",
    }


def build_ai_config(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return usable AI config or None when explicitly disabled or incomplete."""
    cfg = dict(raw or {})
    enabled = cfg.get("ai_enabled")
    if enabled is None:
        enabled = True
    elif isinstance(enabled, str):
        enabled = enabled.lower() not in {"0", "false", "no", "off"}
    if not enabled:
        return None

    endpoint = _normalize_endpoint(cfg.get("openai_endpoint") or os.getenv("OPENAI_ENDPOINT") or "")
    deployment = (cfg.get("openai_deployment") or os.getenv("OPENAI_DEPLOYMENT") or "").strip()
    api_version = (
        cfg.get("openai_api_version")
        or os.getenv("OPENAI_API_VERSION")
        or DEFAULT_API_VERSION
    ).strip()

    if not endpoint or not deployment:
        return None

    key = _resolve_openai_key(cfg)
    auth_mode = _resolve_ai_auth_mode(cfg, has_api_key=bool(key))
    if auth_mode == AI_AUTH_API_KEY and not key:
        return None

    max_findings = cfg.get("ai_max_findings_per_run", 200)
    try:
        max_findings = max(1, min(200, int(max_findings)))
    except (TypeError, ValueError):
        max_findings = 200

    enrich_all = cfg.get("ai_enrich_all_findings", True)
    if isinstance(enrich_all, str):
        enrich_all = enrich_all.lower() not in {"0", "false", "no", "off"}

    batch_size = cfg.get("ai_batch_size", 10)
    try:
        batch_size = max(1, min(25, int(batch_size)))
    except (TypeError, ValueError):
        batch_size = 10

    built: dict[str, Any] = {
        "openai_endpoint": endpoint,
        "openai_deployment": deployment,
        "openai_api_version": api_version,
        "ai_auth_mode": auth_mode,
        "ai_max_findings_per_run": max_findings,
        "ai_enrich_all_findings": enrich_all,
        "ai_batch_size": batch_size,
    }
    if auth_mode == AI_AUTH_API_KEY:
        built["openai_key"] = key
    return built


def _failure_message(config: dict[str, Any], status: int) -> str:
    mode = config.get("ai_auth_mode", AI_AUTH_API_KEY)
    if status == 401:
        if mode == AI_AUTH_AZURE_AD:
            return (
                "Azure OpenAI returned 401. Assign Cognitive Services OpenAI User "
                "(or Contributor) on the OpenAI resource to the app identity configured under Azure settings."
            )
        return (
            "Azure OpenAI returned 401. Verify the API key matches this endpoint and deployment, "
            "or switch authentication to Azure AD if keys are disabled on the resource."
        )
    return "Azure OpenAI request failed. Check endpoint, deployment, API version, and credentials."


def chat_completion(
    config: dict[str, Any],
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    json_mode: bool = True,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    db: Any | None = None,
) -> str | None:
    """Call Azure OpenAI chat completions. Returns assistant message content."""
    endpoint = config["openai_endpoint"]
    deployment = config["openai_deployment"]
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions"
    body: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    auth_mode = config.get("ai_auth_mode", AI_AUTH_API_KEY)
    try:
        resp = requests.post(
            url,
            params={"api-version": config["openai_api_version"]},
            headers=build_ai_headers(config, db=db),
            json=body,
            timeout=timeout_sec,
        )
        if resp.status_code >= 400:
            log.warning(
                "ai.request_failed",
                status=resp.status_code,
                auth_mode=auth_mode,
                endpoint=endpoint,
                deployment=deployment,
                api_version=config.get("openai_api_version"),
                body=resp.text[:500],
            )
            return None
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        return (choices[0].get("message") or {}).get("content")
    except Exception as exc:
        log.warning("ai.request_error", auth_mode=auth_mode, error=str(exc))
        return None


def verify_ai_connection(config: dict[str, Any], db: Any | None = None) -> dict[str, Any]:
    """Validate Azure OpenAI settings with a minimal prompt."""
    built = build_ai_config({**config, "ai_enabled": True})
    if not built:
        return {
            "ok": False,
            "message": "AI is not configured. Enable AI and provide endpoint and deployment name.",
        }
    content = chat_completion(
        built,
        [
            {"role": "system", "content": "Reply with JSON only."},
            {"role": "user", "content": '{"status":"ok"}'},
        ],
        max_tokens=32,
        json_mode=True,
        timeout_sec=30,
        db=db,
    )
    if not content:
        return {
            "ok": False,
            "message": _failure_message(built, 401),
        }
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = {}
    auth_label = "Azure AD" if built.get("ai_auth_mode") == AI_AUTH_AZURE_AD else "API key"
    if payload.get("status") == "ok" or content:
        return {
            "ok": True,
            "message": (
                f"Connected to deployment '{built['openai_deployment']}' "
                f"using {auth_label} authentication."
            ),
        }
    return {"ok": False, "message": "Azure OpenAI responded but the test payload was unexpected."}

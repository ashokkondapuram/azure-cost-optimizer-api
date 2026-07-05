"""Tests for Azure OpenAI client configuration and validation."""

import pytest
from unittest.mock import patch, MagicMock

from app.ai_client import (
    DEFAULT_API_VERSION,
    build_ai_config,
    chat_completion,
    verify_ai_connection,
)


def test_build_ai_config_disabled():
    assert build_ai_config({"ai_enabled": False}) is None


def test_build_ai_config_defaults_enabled_when_credentials_present():
    cfg = build_ai_config({
        "openai_key": "secret",
        "openai_endpoint": "https://example.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
    })
    assert cfg is not None
    assert cfg["ai_enrich_all_findings"] is True
    assert cfg["ai_max_findings_per_run"] == 200
    assert cfg["ai_batch_size"] == 10


def test_build_ai_config_missing_key_uses_azure_ad():
    cfg = build_ai_config({
        "ai_enabled": True,
        "openai_endpoint": "https://example.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
    })
    assert cfg is not None
    assert cfg["ai_auth_mode"] == "azure_ad"
    assert "openai_key" not in cfg


def test_build_ai_config_complete():
    cfg = build_ai_config({
        "ai_enabled": True,
        "openai_key": "secret",
        "openai_endpoint": "https://example.openai.azure.com/",
        "openai_deployment": "gpt-4o-mini",
        "openai_api_version": "2024-02-15-preview",
        "ai_max_findings_per_run": 25,
    })
    assert cfg is not None
    assert cfg["openai_endpoint"] == "https://example.openai.azure.com"
    assert cfg["openai_deployment"] == "gpt-4o-mini"
    assert cfg["openai_api_version"] == "2024-02-15-preview"
    assert cfg["ai_max_findings_per_run"] == 25


def test_build_ai_config_string_enabled_flag():
    cfg = build_ai_config({
        "ai_enabled": "true",
        "openai_key": "k",
        "openai_endpoint": "https://x.openai.azure.com",
        "openai_deployment": "d",
    })
    assert cfg is not None


def test_build_ai_config_invalid_endpoint():
    with pytest.raises(ValueError):
        build_ai_config({
            "ai_enabled": True,
            "openai_key": "k",
            "openai_endpoint": "not-a-url",
            "openai_deployment": "d",
        })


def test_build_ai_config_clamps_max_findings():
    cfg = build_ai_config({
        "ai_enabled": True,
        "openai_key": "k",
        "openai_endpoint": "https://x.openai.azure.com",
        "openai_deployment": "d",
        "ai_max_findings_per_run": 9999,
    })
    assert cfg["ai_max_findings_per_run"] == 200


def test_build_ai_config_from_openai_key_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_KEY", "from-app-settings")
    cfg = build_ai_config({
        "ai_enabled": True,
        "openai_endpoint": "https://x.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
    })
    assert cfg is not None
    assert cfg["openai_key"] == "from-app-settings"


def test_normalize_endpoint_strips_openai_suffix():
    cfg = build_ai_config({
        "ai_enabled": True,
        "openai_key": "k",
        "openai_endpoint": "https://x.openai.azure.com/openai/",
        "openai_deployment": "d",
    })
    assert cfg["openai_endpoint"] == "https://x.openai.azure.com"


@patch("app.ai_client.requests.post")
def test_chat_completion_azure_ad(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '{"ok": true}'}}],
    }
    mock_post.return_value = mock_resp

    cfg = build_ai_config({
        "ai_enabled": True,
        "ai_auth_mode": "azure_ad",
        "openai_endpoint": "https://x.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
    })
    with patch("app.auth.get_openai_token", return_value="aad-token"):
        content = chat_completion(cfg, [{"role": "user", "content": "hi"}])
    assert content == '{"ok": true}'
    assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer aad-token"


@patch("app.ai_client.requests.post")
def test_chat_completion_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '{"ok": true}'}}],
    }
    mock_post.return_value = mock_resp

    cfg = build_ai_config({
        "ai_enabled": True,
        "ai_auth_mode": "api_key",
        "openai_key": "k",
        "openai_endpoint": "https://x.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
        "openai_api_version": DEFAULT_API_VERSION,
    })
    content = chat_completion(cfg, [{"role": "user", "content": "hi"}])
    assert content == '{"ok": true}'
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["api-key"] == "k"
    assert call_kwargs["params"]["api-version"] == cfg["openai_api_version"]


@patch("app.ai_client.requests.post")
def test_chat_completion_http_error(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_post.return_value = mock_resp

    cfg = build_ai_config({
        "ai_enabled": True,
        "ai_auth_mode": "api_key",
        "openai_key": "bad",
        "openai_endpoint": "https://x.openai.azure.com",
        "openai_deployment": "d",
    })
    assert chat_completion(cfg, [{"role": "user", "content": "hi"}]) is None


@patch("app.ai_client.chat_completion", return_value='{"status":"ok"}')
def test_verify_ai_connection_ok(mock_chat):
    result = verify_ai_connection({
        "ai_enabled": True,
        "openai_key": "k",
        "openai_endpoint": "https://x.openai.azure.com",
        "openai_deployment": "gpt-4o-mini",
    })
    assert result["ok"] is True

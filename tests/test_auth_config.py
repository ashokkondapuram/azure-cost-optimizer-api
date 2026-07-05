"""Production auth configuration validation."""

import os

import pytest

from app.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_validate_startup_requires_jwt_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    settings = get_settings()
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.validate_startup()


def test_validate_startup_allows_production_with_jwt(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    monkeypatch.setenv("JWT_SECRET", "test-secret-value")
    monkeypatch.setenv("K8S_AGENT_TOKEN", "test-k8s-agent-token")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv("AUTH_ENABLED", "true")

    settings = get_settings()
    settings.validate_startup()


def test_jwt_configured_reads_live_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "from-env")

    settings = get_settings()
    assert settings.jwt_configured is True

    monkeypatch.delenv("JWT_SECRET", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.jwt_configured is False

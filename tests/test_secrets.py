"""Settings secret encryption and fallback behavior."""

import pytest
from cryptography.fernet import Fernet

from app.security.secrets import encrypt_value, try_decrypt_value


@pytest.fixture(autouse=True)
def _clear_encryption_env(monkeypatch):
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "development")


def test_jwt_derived_encrypt_roundtrip(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-test-jwt-secret")
    encrypted = encrypt_value("sk-test-key")
    assert encrypted.startswith("enc:")
    plain, err = try_decrypt_value(encrypted)
    assert err is None
    assert plain == "sk-test-key"


def test_decrypt_tries_explicit_then_jwt(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "jwt-a")
    encrypted = encrypt_value("secret-a")

    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    plain, err = try_decrypt_value(encrypted)
    assert plain is None
    assert err

    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("JWT_SECRET", "jwt-a")
    plain, err = try_decrypt_value(encrypted)
    assert err is None
    assert plain == "secret-a"


def test_plaintext_secret_passes_through():
    plain, err = try_decrypt_value("not-encrypted")
    assert err is None
    assert plain == "not-encrypted"

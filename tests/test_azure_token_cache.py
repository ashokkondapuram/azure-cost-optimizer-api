"""Tests for PostgreSQL-backed Azure token cache."""

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import ARM_SCOPE, arm_auth_context, auth_headers, get_token, reload_credential
from app.azure_token_cache import (
    clear_token_cache,
    credential_cache_key,
    read_cached_token,
    write_cached_token,
)
from app.models import AzureTokenCache, Base


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_credential_cache_key_changes_with_secret(db_session):
    base = {"auth_mode": "service_principal", "tenant_id": "t1", "client_id": "c1"}
    k1 = credential_cache_key({**base, "client_secret": "secret-a"}, ARM_SCOPE)
    k2 = credential_cache_key({**base, "client_secret": "secret-b"}, ARM_SCOPE)
    k3 = credential_cache_key({**base, "client_secret": "secret-a"}, ARM_SCOPE)
    assert k1 != k2
    assert k1 == k3


def test_write_and_read_cached_token(db_session):
    config = {"auth_mode": "managed_identity", "client_id": "mi-1"}
    key = credential_cache_key(config, ARM_SCOPE)
    expires = time.time() + 3600

    write_cached_token(
        db_session,
        cache_key=key,
        scope=ARM_SCOPE,
        token="test-access-token",
        expires_on=expires,
    )

    row = db_session.query(AzureTokenCache).filter_by(cache_key=key).one()
    assert row.access_token.startswith("enc:")
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    assert expires_at > datetime.now(timezone.utc)

    cached = read_cached_token(db_session, key)
    assert cached is not None
    token, expires_on = cached
    assert token == "test-access-token"
    assert expires_on > time.time()


def test_expired_token_is_removed_on_read(db_session):
    key = credential_cache_key({"auth_mode": "managed_identity"}, ARM_SCOPE)
    write_cached_token(
        db_session,
        cache_key=key,
        scope=ARM_SCOPE,
        token="expired-token",
        expires_on=time.time() - 10,
    )
    assert read_cached_token(db_session, key) is None
    assert db_session.query(AzureTokenCache).count() == 0


def test_get_token_uses_db_without_calling_azure(db_session):
    config = {"auth_mode": "managed_identity", "client_id": "app-mi"}
    key = credential_cache_key(config, ARM_SCOPE)
    write_cached_token(
        db_session,
        cache_key=key,
        scope=ARM_SCOPE,
        token="cached-arm-token",
        expires_on=time.time() + 7200,
    )

    mock_cred = MagicMock()
    with patch("app.auth.resolve_auth_config", return_value=config), \
         patch("app.auth.get_credential", return_value=mock_cred):
        token = get_token(db_session)

    assert token == "cached-arm-token"
    mock_cred.get_token.assert_not_called()


def test_get_token_fetches_and_persists_when_cache_miss(db_session):
    config = {"auth_mode": "managed_identity"}
    key = credential_cache_key(config, ARM_SCOPE)

    mock_tok = MagicMock()
    mock_tok.token = "fresh-token"
    mock_tok.expires_on = time.time() + 3600
    mock_cred = MagicMock()
    mock_cred.get_token.return_value = mock_tok

    with patch("app.auth.resolve_auth_config", return_value=config), \
         patch("app.auth.get_credential", return_value=mock_cred):
        token = get_token(db_session)

    assert token == "fresh-token"
    mock_cred.get_token.assert_called_once()
    cached = read_cached_token(db_session, key)
    assert cached is not None
    assert cached[0] == "fresh-token"


def test_reload_credential_clears_db_cache(db_session):
    key = credential_cache_key({"auth_mode": "managed_identity"}, ARM_SCOPE)
    write_cached_token(
        db_session,
        cache_key=key,
        scope=ARM_SCOPE,
        token="to-clear",
        expires_on=time.time() + 3600,
    )

    with patch("app.auth.get_credential", return_value=MagicMock()):
        reload_credential(db_session)

    assert db_session.query(AzureTokenCache).count() == 0
    assert clear_token_cache(db_session) == 0


def test_auth_headers_uses_pinned_token_from_context():
    with arm_auth_context(token="pinned-token"):
        headers = auth_headers()
    assert headers["Authorization"] == "Bearer pinned-token"

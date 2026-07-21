"""ARM HTTP client resilience for transient connection failures."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.http_client import AzureAPIError, _get, reset_http_client


@pytest.fixture(autouse=True)
def _clean_client():
    reset_http_client()
    yield
    reset_http_client()


def test_connection_error_resets_client_and_retries(monkeypatch):
    calls = {"n": 0}
    mock_client = MagicMock()

    def fake_request(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadError("Broken pipe")
        resp = MagicMock()
        resp.is_success = True
        resp.status_code = 200
        resp.headers = {}
        resp.json.return_value = {"value": []}
        return resp

    mock_client.request.side_effect = fake_request

    with patch("app.http_client._get_http_client", return_value=mock_client):
        with patch("app.http_client.reset_http_client") as reset_mock:
            with patch("app.http_client.time.sleep"):
                result = _get("https://management.azure.com/test", {"Authorization": "Bearer x"})
    assert result == {"value": []}
    assert calls["n"] == 2
    reset_mock.assert_called_once()


def test_connection_error_raises_after_max_attempts(monkeypatch):
    mock_client = MagicMock()
    mock_client.request.side_effect = httpx.RemoteProtocolError("Connection reset by peer")

    with patch("app.http_client._get_http_client", return_value=mock_client):
        with patch("app.http_client._MAX_ATTEMPTS", 2):
            with patch("app.http_client.time.sleep"):
                with pytest.raises(AzureAPIError) as exc:
                    _get("https://management.azure.com/test", {"Authorization": "Bearer x"})
    assert exc.value.status == 503
    assert exc.value.code == "ConnectionError"

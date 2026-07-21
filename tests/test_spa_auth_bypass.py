"""Browser document navigations must not receive JSON 401 before the SPA loads."""

from fastapi.testclient import TestClient

from app.integration_app import app
from app.user_auth import token_expire_delta


def test_browser_refresh_on_costs_does_not_require_auth_json():
    client = TestClient(app)
    resp = client.get(
        "/costs",
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
        },
    )
    assert resp.status_code != 401, resp.text
    assert "Sign in required" not in resp.text


def test_browser_refresh_on_k8s_does_not_require_auth_json():
    client = TestClient(app)
    resp = client.get(
        "/k8s",
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
        },
    )
    assert resp.status_code != 401, resp.text
    assert "Sign in required" not in resp.text


def test_browser_refresh_on_costs_without_fetch_metadata():
    """Proxies and older browsers may omit Sec-Fetch-* and Accept on refresh."""
    client = TestClient(app)
    resp = client.get("/costs")
    assert resp.status_code != 401, resp.text
    assert "Sign in required" not in resp.text


def test_api_costs_still_requires_auth_without_token():
    client = TestClient(app)
    resp = client.get(
        "/api/costs",
        params={"subscription_id": "00000000-0000-0000-0000-000000000001"},
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Sign in required"


def test_token_expire_default_is_eight_hours(monkeypatch):
    monkeypatch.delenv("JWT_EXPIRE_HOURS", raising=False)
    monkeypatch.delenv("JWT_EXPIRE_MINUTES", raising=False)
    delta = token_expire_delta()
    assert delta.total_seconds() == 8 * 3600

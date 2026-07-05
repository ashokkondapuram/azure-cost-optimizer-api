"""Tests for HTTP cache / ETag middleware."""

from fastapi.testclient import TestClient

from app.http_cache import _should_apply_etag, cache_policy_for_path
from app.main import app


def test_cost_routes_skip_etag_buffering():
    assert _should_apply_etag("/api/costs/explorer", "GET") is False
    assert _should_apply_etag("/costs/explorer", "GET") is False
    assert _should_apply_etag("/api/costs", "GET") is False
    assert _should_apply_etag("/costs/summary", "GET") is False


def test_non_cost_routes_keep_etag():
    assert _should_apply_etag("/api/resources/", "GET") is True
    assert _should_apply_etag("/dashboard/overview", "GET") is True


def test_cost_explorer_still_gets_cache_policy():
    assert cache_policy_for_path("/api/costs/explorer") == "public, max-age=900, stale-while-revalidate=1800"


def test_cost_explorer_returns_json_not_empty_response():
    """Regression: stacked BaseHTTPMiddleware must not drop explorer responses."""
    client = TestClient(app)
    resp = client.get(
        "/api/costs/explorer",
        params={
            "subscription_id": "00000000-0000-0000-0000-000000000001",
            "timeframe": "MonthToDate",
        },
        headers={"Accept": "application/json"},
    )
    assert resp.status_code in {200, 401, 422}, resp.text
    if resp.status_code == 200:
        body = resp.json()
        assert "daily" in body
        assert "summary" in body
        assert "by_service" in body

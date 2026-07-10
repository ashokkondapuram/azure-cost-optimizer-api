"""GET /api/costs/timeframes — public static catalog."""

from fastapi.testclient import TestClient

from app.cost_timeframes import TIMEFRAME_CATALOG
from app.main import app


def test_cost_timeframes_is_public_without_auth():
    client = TestClient(app)
    res = client.get("/api/costs/timeframes")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "timeframes" in body
    assert len(body["timeframes"]) == len(TIMEFRAME_CATALOG)
    assert body["timeframes"][0]["id"] == TIMEFRAME_CATALOG[0]["id"]
    assert res.headers.get("cache-control", "").startswith("public")


def test_cost_timeframes_native_route_matches_api_mirror():
    client = TestClient(app)
    native = client.get("/costs/timeframes")
    mirrored = client.get("/api/costs/timeframes")
    assert native.status_code == 200
    assert mirrored.status_code == 200
    assert native.json() == mirrored.json()

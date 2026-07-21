"""Smoke tests — critical API routes are registered and mirrored under /api."""

from starlette.testclient import TestClient

from app.integration_app import app


def _paths() -> set[str]:
    client = TestClient(app)
    openapi = client.get("/openapi.json")
    if openapi.status_code == 200:
        return set(openapi.json().get("paths", {}).keys())
    # Fallback: hit known routes directly (auth may block but not 404).
    return set()


def test_dashboard_overview_route_exists():
    client = TestClient(app)
    response = client.get(
        "/dashboard/overview",
        params={"subscription_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert response.status_code != 404


def test_dashboard_overview_api_mirror_exists():
    client = TestClient(app)
    response = client.get(
        "/api/dashboard/overview",
        params={"subscription_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert response.status_code != 404


def test_resources_subscriptions_route_exists():
    client = TestClient(app)
    response = client.get("/resources/subscriptions")
    assert response.status_code != 404


def test_resources_counts_route_exists():
    client = TestClient(app)
    response = client.get(
        "/resources/counts",
        params={"subscription_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert response.status_code != 404


def test_idle_resources_sweep_route_exists():
    client = TestClient(app)
    sub = "00000000-0000-0000-0000-000000000001"
    response = client.get(f"/idle-resources/sweep/{sub}")
    assert response.status_code != 404


def test_optimize_trends_route_exists():
    client = TestClient(app)
    response = client.get(
        "/optimize/trends",
        params={"subscription_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert response.status_code != 404


def test_advanced_api_mirrors_exist():
    client = TestClient(app)
    sub = "00000000-0000-0000-0000-000000000001"
    routes = [
        f"/api/idle-resources/sweep/{sub}",
        f"/api/anomalies/daily/{sub}",
        f"/api/savings-planner/estimate/{sub}",
        f"/api/engine/analysis/{sub}/combined",
        f"/api/reservations/advisor/{sub}",
        f"/api/reservations/coverage/{sub}",
        "/api/budgets",
    ]
    for path in routes:
        params = {"subscription_id": sub} if path.endswith("/budgets") else None
        response = client.get(path, params=params)
        assert response.status_code != 404, path

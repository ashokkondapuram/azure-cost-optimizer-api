"""Tests for /api route mirroring used by the React client."""

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.route_mirror import mirror_routes_under_api_prefix


def _methods_for_path(app: FastAPI, path: str) -> set[str]:
    out: set[str] = set()
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path:
            out.update(m.upper() for m in route.methods)
    return out


def test_mirror_registers_all_methods_for_same_path():
    app = FastAPI()

    @app.get("/auth/users")
    def list_users():
        return []

    @app.post("/auth/users")
    def create_user():
        return {"status": "ok"}

    mirror_routes_under_api_prefix(app)

    assert _methods_for_path(app, "/api/auth/users") == {"GET", "POST"}

    client = TestClient(app)
    assert client.get("/api/auth/users").status_code != 405
    assert client.post("/api/auth/users", json={}).status_code != 405


def test_mirror_skips_already_mirrored_method_only():
    app = FastAPI()

    @app.get("/items")
    def list_items():
        return []

    mirror_routes_under_api_prefix(app)

    @app.post("/items")
    def create_item():
        return {"ok": True}

    mirror_routes_under_api_prefix(app)
    assert _methods_for_path(app, "/api/items") == {"GET", "POST"}

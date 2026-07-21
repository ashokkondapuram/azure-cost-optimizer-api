"""Subscription allowlist on data endpoints."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import SessionLocal, get_db, init_db
from app.integration_app import app
from app.models import AppUser, ResourceSnapshot, SubscriptionCache, SystemSetting
from app.user_auth import ROLE_ADMIN, ROLE_VIEWER, hash_password


def _auth_client() -> TestClient:
    init_db()
    db = SessionLocal()
    try:
        db.query(AppUser).delete()
        db.query(ResourceSnapshot).delete()
        db.query(SubscriptionCache).delete()
        db.query(SystemSetting).delete()
        db.commit()
        db.add(
            AppUser(
                id="admin-scope-test",
                username="admin",
                display_name="Administrator",
                password_hash=hash_password("password123"),
                role=ROLE_ADMIN,
                is_active=True,
            )
        )
        db.add(
            ResourceSnapshot(
                id="snap-1",
                subscription_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                resource_id="/subscriptions/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
                resource_name="vm1",
                resource_type="compute/vm",
                resource_group="rg",
                location="eastus",
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    token = login.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_costs_rejects_unknown_subscription():
    client = _auth_client()
    resp = client.get(
        "/costs",
        params={"subscription_id": "00000000-0000-0000-0000-000000000099"},
    )
    assert resp.status_code == 404


def test_costs_allows_synced_subscription():
    client = _auth_client()
    resp = client.get(
        "/costs",
        params={"subscription_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
    )
    assert resp.status_code == 200


def test_cost_history_requires_subscription_id():
    client = _auth_client()
    resp = client.get("/costs/history")
    assert resp.status_code == 422


def test_cost_history_scoped_to_subscription():
    client = _auth_client()
    resp = client.get(
        "/costs/history",
        params={"subscription_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_registered_cache_subscription_allowed():
    client = _auth_client()
    db = SessionLocal()
    try:
        db.add(
            SubscriptionCache(
                subscription_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                display_name="Registered via add flow",
                state="Enabled",
                raw_json="{}",
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get(
        "/costs",
        params={"subscription_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"},
    )
    assert resp.status_code == 200


def test_viewer_cannot_fetch_subscription_metrics():
    from tests.auth_helpers import auth_header, seed_app_user

    _auth_client()
    seed_app_user(user_id="viewer-scope", username="viewer", role=ROLE_VIEWER)
    viewer = TestClient(app)
    viewer.headers.update(auth_header(user_id="viewer-scope", username="viewer", role=ROLE_VIEWER))
    resp = viewer.get(
        "/metrics/subscription",
        params={"subscription_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
    )
    assert resp.status_code == 403


def test_resources_all_requires_synced_subscription():
    client = _auth_client()
    resp = client.get(
        "/resources/all",
        params={"subscription_id": "00000000-0000-0000-0000-000000000099"},
    )
    assert resp.status_code == 404


def test_subscription_is_registered_uses_cache_not_table_scan():
    from app.subscription_store import invalidate_registered_subscription_ids_cache, is_subscription_registered
    from app.validators import subscription_is_registered

    init_db()
    invalidate_registered_subscription_ids_cache()
    db = SessionLocal()
    try:
        db.query(SubscriptionCache).delete()
        db.add(
            SubscriptionCache(
                subscription_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
                display_name="Cached sub",
                state="Enabled",
                raw_json="{}",
            )
        )
        db.commit()

        with patch(
            "app.subscription_store._distinct_subscription_ids",
            side_effect=AssertionError("full table scan must not run on hot path"),
        ):
            assert is_subscription_registered(db, "cccccccc-cccc-cccc-cccc-cccccccccccc")
            assert subscription_is_registered(db, "cccccccc-cccc-cccc-cccc-cccccccccccc")
            assert not subscription_is_registered(db, "00000000-0000-0000-0000-000000000099")
    finally:
        db.close()


def test_list_analysis_jobs_skips_distinct_table_scan():
    client = _auth_client()
    unknown = "00000000-0000-0000-0000-000000000099"

    with patch(
        "app.subscription_store._distinct_subscription_ids",
        side_effect=AssertionError("list_analysis_jobs must not scan all tables"),
    ):
        resp = client.get(
            "/optimize/jobs",
            params={"subscription_id": unknown},
        )

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_analysis_jobs_returns_rows_for_cached_subscription():
    client = _auth_client()
    db = SessionLocal()
    try:
        db.add(
            SubscriptionCache(
                subscription_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
                display_name="Jobs sub",
                state="Enabled",
                raw_json="{}",
            )
        )
        db.commit()
    finally:
        db.close()

    with patch(
        "app.subscription_store._distinct_subscription_ids",
        side_effect=AssertionError("list_analysis_jobs must not scan all tables"),
    ):
        resp = client.get(
            "/optimize/jobs",
            params={"subscription_id": "dddddddd-dddd-dddd-dddd-dddddddddddd"},
        )

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_db_closes_session():
  """get_db() must return connections to the pool after each request."""
  closed = {"value": False}
  gen = get_db()
  db = next(gen)
  original_close = db.close

  def _tracked_close():
      closed["value"] = True
      original_close()

  db.close = _tracked_close
  gen.close()
  assert closed["value"] is True


def test_list_analysis_jobs_uses_bounded_query_count():
    """Hot path should issue a handful of queries, not 8+ table DISTINCT scans."""
    from sqlalchemy import event

    from app.database import engine

    client = _auth_client()
    db = SessionLocal()
    try:
        db.add(
            SubscriptionCache(
                subscription_id="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
                display_name="Query budget sub",
                state="Enabled",
                raw_json="{}",
            )
        )
        db.commit()
    finally:
        db.close()

    statements: list[str] = []

    def _capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(str(statement))

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        with patch(
            "app.subscription_store._distinct_subscription_ids",
            side_effect=AssertionError("list_analysis_jobs must not scan all tables"),
        ):
            resp = client.get(
                "/optimize/jobs",
                params={"subscription_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", "active_only": "true"},
            )
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    # Before fix: 8 DISTINCT scans + cache + jobs ≈ 20+. After: cache + settings + jobs + expire.
    assert len(statements) <= 12, f"too many SQL statements ({len(statements)}): {statements[:5]}..."

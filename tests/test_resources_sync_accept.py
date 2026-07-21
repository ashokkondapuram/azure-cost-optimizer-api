"""Tests for fast async POST /resources/sync accept path."""

from __future__ import annotations

import time
import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.integration_app import app
from app.models import AppUser
from app.sync_orchestrator import request_full_sync
from app.user_auth import ROLE_ADMIN, hash_password

SUBSCRIPTION_ID = "93ca908b-5732-440d-b712-f6d7951951c0"


def _auth_client() -> TestClient:
    init_db()
    db = SessionLocal()
    try:
        db.query(AppUser).filter(AppUser.username == "admin").delete()
        db.commit()
        db.add(
            AppUser(
                id="admin-resources-sync",
                username="admin",
                display_name="Administrator",
                password_hash=hash_password("password123"),
                role=ROLE_ADMIN,
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


def _slow_get_token(_db=None):
    time.sleep(2.0)
    return "slow-azure-token"


def test_resources_sync_scoped_accept_returns_202_without_arm_token():
    client = _auth_client()
    sub = SUBSCRIPTION_ID.lower()

    with patch("app.auth.get_token", side_effect=_slow_get_token):
        with patch("app.auth.arm_bearer_token", side_effect=_slow_get_token):
            with patch("app.sync_orchestrator.request_full_sync") as enqueue:
                enqueue.return_value = (
                    True,
                    {
                        "status": "accepted",
                        "async": True,
                        "pending": True,
                        "pipeline": {"subscription_id": sub, "status": "queued"},
                    },
                )
                started = time.monotonic()
                res = client.post(
                    "/api/resources/sync",
                    params={
                        "subscription_id": SUBSCRIPTION_ID,
                        "types": "database/cosmosdb",
                        "include_costs": "true",
                        "components": "Cosmos DB",
                        "wait": "false",
                    },
                )
                elapsed_ms = int((time.monotonic() - started) * 1000)

    assert res.status_code == 202, res.text
    assert elapsed_ms < 1000, f"accept took {elapsed_ms}ms — ARM token fetch must be deferred"
    body = res.json()
    assert body["status"] == "accepted"
    enqueue.assert_called_once()
    _args, kwargs = enqueue.call_args
    assert _args[0] == sub
    assert kwargs["token"] is None
    assert kwargs["scope_resource_types"] == ["database/cosmosdb"]
    assert kwargs["include_costs"] is True
    assert kwargs["scope_components"] == ["Cosmos DB"]


def test_request_full_sync_persists_on_accept(monkeypatch):
    persist_calls: list[str] = []

    def _track_persist(state):
        persist_calls.append(state.get("pipeline_id", ""))

    monkeypatch.setattr("app.sync_orchestrator._persist_pipeline_state", _track_persist)

    with patch("app.sync_orchestrator.threading.Thread") as thread_cls:
        thread_cls.return_value = MagicMock()
        enqueued, _payload = request_full_sync(SUBSCRIPTION_ID, reason="persist-accept")

    assert enqueued is True
    assert persist_calls, "accept path should persist pipeline row for cross-instance polls"


def test_sync_full_accept_skips_subscription_validation_and_arm_token():
    client = _auth_client()
    sub = str(uuid.uuid4()).lower()

    with patch("app.auth.get_token", side_effect=_slow_get_token):
        with patch("app.validators.ensure_subscription_known") as validate:
            with patch("app.routers.sync.request_full_sync") as enqueue:
                enqueue.return_value = (
                    True,
                    {"status": "accepted", "async": True, "pending": True},
                )
                started = time.monotonic()
                res = client.post(
                    "/api/sync/full",
                    params={
                        "subscription_id": sub,
                        "types": "database/cosmosdb",
                        "wait": "false",
                    },
                )
                elapsed_ms = int((time.monotonic() - started) * 1000)

    assert res.status_code == 202, res.text
    assert elapsed_ms < 1000
    validate.assert_not_called()
    enqueue.assert_called_once()
    assert enqueue.call_args.kwargs["token"] is None


def test_resources_sync_duplicate_returns_pipeline_for_polling():
    import app.sync_orchestrator as module

    with module._lock:
        module._pending.clear()
        module._pipeline_by_sub.clear()

    with patch("app.sync_orchestrator.threading.Thread") as thread_cls:
        thread_cls.return_value = MagicMock()
        first_ok, first = request_full_sync(
            SUBSCRIPTION_ID,
            type_list=["database/cosmosdb"],
            scope_resource_types=["database/cosmosdb"],
            reason="dup-poll-test",
        )
        second_ok, second = request_full_sync(
            SUBSCRIPTION_ID,
            type_list=["database/cosmosdb"],
            scope_resource_types=["database/cosmosdb"],
            reason="dup-poll-test",
        )

    assert first_ok is True
    assert second_ok is False
    assert second["status"] == "accepted"
    assert second.get("pipeline_id")
    assert second["pipeline"]["subscription_id"] == SUBSCRIPTION_ID.lower()

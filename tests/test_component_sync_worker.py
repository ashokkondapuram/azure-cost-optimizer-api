"""Tests for component sync worker."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, ComponentSyncState
from app.component_sync_worker import (
    _hydrate_last_sync_from_db,
    _last_component_sync_at,
    get_component_sync_status,
    run_component_sync,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def setup_function():
    _last_component_sync_at.clear()


def test_run_component_sync_skips_when_lock_held():
    with patch("app.component_sync_worker.sync_types_for_component", return_value=["compute/vm"]):
        with patch("app.operations_scheduler._try_acquire_scheduler_lock", return_value=False):
            result = run_component_sync("Virtual Machines")
    assert result["status"] == "skipped"
    assert result["reason"] == "lock_held"


def test_run_component_sync_does_not_advance_timestamp_on_total_failure():
    with patch("app.component_sync_worker.sync_types_for_component", return_value=["compute/vm"]):
        with patch("app.operations_scheduler._try_acquire_scheduler_lock", return_value=True):
            with patch("app.operations_scheduler._release_scheduler_lock"):
                with patch("app.auth.reload_credential"):
                    with patch("app.auth.get_token", return_value="tok"):
                        with patch("app.component_sync_worker._list_subscription_ids", return_value=["sub-a"]):
                            with patch("app.db_sync.sync_scoped", side_effect=RuntimeError("fail")):
                                with patch("app.component_sync_worker.analysis_after_component_sync", return_value=False):
                                    result = run_component_sync("Virtual Machines")
    assert result["status"] == "failed"
    assert "Virtual Machines" not in get_component_sync_status()["last_sync_at"]


def test_run_component_sync_records_timestamp_when_synced(db_session, monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr("app.database.SessionLocal", lambda: db_session)
    with patch("app.component_sync_worker.sync_types_for_component", return_value=["compute/vm"]):
        with patch("app.operations_scheduler._try_acquire_scheduler_lock", return_value=True):
            with patch("app.operations_scheduler._release_scheduler_lock"):
                with patch("app.auth.reload_credential"):
                    with patch("app.auth.get_token", return_value="tok"):
                        with patch("app.component_sync_worker._list_subscription_ids", return_value=["sub-a"]):
                            with patch("app.db_sync.sync_scoped"):
                                with patch("app.component_sync_worker.analysis_after_component_sync", return_value=False):
                                    with patch("app.component_sync_worker.datetime") as mock_dt:
                                        mock_dt.now.return_value = now
                                        result = run_component_sync("Virtual Machines")
    assert result["status"] == "ok"
    assert get_component_sync_status()["last_sync_at"].get("Virtual Machines")
    row = db_session.query(ComponentSyncState).filter_by(component="Virtual Machines").one()
    assert row.synced_at.replace(tzinfo=timezone.utc) == now
    assert row.last_status == "ok"


def test_hydrate_last_sync_from_db(db_session, monkeypatch):
    synced_at = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    db_session.add(
        ComponentSyncState(
            component="Key Vault",
            synced_at=synced_at,
            last_status="ok",
        )
    )
    db_session.commit()
    monkeypatch.setattr("app.database.SessionLocal", lambda: db_session)
    _hydrate_last_sync_from_db()
    loaded = _last_component_sync_at["Key Vault"]
    assert loaded == synced_at

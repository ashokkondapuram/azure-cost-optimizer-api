"""Tests for pipeline cost sync worker."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, CostSyncRun
from app.workers.cost_sync_worker import cost_data_fresh, run_cost_sync_worker


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_cost_data_fresh_when_recent_sync(db_session):
    sub = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    db_session.add(
        CostSyncRun(
            id=str(uuid.uuid4()),
            subscription_id=sub,
            month="2026-07",
            mtd_start="2026-07-01",
            mtd_end="2026-07-13",
            total_billing=100.0,
            total_usd=75.0,
            billing_currency="CAD",
            services_json="[]",
            changes_json="[]",
            synced_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()
    assert cost_data_fresh(db_session, sub) is True


def test_cost_data_fresh_when_stale(db_session):
    sub = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    db_session.add(
        CostSyncRun(
            id=str(uuid.uuid4()),
            subscription_id=sub,
            month="2026-06",
            mtd_start="2026-06-01",
            mtd_end="2026-06-30",
            total_billing=100.0,
            total_usd=75.0,
            billing_currency="CAD",
            services_json="[]",
            changes_json="[]",
            synced_at=datetime.now(timezone.utc) - timedelta(hours=48),
        )
    )
    db_session.commit()
    assert cost_data_fresh(db_session, sub) is False


def test_run_cost_sync_worker_skips_when_fresh(db_session, monkeypatch):
    monkeypatch.setenv("PIPELINE_COST_SYNC_ENABLED", "true")
    sub = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    with patch("app.workers.cost_sync_worker.cost_data_fresh", return_value=True):
        result = run_cost_sync_worker(db_session, sub)

    assert result["status"] == "fresh"
    assert result["skipped"] is True


def test_run_cost_sync_worker_syncs_when_stale(db_session, monkeypatch):
    monkeypatch.setenv("PIPELINE_COST_SYNC_ENABLED", "true")
    sub = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    with (
        patch("app.workers.cost_sync_worker.cost_data_fresh", return_value=False),
        patch("app.auth.get_token", return_value="token"),
        patch("app.db_sync.sync_costs", return_value={"month": "2026-07"}) as sync_mock,
    ):
        result = run_cost_sync_worker(db_session, sub)

    assert result["status"] == "ok"
    sync_mock.assert_called_once_with(sub, db_session, "token")


def test_run_cost_sync_worker_failure_does_not_raise(db_session, monkeypatch):
    monkeypatch.setenv("PIPELINE_COST_SYNC_ENABLED", "true")
    sub = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    with (
        patch("app.workers.cost_sync_worker.cost_data_fresh", return_value=False),
        patch("app.auth.get_token", side_effect=RuntimeError("no creds")),
    ):
        result = run_cost_sync_worker(db_session, sub)

    assert result["status"] == "failed"
    assert "no creds" in result["error"]

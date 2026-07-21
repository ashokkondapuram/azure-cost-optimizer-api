"""Tests for utilization trend helpers (history table removed)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base
from app.utilization_history import (
    batch_utilization_trends,
    downsize_allowed_by_trend,
    persist_utilization_snapshot,
    utilization_trend,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_persist_utilization_snapshot_is_noop(db_session):
    sub = "sub-test"
    vm_id = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    buckets = {
        "vms": [{
            "id": vm_id,
            "_technical_facts": {"avg_cpu_pct": 12.0, "max_cpu_pct": 45.0},
        }],
    }
    resource_facts = {vm_id.lower(): {"avg_cpu_pct": 12.0}}

    assert persist_utilization_snapshot(db_session, sub, buckets, resource_facts=resource_facts) == 0


def test_utilization_trend_returns_insufficient_history(db_session):
    rid = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    trend = utilization_trend(db_session, rid, "avg_cpu_pct", subscription_id="sub-1")
    assert trend["insufficient_history"] is True
    assert trend["slope"] == "unknown"


def test_downsize_allowed_by_trend_blocks_growing():
    assert downsize_allowed_by_trend({"slope": "growing", "insufficient_history": False}) is False
    assert downsize_allowed_by_trend({"slope": "stable", "insufficient_history": False}) is True
    assert downsize_allowed_by_trend({"slope": "unknown", "insufficient_history": True}) is True


def test_batch_utilization_trends_returns_nested_map(db_session):
    rid = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm3"
    trends = batch_utilization_trends(db_session, "sub-1", [rid], metrics=["avg_cpu_pct"])
    assert rid.lower() in trends
    assert trends[rid.lower()]["avg_cpu_pct"]["insufficient_history"] is True

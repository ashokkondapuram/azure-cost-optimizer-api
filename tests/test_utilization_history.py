"""Tests for utilization history persistence and trend analysis (T2-A)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, ResourceUtilizationHistory
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


def _seed_history(
    db,
    resource_id: str,
    metric_name: str,
    values: list[float],
    *,
    subscription_id: str = "sub-1",
) -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for idx, value in enumerate(values):
        day = (base + timedelta(days=idx * 7)).strftime("%Y-%m-%d")
        db.add(ResourceUtilizationHistory(
            id=str(uuid.uuid4()),
            subscription_id=subscription_id,
            resource_id=resource_id.lower(),
            metric_name=metric_name,
            snapshot_date=day,
            recorded_at=base + timedelta(days=idx * 7),
            value_avg=value,
            period_days=7,
        ))
    db.commit()


def test_persist_utilization_snapshot_upserts_same_day(db_session):
    sub = "sub-test"
    vm_id = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    buckets = {
        "vms": [{
            "id": vm_id,
            "_technical_facts": {"avg_cpu_pct": 12.0, "max_cpu_pct": 45.0},
        }],
    }
    resource_facts = {vm_id.lower(): {"avg_cpu_pct": 12.0}}

    first = persist_utilization_snapshot(db_session, sub, buckets, resource_facts=resource_facts)
    db_session.commit()
    second = persist_utilization_snapshot(db_session, sub, buckets, resource_facts=resource_facts)
    db_session.commit()

    rows = db_session.query(ResourceUtilizationHistory).filter(
        ResourceUtilizationHistory.subscription_id == sub,
        ResourceUtilizationHistory.resource_id == vm_id.lower(),
    ).all()
    assert first >= 2
    assert second >= 2
    assert len(rows) == 2
    avg_row = next(r for r in rows if r.metric_name == "avg_cpu_pct")
    assert avg_row.value_avg == 12.0


def test_utilization_trend_detects_growing_series(db_session):
    rid = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    _seed_history(db_session, rid, "avg_cpu_pct", [10.0, 12.0, 15.0, 18.0, 22.0])

    trend = utilization_trend(db_session, rid, "avg_cpu_pct", subscription_id="sub-1")
    assert trend["insufficient_history"] is False
    assert trend["slope"] == "growing"
    assert trend["projected_4w"] > trend["current_value"]


def test_utilization_trend_insufficient_history(db_session):
    rid = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm2"
    _seed_history(db_session, rid, "avg_cpu_pct", [10.0, 11.0])

    trend = utilization_trend(db_session, rid, "avg_cpu_pct")
    assert trend["insufficient_history"] is True
    assert trend["slope"] == "unknown"


def test_downsize_allowed_by_trend_blocks_growing():
    assert downsize_allowed_by_trend({"slope": "growing", "insufficient_history": False}) is False
    assert downsize_allowed_by_trend({"slope": "stable", "insufficient_history": False}) is True
    assert downsize_allowed_by_trend({"slope": "unknown", "insufficient_history": True}) is True


def test_batch_utilization_trends_returns_nested_map(db_session):
    rid = "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm3"
    _seed_history(db_session, rid, "avg_cpu_pct", [8.0, 8.5, 9.0, 9.5])

    trends = batch_utilization_trends(db_session, "sub-1", [rid], metrics=["avg_cpu_pct"])
    assert rid.lower() in trends
    assert trends[rid.lower()]["avg_cpu_pct"]["slope"] == "stable"

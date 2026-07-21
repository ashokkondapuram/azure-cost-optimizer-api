"""Tests for finding activity audit trail and job SSE events."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.finding_activity import list_finding_activity, log_finding_status_change
from app.job_events import publish_job_event, subscribe_job_events
from app.models import Base, OptimizationFinding


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_log_finding_status_change(db_session, sample_finding):
    log_finding_status_change(
        db_session,
        finding_id=sample_finding.id,
        subscription_id=sample_finding.subscription_id,
        from_status="open",
        to_status="acknowledged",
        user={"id": "u1", "username": "admin", "display_name": "Admin User"},
    )
    db_session.commit()
    items = list_finding_activity(db_session, finding_id=sample_finding.id)
    assert len(items) == 1
    assert items[0]["from_status"] == "open"
    assert items[0]["to_status"] == "acknowledged"
    assert items[0]["user_name"] == "Admin User"


def test_job_events_pub_sub():
    received: list[dict] = []

    async def collect():
        async for chunk in subscribe_job_events("sub-test-123"):
            if chunk.startswith("data: "):
                received.append(json.loads(chunk[6:].strip()))
            if len(received) >= 1:
                break

    async def run():
        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)
        publish_job_event("sub-test-123", {"type": "progress", "job": {"id": "j1", "progress_pct": 50}})
        await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(run())
    assert received[0]["type"] == "progress"
    assert received[0]["job"]["id"] == "j1"


@pytest.fixture
def sample_finding(db_session):
    finding = OptimizationFinding(
        id=str(uuid.uuid4()),
        run_id="run-1",
        rule_id="VM_IDLE",
        rule_name="Idle VM",
        category="compute",
        severity="medium",
        subscription_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        resource_id="/subscriptions/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        resource_name="vm1",
        status="open",
    )
    db_session.add(finding)
    db_session.commit()
    return finding

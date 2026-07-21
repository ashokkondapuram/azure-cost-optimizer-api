"""Tests for /activity finding audit trail routes."""

import uuid

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.finding_activity import list_finding_activity, log_activity_entry
from app.models import Base, OptimizationFinding
from app.routers.activity import router


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
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


def test_activity_routes_registered():
    paths = [route.path for route in router.routes if isinstance(route, APIRoute)]
    assert "/activity/finding/{finding_id}" in paths
    assert "/activity/log" in paths


def test_log_activity_entry_lists_note(db_session, sample_finding):
    log_activity_entry(
        db_session,
        finding_id=sample_finding.id,
        subscription_id=sample_finding.subscription_id,
        action="note",
        note="Reviewed with platform team",
        user={"id": "u1", "username": "admin", "display_name": "Admin User"},
    )
    db_session.commit()
    items = list_finding_activity(db_session, finding_id=sample_finding.id)
    assert len(items) == 1
    assert items[0]["action"] == "note"
    assert items[0]["note"] == "Reviewed with platform team"

"""Tests for resolved finding supersede filtering."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.finding_dedupe import actionable_resolved_rows, collect_open_identity_keys, is_superseded_resolved_row
from app.models import Base, OptimizationFinding


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _row(**kwargs):
    defaults = {
        "id": str(uuid.uuid4()),
        "run_id": "run-1",
        "rule_id": "VM_IDLE",
        "rule_name": "Idle VM",
        "category": "COMPUTE",
        "severity": "HIGH",
        "resource_id": "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1",
        "resource_name": "vm-1",
        "resource_type": "compute/vm",
        "subscription_id": "sub-1",
        "detail": "Detail",
        "recommendation": "Fix",
    }
    defaults.update(kwargs)
    return OptimizationFinding(**defaults)


def test_superseded_resolved_row_detected(db_session):
    resource_id = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"
    open_row = _row(id="open", status="open", resource_id=resource_id)
    resolved_row = _row(id="resolved", status="resolved", resource_id=resource_id)
    db_session.add_all([open_row, resolved_row])
    db_session.commit()

    open_keys = collect_open_identity_keys([open_row])
    assert is_superseded_resolved_row(resolved_row, open_keys) is True
    assert actionable_resolved_rows([resolved_row], open_keys) == []


def test_actionable_resolved_keeps_latest_per_key(db_session):
    resource_id = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-1"
    older = _row(
        id="old",
        status="resolved",
        rule_id="DISK_UNATTACHED",
        resource_id=resource_id,
        detected_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    newer = _row(
        id="new",
        status="resolved",
        rule_id="DISK_UNATTACHED",
        resource_id=resource_id,
        detected_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
    )
    open_keys = set()
    kept = actionable_resolved_rows([older, newer], open_keys)
    assert len(kept) == 1
    assert kept[0].id == "new"

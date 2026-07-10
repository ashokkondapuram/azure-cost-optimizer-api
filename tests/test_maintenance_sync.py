"""Tests for planned maintenance sync and activity log helpers."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.azure_maintenance import (
    _activity_log_row,
    _health_event_row,
    _is_maintenance_activity_event,
    _is_planned_maintenance_event,
    _is_upcoming,
    _vm_maintenance_row,
)
from app.maintenance_sync import (
    _dedupe_items,
    _filter_upcoming,
    _row_to_item_dict,
    load_planned_maintenance_from_db,
    sync_planned_maintenance,
)
from app.models import Base, MaintenanceSyncRun, PlannedMaintenanceItem


def test_is_planned_maintenance_event():
    assert _is_planned_maintenance_event({"properties": {"eventType": "PlannedMaintenance"}})
    assert not _is_planned_maintenance_event({"properties": {"eventType": "ServiceIssue"}})


def test_health_event_row_maps_properties():
    row = _health_event_row({
        "name": "tracking-1",
        "properties": {
            "title": "Host OS update",
            "eventType": "PlannedMaintenance",
            "impactStartTime": "2026-07-10T01:00:00Z",
            "impactMitigationTime": "2026-07-10T05:00:00Z",
            "impactedResource": "/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
            "summary": "Routine maintenance",
            "status": "Active",
        },
    })
    assert row["source"] == "health_event"
    assert row["resource_name"] == "vm1"
    assert row["title"] == "Host OS update"


def test_vm_maintenance_row_requires_window_or_upcoming():
    vm = {"id": "/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1", "name": "vm1"}
    assert _vm_maintenance_row(vm, {"upcoming": False}) is None
    row = _vm_maintenance_row(
        vm,
        {
            "upcoming": True,
            "maintenance_window_start": "2026-07-10T01:00:00Z",
            "maintenance_window_end": "2026-07-10T05:00:00Z",
        },
    )
    assert row["source"] == "vm"
    assert row["resource_name"] == "vm1"


def test_is_upcoming_false_for_past_window():
    assert _is_upcoming("2020-01-01T00:00:00Z", "2020-01-01T04:00:00Z") is False


def test_is_upcoming_false_for_past_start_without_end():
    assert _is_upcoming("2020-01-01T00:00:00Z", None) is False


def test_is_upcoming_true_for_in_progress_window():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert _is_upcoming(start, end) is True


def test_is_maintenance_activity_event_detects_live_migration():
    event = {
        "operationName": {"value": "Microsoft.Compute/virtualMachines/liveMigration/action"},
        "resourceId": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/vmss1",
    }
    assert _is_maintenance_activity_event(event)


def test_is_maintenance_activity_event_rejects_unrelated_operation():
    event = {
        "operationName": {"value": "Microsoft.Compute/virtualMachines/start/action"},
        "resourceId": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
    }
    assert not _is_maintenance_activity_event(event)


def test_activity_log_row_maps_vmss_live_migration():
    row = _activity_log_row({
        "eventDataId": "evt-1",
        "operationName": {"value": "Microsoft.Compute/virtualMachineScaleSets/virtualMachines/liveMigration/action"},
        "resourceId": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/vmss1",
        "eventTimestamp": "2026-07-01T12:00:00Z",
        "status": {"value": "Succeeded"},
    })
    assert row is not None
    assert row["source"] == "vmss"
    assert row["resource_type"] == "VM scale set"
    assert row["resource_name"] == "vmss1"
    assert row["origin"] == "activity_log"


def test_filter_upcoming_excludes_activity_log_history():
    from app.maintenance_sync import filter_upcoming_items

    recent_activity = {
        "source": "vmss",
        "origin": "activity_log",
        "event_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "window_start": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    future_vm = {
        "source": "vm",
        "window_start": "2030-01-01T00:00:00Z",
        "window_end": "2030-01-01T04:00:00Z",
    }
    filtered = filter_upcoming_items([recent_activity, future_vm], upcoming_only=True)
    assert recent_activity not in filtered
    assert future_vm in filtered


def test_row_to_item_dict_merges_payload():
    row = PlannedMaintenanceItem(
        id="1",
        subscription_id="sub",
        external_id="vm:rid",
        source="vm",
        resource_name="vm1",
        payload_json=json.dumps({"pending_model_update": True}),
        synced_at=datetime.now(timezone.utc),
    )
    item = _row_to_item_dict(row)
    assert item["id"] == "vm:rid"
    assert item["pending_model_update"] is True


def test_dedupe_items_keeps_last_occurrence():
    items = [
        {"id": "LZ_W-CGG", "title": "first"},
        {"id": "LZ_W-CGG", "title": "second"},
        {"id": "other", "title": "other"},
    ]
    deduped = _dedupe_items(items)
    assert len(deduped) == 2
    by_id = {row["id"]: row for row in deduped}
    assert by_id["LZ_W-CGG"]["title"] == "second"


def test_sync_skips_when_already_in_progress(db_session):
    from app.maintenance_sync import _sync_in_progress, _sync_in_progress_guard

    sub = "sub-1"
    with _sync_in_progress_guard:
        _sync_in_progress.add(sub)
    try:
        result = sync_planned_maintenance(db_session, sub, upcoming_only=False)
    finally:
        with _sync_in_progress_guard:
            _sync_in_progress.discard(sub)

    assert result.get("sync_skipped") is True
    assert result.get("data_source") == "database"


@pytest.fixture
def db_session(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'maint.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_sync_and_load_planned_maintenance(db_session):
    payload = {
        "items": [
            {
                "id": "vm:1",
                "source": "vm",
                "resource_type": "Virtual machine",
                "resource_name": "vm1",
                "window_start": "2030-01-01T00:00:00Z",
                "window_end": "2030-01-01T04:00:00Z",
            },
        ],
    }

    with patch("app.maintenance_sync.AzureMaintenanceClient") as mock_client_cls:
        mock_client_cls.return_value.list_planned_maintenance.return_value = payload
        result = sync_planned_maintenance(db_session, "sub-1", upcoming_only=True)

    assert result["count"] == 1
    assert result["data_source"] == "azure"
    assert db_session.query(PlannedMaintenanceItem).count() == 1
    assert db_session.query(MaintenanceSyncRun).filter_by(status="success").count() == 1

    cached = load_planned_maintenance_from_db(db_session, "sub-1", upcoming_only=True)
    assert cached["data_source"] == "database"
    assert cached["count"] == 1
    assert cached["synced_at"] is not None

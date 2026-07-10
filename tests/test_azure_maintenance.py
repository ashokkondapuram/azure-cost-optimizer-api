"""Tests for planned maintenance helpers."""

from app.azure_maintenance import (
    _health_event_row,
    _is_planned_maintenance_event,
    _is_upcoming,
    _vm_maintenance_row,
)


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

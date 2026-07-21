"""Tests for disk snapshot retention helpers."""

from datetime import datetime, timedelta, timezone

from app.snapshot_retention import (
    is_stale_snapshot,
    meets_snapshot_savings_gate,
    meets_snapshot_size_gate,
    snapshot_age_days,
    snapshot_created_at,
    snapshot_lineage_evidence,
    snapshot_size_gb,
    snapshot_threshold_evidence,
)


def _snapshot(*, days_ago: int = 100, size_gb: float = 64) -> dict:
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/snapshots/snap1",
        "name": "snap1",
        "properties": {
            "diskSizeGB": size_gb,
            "timeCreated": created.isoformat(),
            "diskState": "Unattached",
            "provisioningState": "Succeeded",
            "creationData": {
                "sourceResourceId": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
                "incremental": True,
            },
        },
        "sku": {"name": "Standard_LRS"},
    }


def test_snapshot_created_at_from_properties():
    snap = _snapshot(days_ago=30)
    created = snapshot_created_at(snap)
    assert created is not None
    assert snapshot_age_days(snap) == 30


def test_is_stale_snapshot_respects_retention_days():
    snap = _snapshot(days_ago=100)
    assert is_stale_snapshot(snap, retention_days=90) is True
    assert is_stale_snapshot(snap, retention_days=120) is False


def test_meets_snapshot_size_gate():
    snap = _snapshot(size_gb=32)
    assert meets_snapshot_size_gate(snap, min_size_gb=0) is True
    assert meets_snapshot_size_gate(snap, min_size_gb=64) is False
    assert meets_snapshot_size_gate(snap, min_size_gb=32) is True


def test_meets_snapshot_savings_gate():
    assert meets_snapshot_savings_gate(5.0, min_monthly_savings_usd=1.0) is True
    assert meets_snapshot_savings_gate(0.5, min_monthly_savings_usd=1.0) is False


def test_snapshot_threshold_evidence():
    class Rule:
        snapshot_retention_days = 90
        snapshot_min_size_gb = 10
        min_monthly_savings_usd = 2.0

    assert snapshot_threshold_evidence(Rule()) == {
        "snapshot_retention_days": 90,
        "snapshot_min_size_gb": 10,
        "min_monthly_savings_usd": 2.0,
    }


def test_snapshot_lineage_evidence():
    snap = _snapshot()
    lineage = snapshot_lineage_evidence(snap)
    assert lineage["sku"] == "Standard_LRS"
    assert lineage["incremental"] is True
    assert "disks/d1" in lineage["source_disk_id"]
    assert snapshot_size_gb(snap) == 64

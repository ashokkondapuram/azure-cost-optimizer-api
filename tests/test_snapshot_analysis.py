"""Tests for disk snapshot retention analysis."""

from datetime import datetime, timedelta, timezone

from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.resource_engines.compute.snapshot.analysis import analyze_snapshots
from app.optimizer.resource_engines.runtime.context import AnalysisContext
from app.resource_store import _display_state


def _snapshot(created_days_ago: int = 120) -> dict:
    created = datetime.now(timezone.utc) - timedelta(days=created_days_ago)
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/snapshots/snap-old"
    return {
        "id": rid,
        "name": "snap-old",
        "type": "compute/snapshot",
        "properties": {
            "diskSizeGB": 128,
            "timeCreated": created.isoformat(),
            "provisioningState": "Succeeded",
        },
    }


def test_display_state_uses_creation_time_for_snapshots():
    created = datetime(2024, 3, 15, tzinfo=timezone.utc)
    state = _display_state(
        "compute/snapshot",
        None,
        {"timeCreated": created.isoformat(), "provisioningState": "Succeeded"},
    )
    assert state == created.isoformat()


def test_analyze_snapshots_finds_stale_snapshot_with_cost():
    eng = ExtendedOptimizationEngine()
    snap = _snapshot(created_days_ago=120)
    rid = snap["id"].lower()
    findings = analyze_snapshots(eng, "sub", [snap], {rid: 18.5})
    assert len(findings) == 1
    assert findings[0].rule_id == "SNAPSHOT_RETENTION_EXTENDED"
    assert findings[0].estimated_savings_usd == 18.5
    assert findings[0].evidence["age_days"] >= 119
    assert findings[0].evidence["size_gb"] == 128
    assert findings[0].evidence["time_created"]


def test_analyze_snapshots_skips_without_creation_time():
    eng = ExtendedOptimizationEngine()
    snap = _snapshot()
    snap["properties"].pop("timeCreated")
    assert analyze_snapshots(eng, "sub", [snap], {snap["id"].lower(): 5.0}) == []


def test_analyze_snapshots_skips_young_snapshots():
    eng = ExtendedOptimizationEngine()
    snap = _snapshot(created_days_ago=10)
    assert analyze_snapshots(eng, "sub", [snap], {snap["id"].lower(): 5.0}) == []


def test_analyze_snapshots_skips_below_min_size_gate():
    eng = ExtendedOptimizationEngine(
        rule_overrides={"SNAPSHOT_RETENTION_EXTENDED": {"snapshot_min_size_gb": 256}},
    )
    snap = _snapshot(created_days_ago=120)
    assert analyze_snapshots(eng, "sub", [snap], {snap["id"].lower(): 5.0}) == []


def test_analyze_snapshots_skips_below_savings_gate():
    eng = ExtendedOptimizationEngine()
    snap = _snapshot(created_days_ago=120)
    assert analyze_snapshots(eng, "sub", [snap], {snap["id"].lower(): 0.5}) == []


def test_analyze_snapshots_includes_lineage_evidence():
    eng = ExtendedOptimizationEngine()
    snap = _snapshot(created_days_ago=120)
    snap["properties"]["creationData"] = {
        "sourceResourceId": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        "incremental": True,
    }
    snap["sku"] = {"name": "Premium_LRS"}
    rid = snap["id"].lower()
    findings = analyze_snapshots(eng, "sub", [snap], {rid: 12.0})
    assert len(findings) == 1
    assert findings[0].evidence["incremental"] is True
    assert "disks/d1" in findings[0].evidence["source_disk_id"]
    assert findings[0].evidence["snapshot_retention_days"] == 90


def test_standard_engine_snapshot_uses_configurable_retention():
    from app.optimizer.engine import OptimizationEngine

    eng = OptimizationEngine(
        rule_overrides={"SNAPSHOT_OLD": {"snapshot_retention_days": 30, "snapshot_min_size_gb": 0}},
    )
    snap = _snapshot(created_days_ago=45)
    rid = snap["id"].lower()
    result = eng.analyze(snapshots=[snap], cost_by_resource={rid: 8.0})
    snap_findings = [f for f in result["findings"] if f.get("rule_id") == "SNAPSHOT_OLD"]
    assert len(snap_findings) == 1
    assert snap_findings[0]["evidence"]["snapshot_retention_days"] == 30


def test_snapshot_sub_engine_runs_in_extended_batch():
    eng = ExtendedOptimizationEngine()
    snap = _snapshot(created_days_ago=100)
    rid = snap["id"].lower()
    result = eng.analyze(
        subscription_id="sub",
        snapshots=[snap],
        cost_by_resource={rid: 12.0},
    )
    snap_findings = [
        f for f in result["findings"]
        if (f.get("resource_id") or "").lower() == rid
    ]
    assert snap_findings
    assert snap_findings[0]["rule_id"] == "SNAPSHOT_RETENTION_EXTENDED"


def test_snapshot_technical_facts_include_age_days():
    from app.optimizer.resource_engines.runtime.envelope import build_resource_envelope

    snap = _snapshot(created_days_ago=45)
    ctx = AnalysisContext(subscription_id="sub", rules={}, cost_by_resource={})
    envelope = build_resource_envelope(snap, ctx)
    assert envelope.facts.get("time_created")
    assert envelope.facts.get("age_days") == 45

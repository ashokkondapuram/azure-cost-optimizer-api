"""Engine integration tests for unattached disk staleness gating."""

from datetime import datetime, timedelta, timezone

from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.engine import OptimizationEngine
from app.optimizer.resource_engines.compute.disk.analysis import analyze_disks


def _disk_with_facts(name: str, *, state: str = "Attached", sku: str = "Premium_LRS", facts: dict | None = None, **props_overrides) -> dict:
    props = {
        "diskState": state,
        "diskSizeGB": 256,
        "diskIOPSReadWrite": 5000,
        "diskMBpsReadWrite": 200,
        "timeCreated": datetime.now(timezone.utc).isoformat(),
    }
    props.update(props_overrides)
    disk = {
        "id": f"/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/disks/{name}",
        "name": name,
        "type": "Microsoft.Compute/disks",
        "location": "eastus",
        "sku": {"name": sku},
        "properties": props,
    }
    if facts:
        disk["_technical_facts"] = {"data_source": "azure_monitor", **facts}
    return disk


def _unattached_disk(name: str, *, days_unattached: int, last_owner: str | None = None) -> dict:
    detached = datetime.now(timezone.utc) - timedelta(days=days_unattached)
    created = datetime.now(timezone.utc) - timedelta(days=days_unattached + 30)
    props = {
        "diskState": "Unattached",
        "diskSizeGB": 128,
        "timeCreated": created.isoformat(),
        "lastOwnershipUpdateTime": detached.isoformat(),
    }
    if last_owner:
        props["lastManagedBy"] = last_owner
    return {
        "id": f"/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/disks/{name}",
        "name": name,
        "type": "Microsoft.Compute/disks",
        "location": "eastus",
        "sku": {"name": "Premium_LRS"},
        "properties": props,
    }


def test_extended_engine_skips_recent_unattached_disk():
    eng = ExtendedOptimizationEngine()
    disk = _unattached_disk("recent-disk", days_unattached=3)
    findings = analyze_disks(
        eng,
        "s",
        [disk],
        {disk["id"].lower(): 45.0},
    )
    disk_findings = [f for f in findings if f.rule_id == "DISK_UNUSED_EXTENDED"]
    assert disk_findings == []


def test_extended_engine_flags_stale_unattached_disk():
    eng = ExtendedOptimizationEngine()
    disk = _unattached_disk(
        "stale-disk",
        days_unattached=30,
        last_owner="/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/old-vm",
    )
    findings = analyze_disks(
        eng,
        "s",
        [disk],
        {disk["id"].lower(): 80.0},
    )
    disk_findings = [f for f in findings if f.rule_id == "DISK_UNUSED_EXTENDED"]
    assert len(disk_findings) == 1
    assert "30 days" in disk_findings[0].detail
    assert "old-vm" in disk_findings[0].detail
    assert disk_findings[0].evidence.get("is_stale") is True
    assert disk_findings[0].evidence.get("last_owner_name") == "old-vm"


def test_standard_engine_skips_recent_unattached_disk():
    eng = OptimizationEngine()
    disk = _unattached_disk("recent-std", days_unattached=5)
    findings = eng._check_disks([disk], {disk["id"].lower(): 20.0})
    assert [f for f in findings if f.rule_id == "DISK_UNATTACHED"] == []


def test_standard_engine_flags_stale_unattached_disk():
    eng = OptimizationEngine()
    disk = _unattached_disk("stale-std", days_unattached=21)
    findings = eng._check_disks([disk], {disk["id"].lower(): 20.0})
    attached = [f for f in findings if f.rule_id == "DISK_UNATTACHED"]
    assert len(attached) == 1
    assert attached[0].evidence.get("age_days", 0) >= 21


def test_extended_engine_skips_premium_downgrade_when_iops_utilization_high():
    eng = ExtendedOptimizationEngine()
    disk = _disk_with_facts(
        "busy-premium",
        facts={
            "disk_read_bps": 10.0,
            "disk_write_bps": 5.0,
            "disk_read_iops": 900.0,
            "disk_write_iops": 200.0,
        },
    )
    findings = analyze_disks(eng, "s", [disk], {disk["id"].lower(): 120.0})
    assert [f for f in findings if f.rule_id == "DISK_OVERSIZE_EXTENDED"] == []


def test_extended_engine_flags_underprovisioned_premium_disk():
    eng = ExtendedOptimizationEngine()
    disk = _disk_with_facts(
        "hot-premium",
        facts={
            "disk_read_iops": 3600.0,
            "disk_write_iops": 900.0,
        },
    )
    findings = analyze_disks(eng, "s", [disk], {disk["id"].lower(): 200.0})
    under = [f for f in findings if f.rule_id == "DISK_UNDERPROVISIONED"]
    assert len(under) == 1
    assert under[0].evidence.get("disk_iops_utilization_pct", 0) >= 80
    assert under[0].evidence.get("disk_iops_high_util_pct") == 80.0


def test_disk_underprovisioned_respects_rule_override_threshold():
    eng = ExtendedOptimizationEngine(rule_overrides={
        "DISK_UNDERPROVISIONED": {"disk_iops_high_util_pct": 70.0},
    })
    disk = _disk_with_facts(
        "warm-premium",
        facts={
            "disk_read_iops": 2800.0,
            "disk_write_iops": 700.0,
        },
    )
    findings = analyze_disks(eng, "s", [disk], {disk["id"].lower(): 200.0})
    under = [f for f in findings if f.rule_id == "DISK_UNDERPROVISIONED"]
    assert len(under) == 1
    assert under[0].evidence.get("disk_iops_high_util_pct") == 70.0

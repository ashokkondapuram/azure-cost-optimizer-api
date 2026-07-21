"""Tests for managed disk catalog provisioned performance resolution."""

from app.managed_disk_catalog import (
    enrich_disk_provisioned_properties,
    parse_disk_arm,
    provisioned_limits_from_tier,
    resolve_disk_provisioned_performance,
)


def test_provisioned_limits_from_tier_premium_256gb():
    iops, mbps = provisioned_limits_from_tier("Premium_LRS", 256)
    assert iops == 3500
    assert mbps == 170


def test_provisioned_limits_from_tier_standard_ssd_512gb():
    iops, mbps = provisioned_limits_from_tier("StandardSSD_LRS", 512)
    assert iops == 500
    assert mbps == 60


def test_provisioned_limits_from_tier_premium_zrs_uses_lrs_bands():
    iops, mbps = provisioned_limits_from_tier("Premium_ZRS", 1024)
    assert iops == 7500
    assert mbps == 250


def test_resolve_disk_provisioned_performance_prefers_arm():
    disk = {
        "sku": {"name": "Premium_LRS"},
        "properties": {
            "diskSizeGB": 256,
            "diskIOPSReadWrite": 8000,
            "diskMBpsReadWrite": 300,
        },
    }
    perf = resolve_disk_provisioned_performance(disk)
    assert perf["diskIOPSReadWrite"] == 8000
    assert perf["diskMBpsReadWrite"] == 300
    assert perf["provisionedPerformanceSource"] == "arm"


def test_resolve_disk_provisioned_performance_falls_back_to_tier():
    disk = {
        "sku": {"name": "StandardSSD_LRS"},
        "properties": {"diskSizeGB": 128},
    }
    perf = resolve_disk_provisioned_performance(disk)
    assert perf["diskIOPSReadWrite"] == 500
    assert perf["diskMBpsReadWrite"] == 60
    assert perf["provisionedPerformanceSource"] == "tier_spec"


def test_resolve_disk_provisioned_performance_accepts_string_sku():
    disk = {
        "sku": "Premium_LRS",
        "properties": {"diskSizeGB": 256, "diskState": "Attached"},
    }
    perf = resolve_disk_provisioned_performance(disk)
    assert perf["diskIOPSReadWrite"] == 3500
    assert perf["diskMBpsReadWrite"] == 170
    assert perf["provisionedPerformanceSource"] == "tier_spec"


def test_parse_disk_arm_includes_tier_limits():
    ctx = parse_disk_arm({
        "sku": {"name": "Premium_LRS"},
        "properties": {"diskSizeGB": 512, "diskState": "Attached"},
    })
    assert ctx["provisioned_iops"] == 3500
    assert ctx["provisioned_mbps"] == 170


def test_enrich_disk_provisioned_properties_persists_values():
    props = {"diskSizeGB": 1024}
    enrich_disk_provisioned_properties(props, sku={"name": "Premium_LRS"})
    assert props["diskIOPSReadWrite"] == 7500
    assert props["diskMBpsReadWrite"] == 250
    assert props["provisionedPerformanceSource"] == "tier_spec"

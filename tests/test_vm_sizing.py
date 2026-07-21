"""Tests for VM SKU parsing and rightsizing recommendations."""

from app.vm_sizing import (
    extract_vm_utilization,
    parse_vm_sku,
    recommend_vm_sku,
    sku_in_catalog,
    suggest_smaller_sku,
)


def _metrics(cpu: float, available_memory_bytes: float) -> dict:
    return {
        "value": [
            {
                "name": {"value": "Percentage CPU"},
                "timeseries": [{"data": [{"average": cpu}]}],
            },
            {
                "name": {"value": "Available Memory Bytes"},
                "timeseries": [{"data": [{"average": available_memory_bytes}]}],
            },
        ]
    }


def test_parse_vm_sku_d_family():
    parsed = parse_vm_sku("Standard_D4s_v3")
    assert parsed is not None
    assert parsed.family == "D"
    assert parsed.family_label == "General purpose"
    assert parsed.vcpus == 4
    assert parsed.memory_gb == 16.0
    assert parsed.variant == "s"
    assert parsed.version == 3


def test_parse_vm_sku_from_catalog():
    parsed = parse_vm_sku(
        "Standard_E8s_v5",
        catalog_entry={"name": "Standard_E8s_v5", "numberOfCores": 8, "memoryInMB": 65536},
    )
    assert parsed is not None
    assert parsed.family == "E"
    assert parsed.memory_gb == 64.0


def test_extract_vm_utilization_memory_percent():
    # D4s_v3 ≈ 16 GB; 12 GB available → ~25% used
    util = extract_vm_utilization(
        _metrics(12.0, 12 * 1024**3),
        sku="Standard_D4s_v3",
    )
    assert util.avg_cpu_pct == 12.0
    assert util.has_cpu is True
    assert util.has_memory is True
    assert util.avg_memory_pct is not None
    assert 20 < util.avg_memory_pct < 30


def test_recommend_downgrade_low_cpu_and_memory():
    util = extract_vm_utilization(
        _metrics(8.0, 13 * 1024**3),
        sku="Standard_D4s_v3",
    )
    rec = recommend_vm_sku(current_sku="Standard_D4s_v3", utilization=util)
    assert rec is not None
    assert rec.action == "downgrade"
    assert rec.suggested_sku == "Standard_D2s_v3"
    assert rec.direction == "down"


def test_recommend_upgrade_high_cpu():
    util = extract_vm_utilization(
        _metrics(88.0, 10 * 1024**3),
        sku="Standard_D4s_v3",
    )
    rec = recommend_vm_sku(current_sku="Standard_D4s_v3", utilization=util)
    assert rec is not None
    assert rec.action == "upgrade"
    assert rec.suggested_sku == "Standard_D8s_v3"


def test_suggest_smaller_sku_compat():
    assert suggest_smaller_sku("Standard_D4s_v3") == "Standard_D2s_v3"


def test_cross_family_recommends_catalog_sku():
    catalog = [
        {"name": "Standard_D4s_v3", "numberOfCores": 4, "memoryInMB": 16384},
        {"name": "Standard_B2s_v3", "numberOfCores": 2, "memoryInMB": 8192},
    ]
    util = extract_vm_utilization(
        _metrics(8.0, 13 * 1024**3),
        sku="Standard_D4s_v3",
    )
    rec = recommend_vm_sku(current_sku="Standard_D4s_v3", utilization=util, catalog=catalog)
    assert rec is not None
    assert rec.action in {"downgrade", "cross_family"}
    assert rec.suggested_sku in {row["name"] for row in catalog}


def test_sku_in_catalog_requires_catalog():
    catalog = [{"name": "Standard_D4s_v3"}]
    assert sku_in_catalog("Standard_D4s_v3", catalog) is True
    assert sku_in_catalog("Standard_B2s_v3", catalog) is False
    assert sku_in_catalog("Standard_D4s_v3", None) is False
    assert sku_in_catalog(None, catalog) is False

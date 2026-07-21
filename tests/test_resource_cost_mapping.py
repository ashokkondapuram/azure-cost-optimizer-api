"""Tests for resource → cost driver property/metric mapping."""

from __future__ import annotations

from app.resource_cost_mapping import (
    cost_drivers_for_resource,
    generate_resource_cost_mapping_markdown,
    resource_cost_mapping,
    resource_cost_mapping_for_type,
)


def test_vm_cost_mapping_includes_properties_and_metrics():
    mapping = resource_cost_mapping_for_type("compute/vm")
    fact_keys = {d["fact_key"] for d in mapping["cost_drivers"]}
    assert "vm_size" in fact_keys
    assert "avg_cpu_pct" in fact_keys
    assert "monthly_cost_usd" in fact_keys
    assert mapping["property_count"] >= 1
    assert mapping["metric_count"] >= 1


def test_disk_mapping_includes_disk_state_and_io_metrics():
    mapping = resource_cost_mapping_for_type("compute/disk")
    fact_keys = {d["fact_key"] for d in mapping["cost_drivers"]}
    assert "disk_state" in fact_keys
    assert "disk_read_bps" in fact_keys
    assert "provisioned_iops" in fact_keys
    monitor_metrics = {
        m["fact_key"]
        for profile in mapping["monitor_profiles"]
        for m in profile.get("metrics", [])
    }
    assert "disk_read_iops" in monitor_metrics


def test_full_mapping_covers_resource_types():
    data = resource_cost_mapping()
    assert data["count"] >= 30
    types = {r["canonical_type"] for r in data["resources"]}
    assert "compute/vm" in types
    assert "storage/account" in types


def test_cost_drivers_for_vm_resource_id():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    result = cost_drivers_for_resource(rid, "compute/vm")
    assert result["resource_id"] == rid
    assert len(result["cost_drivers"]) >= 3


def test_sql_server_returns_unavailable_with_hint():
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Sql/servers/srv1"
    result = cost_drivers_for_resource(rid, "database/sql")
    assert result["data_quality"] == "unavailable"


def test_generate_markdown_includes_vm_section():
    md = generate_resource_cost_mapping_markdown()
    assert "compute/vm" in md
    assert "Properties (inventory)" in md
    assert "Metrics (Azure Monitor" in md

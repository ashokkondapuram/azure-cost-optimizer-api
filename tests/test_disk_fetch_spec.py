"""Tests for disk-assessment.json driven inventory, metrics, and cost fetch specs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DISK_ASSESSMENT = ROOT / "data" / "disk-assessment.json"


@pytest.fixture(scope="module")
def disk_assessment() -> dict:
    return json.loads(DISK_ASSESSMENT.read_text(encoding="utf-8"))


def test_disk_sync_property_paths_from_assessment(disk_assessment):
    from app.assessment.disk_fetch_spec import disk_sync_property_paths

    expected = tuple(disk_assessment["azure_properties"]["sync_property_paths"])
    assert disk_sync_property_paths() == expected
    assert len(disk_sync_property_paths()) == 14


def test_disk_arm_property_paths_from_groups(disk_assessment):
    from app.assessment.disk_fetch_spec import disk_arm_property_paths

    paths = disk_arm_property_paths()
    assert paths
    group_paths = [
        prop["arm_path"]
        for group in disk_assessment["azure_properties"]["groups"]
        for prop in group["properties"]
    ]
    assert set(group_paths) == set(paths)
    assert "properties.diskSizeGB" in paths
    assert "sku.name" in paths


def test_disk_monitor_metrics_from_assessment(disk_assessment):
    from app.assessment.disk_fetch_spec import disk_monitor_metric_names, disk_monitor_metrics

    assessment_metrics = disk_assessment["azure_metrics"]["metrics"]
    profile_metrics = disk_monitor_metrics()
    assert len(profile_metrics) == len(assessment_metrics) == 5

    names = disk_monitor_metric_names()
    assert names == tuple(m["metric_name"] for m in assessment_metrics)
    assert "Composite Disk Read Bytes/sec" in names
    assert "DiskPaidBurstIOPS" in names

    fact_keys = {m.fact_key for m in profile_metrics}
    assert fact_keys == {m["fact_key"] for m in assessment_metrics}
    read_metric = next(m for m in profile_metrics if m.fact_key == "disk_read_bps")
    assert read_metric.aggregation == "Average"
    assert read_metric.timespan == "P7D"


def test_disk_cost_fields_from_assessment(disk_assessment):
    from app.assessment.disk_fetch_spec import (
        billed_mtd_normalized_key,
        cost_field_mapping,
        disk_cost_field_names,
        disk_cost_fields,
        retail_monthly_normalized_key,
    )

    fields = disk_cost_fields()
    assert len(fields) == len(disk_assessment["cost_management"]["fields"]) == 6
    assert disk_cost_field_names() == (
        "billed_mtd",
        "retail_monthly",
        "retail_currency",
        "retail_source",
        "retail_pending",
        "savings_estimate",
    )
    mapping = cost_field_mapping()
    assert mapping["billed_mtd"] == "monthly_cost_usd"
    assert mapping["retail_monthly"] == "retail_monthly"
    assert billed_mtd_normalized_key() == "monthly_cost_usd"
    assert retail_monthly_normalized_key() == "retail_monthly"


def test_resource_profile_uses_assessment(disk_assessment):
    from app.resources.registry import (
        RESOURCE_MONITOR_PROFILES,
        TECHNICAL_FETCH_SPECS,
        assessment_driven_fetch_spec,
        assessment_driven_monitor_profile,
    )

    spec = TECHNICAL_FETCH_SPECS["compute/disk"]
    assert spec.sync_property_paths == tuple(disk_assessment["azure_properties"]["sync_property_paths"])

    profile = RESOURCE_MONITOR_PROFILES["microsoft.compute/disks"]
    assessment_names = [m["metric_name"] for m in disk_assessment["azure_metrics"]["metrics"]]
    assert profile.metric_names() == tuple(assessment_names)

    assert assessment_driven_fetch_spec("compute/disk") is spec
    driven_profile = assessment_driven_monitor_profile("compute/disk")
    assert driven_profile is not None
    assert driven_profile.canonical_type == "compute/disk"


def test_normalize_disk_arm_properties_respects_sync_paths():
    from it_services.compute_disk.arm_disk_properties import normalize_disk_arm_properties

    arm = {
        "sku": {"name": "Premium_LRS"},
        "properties": {
            "diskSizeGB": 512,
            "diskState": "Unattached",
            "hyperVGeneration": "V2",
            "provisioningState": "Succeeded",
        },
    }
    props = normalize_disk_arm_properties(arm)
    assert props["diskSizeGB"] == 512
    assert props["sku"] == "Premium_LRS"
    assert "hyperVGeneration" not in props


def test_attach_cost_envelope_applies_assessment_normalized_keys():
    from app.cost_utils import attach_cost_envelope_to_row, build_resource_cost_envelope

    row = {"type": "compute/disk", "id": "/subscriptions/s/rg/providers/Microsoft.Compute/disks/d1"}
    envelope = build_resource_cost_envelope(
        billing=42.0,
        usd=42.0,
        currency="USD",
        retail_monthly=38.0,
        retail_currency="USD",
        retail_source="azure_retail_prices",
        retail_pending=False,
        cost_pending=False,
    )
    attach_cost_envelope_to_row(row, envelope)
    assert row["monthly_cost_usd"] == 42.0
    assert row["retail_monthly"] == 38.0


def test_monitor_metric_names_spec_alignment(disk_assessment):
    from app.assessment.spec import monitor_metric_names, required_metric_keys
    from app.assessment.disk_fetch_spec import disk_monitor_metric_names, disk_required_metric_keys

    assert disk_monitor_metric_names() == monitor_metric_names(disk_assessment)
    assert disk_required_metric_keys() == required_metric_keys(disk_assessment)

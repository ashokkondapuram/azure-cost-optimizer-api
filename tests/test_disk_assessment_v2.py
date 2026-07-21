"""Validate disk-assessment.json schema v2 structure and rule alignment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.assessment.catalog import get_assessment_for_arm_type
from app.assessment.spec import monitor_metric_names, required_metric_keys
from app.optimizer.rule_catalog import RULE_MANIFEST

DATA = Path(__file__).resolve().parents[1] / "data"
DISK_PATH = DATA / "disk-assessment.json"

DISK_ENGINE_RULES = {
    "DISK_UNATTACHED",
    "DISK_OVERSIZE",
    "DISK_UNUSED_EXTENDED",
    "DISK_OVERSIZE_EXTENDED",
    "DISK_UNDERPROVISIONED",
    "DISK_CAPACITY_RIGHTSIZE_EXTENDED",
    "DISK_QUEUE_DEPTH_EXTENDED",
    "DISK_NEW_GRACE_PERIOD",
    "DISK_ULTRA_DOWNGRADE_PREMIUM",
    "DISK_ULTRA_DOWNGRADE_SSD",
    "DISK_PREMIUM_DOWNGRADE_HDD",
    "DISK_SSD_DOWNGRADE_HDD",
}


@pytest.fixture(scope="module")
def disk_assessment() -> dict:
    return json.loads(DISK_PATH.read_text(encoding="utf-8"))


def test_disk_assessment_json_valid_and_compact(disk_assessment):
    assert DISK_PATH.is_file()
    line_count = len(DISK_PATH.read_text(encoding="utf-8").splitlines())
    assert line_count < 2500, f"disk-assessment.json too large: {line_count} lines"
    assert disk_assessment["schema_version"] == "2.0"


def test_disk_assessment_required_sections(disk_assessment):
    for key in (
        "azure_properties",
        "azure_metrics",
        "cost_management",
        "rules",
        "cases",
    ):
        assert key in disk_assessment
        assert disk_assessment[key]


def test_disk_assessment_rule_ids_match_engine(disk_assessment):
    rule_ids = {rule["rule_id"] for rule in disk_assessment["rules"]}
    assert rule_ids == DISK_ENGINE_RULES
    for rule_id in rule_ids:
        assert rule_id in RULE_MANIFEST


def test_disk_assessment_cases_reference_valid_rules(disk_assessment):
    rule_ids = {rule["rule_id"] for rule in disk_assessment["rules"]}
    for case in disk_assessment["cases"]:
        assert case["rule_id"] in rule_ids


def test_disk_assessment_metrics_from_monitor_profile(disk_assessment):
    metrics = disk_assessment["azure_metrics"]["metrics"]
    fact_keys = {m["fact_key"] for m in metrics}
    assert {
        "disk_read_bps",
        "disk_write_bps",
        "disk_read_iops",
        "disk_write_iops",
        "disk_paid_burst_iops",
    } <= fact_keys

    names = monitor_metric_names(disk_assessment)
    assert "Composite Disk Read Bytes/sec" in names
    assert "DiskPaidBurstIOPS" in names


def test_disk_assessment_cost_fields(disk_assessment):
    fields = {f["field"] for f in disk_assessment["cost_management"]["fields"]}
    assert "billed_mtd" in fields
    assert "retail_monthly" in fields


def test_disk_assessment_loaded_by_catalog():
    from it_services.compute_disk.assessment_bridge import (
        disk_rule_ids,
        hydrate_disk_rules,
        optimization_thresholds,
    )
    from app.optimizer.advanced_rules import ADVANCED_RULES
    import copy

    assessment = get_assessment_for_arm_type("Microsoft.Compute/disks")
    assert assessment is not None
    assert assessment.get("_file") == "disk-assessment.json"
    assert assessment.get("schema_version") == "2.0"
    keys = required_metric_keys(assessment)
    assert "disk_read_bps" in keys
    assert "disk_iops_utilization_pct" in keys
    assert len(disk_rule_ids()) == 12
    assert optimization_thresholds().get("max_unattached_disk_days") == 14

    rules = {rid: copy.deepcopy(r) for rid, r in ADVANCED_RULES.items()}
    hydrate_disk_rules(rules)
    assert rules["DISK_UNUSED_EXTENDED"].disk_io_idle_bps == 1024.0


def test_rule_evidence_from_disk_assessment():
    from app.rule_evidence_config import analysis_rule_config, required_evidence_for_rule

    cfg = analysis_rule_config("DISK_OVERSIZE_EXTENDED", "compute/disk")
    assert cfg.get("required_evidence")
    assert cfg.get("evidence_factors")
    evidence = required_evidence_for_rule("DISK_OVERSIZE_EXTENDED", "compute/disk")
    signals = {item["signal"] for item in evidence}
    assert "disk_read_throughput" in signals


def test_augment_finding_evidence_structured_rows():
    from it_services.compute_disk.assessment_bridge import augment_finding_evidence

    raw = {
        "disk_state": "Attached",
        "sku": "Premium_LRS",
        "disk_read_bps": 400.0,
        "disk_write_bps": 300.0,
        "disk_iops_utilization_pct": 8.0,
        "disk_io_idle_bps": 1024,
        "disk_idle_min_size_gb": 128,
        "creationData": {"createOption": "Copy"},
        "data_quality": "inventory_only",
    }
    out = augment_finding_evidence("DISK_OVERSIZE_EXTENDED", raw)

    assert out.get("exclude_inventory_facts") is True
    assert "assessment_file" not in out
    assert out.get("rule_thresholds", {}).get("disk_io_idle_bps") == 1024
    assert "disk_io_idle_bps" not in out
    assert "creationData" not in out.get("resource_details", {})

    rows = out.get("evidence_rows") or []
    assert rows
    signals = {row["signal"] for row in rows}
    assert "disk_iops_utilization_pct" in signals
    iops_row = next(row for row in rows if row["signal"] == "disk_iops_utilization_pct")
    assert iops_row["value"] == "8%"
    assert iops_row["label"] == "Disk IOPS utilization"
    assert iops_row["pillar"] == "performance"
    assert out.get("evidence_factors")

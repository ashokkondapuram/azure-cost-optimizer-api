"""Tests for generic assessment bridge and config resolver."""

from __future__ import annotations

import pytest

from app.assessment.bridge import (
    is_v2_assessment,
    load_assessment_for_canonical,
    optimization_thresholds,
    sync_property_paths,
)
from app.assessment.config_resolver import (
    assessment_file_for_canonical,
    load_optimization_thresholds,
    load_resource_config,
)
from app.assessment.property_registry import property_defs_for_canonical
from app.assessment.route_table_fetch_spec import (
    load_route_table_assessment,
    route_table_sync_property_paths,
)
from app.assessment.vm_fetch_spec import load_vm_assessment, vm_optimization_thresholds


def test_disk_assessment_is_v2_reference():
    assessment = load_assessment_for_canonical("compute/disk")
    assert assessment is not None
    assert is_v2_assessment(assessment)
    assert assessment_file_for_canonical("compute/disk") == "disk-assessment.json"
    paths = sync_property_paths(assessment)
    assert "diskSizeGB" in paths
    thresholds = optimization_thresholds(assessment)
    assert thresholds.get("disk_io_idle_bps") == 1024.0
    assert assessment.get("disk_tier_specs")


def test_disk_property_registry_roundtrip():
    defs = property_defs_for_canonical("compute/disk")
    keys = {d.property_key for d in defs}
    assert "diskSizeGB" in keys
    assert "sku" in keys


def test_vm_thresholds_from_assessment():
    assessment = load_vm_assessment()
    assert assessment is not None
    thresholds = vm_optimization_thresholds()
    assert thresholds.get("cpu_idle_pct") == 5.0
    assert assessment.get("analysis_rules")


def test_vm_config_resolver():
    config = load_resource_config("compute/vm")
    assert config.get("optimization_thresholds")
    assert load_optimization_thresholds("compute/vm").get("cpu_downsize_pct") == 20.0


def test_route_table_fetch_spec():
    assessment = load_route_table_assessment()
    assert assessment is not None
    paths = route_table_sync_property_paths()
    assert "routes" in paths or "properties.routes" in str(paths)


def test_route_table_property_defs_v1_fallback():
    defs = property_defs_for_canonical("network/routetable")
    keys = {d.property_key for d in defs}
    assert "routes" in keys or "subnets" in keys

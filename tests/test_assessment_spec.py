"""Tests for assessment JSON spec extraction."""

from __future__ import annotations

from app.assessment.signals import compute_signals
from app.assessment.spec import (
    monitor_metric_names,
    required_metric_keys,
    required_normalized_input,
)


def _disk_assessment_stub() -> dict:
    return {
        "_file": "disk-assessment.json",
        "resourceType": "Microsoft.Compute/disks",
        "supportedDiskMetricsFallback": [
            {"restApiName": "Composite Disk Read Operations/sec"},
            {"restApiName": "DiskPaidBurstIOPS"},
        ],
        "lowCallCollectionPlan": {
            "minimumCallFlowPerSubscription": [
                {"metricnames": ["Composite Disk Write Operations/sec"]},
            ],
        },
        "derivedMetrics": {"p95Iops": "p95(readOpsPerSec + writeOpsPerSec)"},
        "costOptimizationSignals": [
            "monthlyActualCost",
            "p95Iops",
            "p95ThroughputMBps",
        ],
        "pythonAssessment": {
            "requiredNormalizedInput": ["resource", "metrics", "cost", "signals"],
            "deterministicCases": {
                "warning": [
                    {"field": "signals.p95IopsUtilizationPct", "operator": "gt", "value": 80},
                ],
            },
        },
    }


def test_monitor_metric_names_from_assessment_json():
    names = monitor_metric_names(_disk_assessment_stub())
    assert "Composite Disk Read Operations/sec" in names
    assert "DiskPaidBurstIOPS" in names
    assert "Composite Disk Write Operations/sec" in names


def test_required_metric_keys_from_assessment_json():
    keys = required_metric_keys(_disk_assessment_stub())
    assert "p95Iops" in keys
    assert "p95ThroughputMBps" in keys
    assert "p95IopsUtilizationPct" in keys
    assert "monthlyActualCost" not in keys


def test_required_normalized_input_from_assessment_json():
    fields = required_normalized_input(_disk_assessment_stub())
    assert "metrics" in fields
    assert "signals" in fields


def test_compute_signals_sets_required_metrics_present():
    record = {
        "metrics": {"p95Iops": 12.0},
        "cost": {"monthlyActualCost": 10.0},
        "tags": {},
        "policy": {},
    }
    signals = compute_signals(record, required_metric_keys=["p95Iops"])
    assert signals["requiredMetricsPresent"] is True
    assert signals["costDataComplete"] is True
    assert signals["missingRequiredMetrics"] is False

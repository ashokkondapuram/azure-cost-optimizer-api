"""Tests for metric trigger registry."""
from __future__ import annotations

from app.metrics_triggers import (
    METRIC_TRIGGERS,
    TRAFFIC_THRESHOLDS,
    generate_metrics_triggers_markdown,
    trigger_reason_for_finding,
    triggers_for_rule,
)
from app.optimization_metrics import RULE_METRIC_PROFILES


def test_avg_cpu_trigger_links_to_vm_rules():
    trigger = METRIC_TRIGGERS["avg_cpu_pct"]
    assert "VM_IDLE" in trigger.rules
    assert trigger.direction == "both"
    assert trigger.safety_gate


def test_traffic_thresholds_match_utilization_constants():
    assert TRAFFIC_THRESHOLDS["byte_count_low"] == 1_000_000
    assert TRAFFIC_THRESHOLDS["disk_io_idle_bps"] == 1024


def test_trigger_reason_for_vm_idle_finding():
    evidence = {
        "optimization_metrics": {
            "performance": [
                {"id": "avg_cpu", "label": "Average CPU utilization", "value": "3.2%", "status": "underutilized"},
            ],
        },
    }
    reasons = trigger_reason_for_finding("VM_IDLE", evidence)
    assert reasons
    assert reasons[0]["fact_key"] == "avg_cpu_pct"
    assert reasons[0]["threshold"]


def test_rule_metric_profiles_have_trigger_coverage():
    missing = []
    for rule_id in RULE_METRIC_PROFILES:
        if rule_id.startswith("BUDGET_"):
            continue
        if not triggers_for_rule(rule_id):
            missing.append(rule_id)
    assert len(missing) < len(RULE_METRIC_PROFILES) * 0.5


def test_generate_markdown_contains_key_metrics():
    md = generate_metrics_triggers_markdown()
    assert "avg_cpu_pct" in md
    assert "Centralized thresholds" in md

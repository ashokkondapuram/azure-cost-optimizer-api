"""Tests for unified finding merge and recommendation mode."""

from __future__ import annotations

from app.finding_dedupe import merge_unified_findings, pick_better_finding
from app.optimizer.analysis_routing import unified_recommendation_mode


def test_unified_recommendation_mode_default(monkeypatch):
    monkeypatch.delenv("LEGACY_SUB_ENGINES_ENABLED", raising=False)
    monkeypatch.setenv("ASSESSMENT_PIPELINE_ENABLED", "true")
    assert unified_recommendation_mode() is True


def test_pick_better_finding_prefers_higher_savings():
    current = {
        "rule_id": "DISK_TIER",
        "resource_id": "/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/disks/d1",
        "estimated_savings_usd": 10,
        "severity": "MEDIUM",
        "data_source": "assessment_pipeline",
    }
    candidate = {
        "rule_id": "DISK_TIER",
        "resource_id": "/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/disks/d1",
        "estimated_savings_usd": 25,
        "severity": "HIGH",
        "data_source": "legacy_sub_engines",
        "detail": "Legacy engine found larger savings",
    }
    picked = pick_better_finding(current, candidate)
    assert picked["estimated_savings_usd"] == 25


def test_merge_unified_findings_keeps_one_per_identity():
    findings = [
        {
            "subscription_id": "sub-a",
            "rule_id": "VM_IDLE",
            "resource_id": "/subscriptions/sub-a/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
            "estimated_savings_usd": 5,
            "severity": "LOW",
            "data_source": "assessment_pipeline",
        },
        {
            "subscription_id": "sub-a",
            "rule_id": "VM_IDLE",
            "resource_id": "/subscriptions/sub-a/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
            "estimated_savings_usd": 40,
            "severity": "HIGH",
            "data_source": "legacy_sub_engines",
        },
    ]
    merged = merge_unified_findings(findings)
    assert len(merged) == 1
    assert merged[0]["estimated_savings_usd"] == 40

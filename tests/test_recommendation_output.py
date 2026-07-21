"""Tests for recommendation output validation and assessment coverage."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.assessment.catalog import collect_assessment_rule_ids
from app.assessment.recommendation_engine import (
    collect_covered_resource_ids,
    evaluate_assessment_recommendations,
)
from app.assessment.runtime import rule_applies_to_resource
from app.optimizer.platform.runtime.base import ResourceSubEngine
from app.optimizer.platform.runtime.context import AnalysisContext
from app.optimizer.rule_registry import is_known_rule
from app.recommendation_output import (
    enrich_recommendation_narrative,
    extract_evidence_highlights,
    extract_target_action,
    filter_valid_recommendations,
    is_actionable_recommendation,
    normalize_recommendation_finding,
    recommendation_api_shape,
    synthesize_action_narrative,
)


def test_rejects_generic_assessment_rule_placeholder():
    finding = {
        "rule_id": "assessment_rule",
        "severity": "MEDIUM",
        "resource_id": "/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/disks/d1",
        "detail": "Generic text",
        "recommendation": "Do something",
        "estimated_savings_usd": 10,
        "evidence": {"engine": "assessment_json"},
    }
    assert is_actionable_recommendation(finding) is False
    assert normalize_recommendation_finding(finding) is None


def test_accepts_rule_based_assessment_finding():
    finding = {
        "rule_id": "disk_orphan",
        "severity": "HIGH",
        "resource_id": "/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/disks/d1",
        "detail": "Delete orphaned disk",
        "recommendation": "Delete orphaned disk",
        "estimated_savings_usd": 25.5,
        "evidence": {
            "engine": "assessment_json",
            "rule_source": "assessment_json",
            "assessment_file": "disk-assessment.json",
            "pillar": "cost",
            "confidence": "high",
            "signals": {"isOrphaned": True},
        },
    }
    normalized = normalize_recommendation_finding(finding)
    assert normalized is not None
    shape = recommendation_api_shape(normalized)
    assert shape["rule_id"] == "disk_orphan"
    assert shape["severity"] == "HIGH"
    assert shape["estimated_savings_usd"] == 25.5
    assert shape["evidence"]["rule_source"] == "assessment_json"
    assert shape["evidence"]["signals"]["isOrphaned"] is True


def test_filter_valid_recommendations_drops_invalid_rows():
    rows = [
        {
            "rule_id": "VM_IDLE",
            "severity": "HIGH",
            "resource_id": "/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
            "detail": "VM is idle",
            "recommendation": "Deallocate VM",
            "estimated_savings_usd": 40,
            "evidence": {"engine": "extended_engine", "rule_id": "VM_IDLE"},
        },
        {
            "rule_id": "assessment_rule",
            "severity": "LOW",
            "resource_id": "/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/disks/d2",
            "detail": "placeholder",
            "recommendation": "placeholder",
            "estimated_savings_usd": 0,
            "evidence": {},
        },
    ]
    valid = filter_valid_recommendations(rows)
    assert len(valid) == 1
    assert valid[0]["rule_id"] == "VM_IDLE"


def test_rule_applies_to_resource_requires_primary_type_when_unscoped():
    rule = {"id": "example_rule", "condition": {"type": "all", "conditions": []}}
    assert rule_applies_to_resource(
        rule,
        "Microsoft.Example/resources",
        primary_resource_type=None,
    ) is False
    assert rule_applies_to_resource(
        rule,
        "",
        primary_resource_type=None,
    ) is True
    assert rule_applies_to_resource(
        rule,
        "Microsoft.Example/resources",
        primary_resource_type="Microsoft.Example/resources",
    ) is True


def test_collect_covered_resource_ids_from_buckets():
    buckets = {
        "disks": [{"id": "/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/disks/d1"}],
        "vms": [],
    }
    covered = collect_covered_resource_ids(buckets)
    assert covered == {
        "/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/disks/d1".lower(),
    }


class _DiskLikeSubEngine(ResourceSubEngine):
    component = "Managed Disks"
    bucket_keys = ("disks",)

    def analyze(self, buckets):
        return []


def test_evaluate_assessment_recommendations_returns_rule_findings(monkeypatch):
    assessment = {
        "_file": "disk-assessment.json",
        "resourceType": "Microsoft.Compute/disks",
        "recommendationRules": [
            {
                "id": "disk_orphan",
                "severity": "high",
                "enabled": True,
                "pillar": "cost",
                "condition": {
                    "type": "all",
                    "conditions": [
                        {"field": "signals.isOrphaned", "operator": "eq", "value": True},
                    ],
                },
                "recommendation": "Delete orphaned disk",
            }
        ],
    }

    monkeypatch.setattr(
        "app.optimizer.platform.runtime.base.get_assessment_for_arm_type",
        lambda _arm: assessment,
    )
    monkeypatch.setattr(
        "app.optimizer.platform.runtime.base.evaluate_assessment_rules",
        lambda *_args, **_kwargs: assessment["recommendationRules"],
    )

    ctx = AnalysisContext(
        subscription_id="sub-a",
        rules={},
        cost_by_resource={},
    )
    engine = MagicMock()
    resource = {
        "id": "/subscriptions/sub-a/resourcegroups/rg/providers/microsoft.compute/disks/d1",
        "name": "d1",
        "type": "Microsoft.Compute/disks",
        "_technical_facts": {},
        "_canonical_type": "compute/disk",
        "_resource_elements": {"cost": {"monthly_usd": 5.0}, "runtime": {}},
    }

    findings = evaluate_assessment_recommendations(engine, ctx, [resource])
    assert len(findings) == 1
    assert findings[0].rule_id == "disk_orphan"
    assert findings[0].evidence.get("rule_source") == "assessment_json"


def test_assessment_rule_ids_are_known_rules():
    sample_ids = collect_assessment_rule_ids()[:5]
    assert sample_ids
    for rule_id in sample_ids:
        assert is_known_rule(rule_id)


def test_enrich_recommendation_narrative_uses_evidence_summary_and_savings():
    finding = {
        "rule_id": "VM_IDLE",
        "detail": "VM is idle",
        "recommendation": "Deallocate VM",
        "estimated_savings_usd": 127.0,
        "evidence": {
            "summary": "Average CPU is 12.0% over the evaluation window (idle threshold ≤ 5%).",
            "checks": [
                {
                    "signal": "Average CPU utilization",
                    "value": 12.0,
                    "value_display": "12.0%",
                    "threshold_display": "≤ 5%",
                    "passed": True,
                }
            ],
            "vm_size": "Standard_D4s_v3",
            "suggested_sku": "Standard_D2s_v3",
        },
    }
    result = enrich_recommendation_narrative(finding, action_type="resize_down")
    assert "12.0%" in result["narrative"]
    assert "Standard_D4s_v3" in result["narrative"]
    assert "Standard_D2s_v3" in result["narrative"]
    assert "$127/mo" in result["narrative"]
    assert any(h["label"] == "Average CPU utilization" for h in result["highlights"])


def test_extract_target_action_from_sku_evidence():
    evidence = {"vm_size": "Standard_D4s_v3", "suggested_sku": "Standard_D2s_v3"}
    action = extract_target_action(evidence, action_type="resize_down")
    assert action == "Resize from Standard_D4s_v3 to Standard_D2s_v3"


def test_extract_evidence_highlights_disk_iops():
    evidence = {
        "checks": [
            {
                "signal": "IOPS utilization",
                "value": 45.0,
                "value_display": "45.0%",
                "threshold_display": "< 50%",
            }
        ],
        "provisioned_iops": 5120,
        "measured_iops": 2300,
        "resource_details": {"sku": "Premium_LRS", "size_gb": 512},
    }
    highlights = extract_evidence_highlights(evidence)
    labels = {h["label"] for h in highlights}
    assert "IOPS utilization" in labels
    assert any("45.0%" in h["value"] for h in highlights)


def test_synthesize_action_narrative_merges_multiple_findings():
    findings = [
        {
            "rule_id": "VM_UNDERUTILIZED_EXTENDED",
            "rule_name": "Underutilized VM",
            "estimated_savings_usd": 80,
            "detail": "Generic detail",
            "recommendation": "Resize VM",
            "evidence": {
                "summary": "VM average CPU is 8.5% (extended idle analysis).",
                "avg_cpu_pct": 8.5,
            },
        },
        {
            "rule_id": "VM_NO_RESERVED",
            "rule_name": "No reservation",
            "estimated_savings_usd": 40,
            "detail": "No RI",
            "recommendation": "Buy reservation",
            "evidence": {"summary": "VM Standard_D4s_v3 is running on pay-as-you-go pricing."},
        },
    ]
    result = synthesize_action_narrative(
        findings,
        action_type="resize_down",
        estimated_savings=120.0,
        workload_type="batch",
    )
    assert "8.5%" in result["narrative"]
    assert "Also flagged: No reservation" in result["narrative"]
    assert "$120/mo" in result["narrative"]
    assert "batch workload" in result["narrative"]


def test_synthesize_action_narrative_does_not_invent_metrics():
    result = synthesize_action_narrative(
        [{"detail": "Review", "recommendation": "Review", "evidence": {}}],
        fallback_reason="CPU and memory utilization are below threshold",
    )
    assert "CPU and memory" in result["narrative"]
    assert result["highlights"] == []

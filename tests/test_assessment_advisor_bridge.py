"""Tests for assessment JSON vs Azure Advisor pillar separation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.assessment.advisor_bridge import (
    advisor_row_to_finding,
    build_policy_from_advisor,
    is_json_evaluated_rule,
)
from app.assessment.bridge import resource_to_assessment_record
from app.assessment.runtime import evaluate_assessment_rules
from app.assessment.catalog import get_assessment_for_arm_type
from app.assessment.normalizer import build_normalized_record
from app.optimizer.platform.runtime.base import ResourceSubEngine
from app.optimizer.platform.runtime.context import AnalysisContext


def test_json_evaluated_rule_filters_reliability_and_security():
    assert is_json_evaluated_rule({"pillar": "cost", "id": "cost_rule"})
    assert is_json_evaluated_rule({"pillar": "performance", "id": "perf_rule"})
    assert is_json_evaluated_rule({"pillar": "governance", "id": "gov_rule"})
    assert not is_json_evaluated_rule({"pillar": "reliability", "id": "rel_rule"})
    assert not is_json_evaluated_rule({"pillar": "security", "id": "sec_rule"})


def test_build_policy_from_advisor_sets_security_and_reliability_flags():
    rows = [
        SimpleNamespace(category="Security", impact="High", recommendation_id="sec-1"),
        SimpleNamespace(category="HighAvailability", impact="High", recommendation_id="rel-1"),
        SimpleNamespace(category="Cost", impact="High", recommendation_id="cost-1"),
    ]
    policy = build_policy_from_advisor(rows)
    assert policy["anyHighSecurityFinding"] is True
    assert policy["anyHighReliabilityFinding"] is True
    assert policy["advisorRecommendationCount"] == 3


def test_advisor_row_to_finding_maps_reliability_pillar():
    row = SimpleNamespace(
        category="HighAvailability",
        impact="High",
        summary="Enable zone redundancy",
        description="Deploy across availability zones.",
        potential_savings_monthly=0.0,
        resource_id="/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/disks/d1",
        recommendation_id="rec-ha-1",
        recommendation_type_id="ha-type",
    )
    resource = {
        "resource_id": row.resource_id,
        "resource": {"name": "d1", "type": "Microsoft.Compute/disks"},
    }
    finding = advisor_row_to_finding(row, resource=resource, subscription_id="sub")
    assert finding is not None
    assert finding["category"] == "reliability"
    assert finding["evidence"]["rule_source"] == "azure_advisor"
    assert finding["rule_id"] == "advisor_rec-ha-1"


def test_evaluate_assessment_rules_skips_security_json_rules():
    assessment = get_assessment_for_arm_type("Microsoft.Compute/virtualMachines")
    assert assessment is not None

    record = build_normalized_record(
        {
            "subscription_id": "sub",
            "resource_id": "/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
            "resource_name": "vm1",
            "resource_type": "Microsoft.Compute/virtualMachines",
            "resource_group": "rg",
            "location": "canadacentral",
            "sku": "Standard_D2s_v3",
            "properties": {},
            "tags": {},
            "monthly_cost_usd": 100.0,
        },
        metrics={"avg_cpu_pct": 10},
        policy={"anyHighSecurityFinding": True},
        assessment=assessment,
    )
    matched = evaluate_assessment_rules(assessment, record, exclude_investigate=True)
    pillars = {rule.get("pillar") for rule in matched}
    assert "security" not in pillars
    assert "reliability" not in pillars


class _AdvisorSubEngine(ResourceSubEngine):
    component = "Managed Disks"
    bucket_keys = ("disks",)

    def analyze(self, buckets):
        return []


def test_sub_engine_merges_advisor_reliability_findings():
    assessment = {
        "_file": "disk-assessment.json",
        "recommendationRules": [
            {
                "id": "disk_cost_rule",
                "pillar": "cost",
                "severity": "medium",
                "enabled": True,
                "condition": {
                    "type": "all",
                    "conditions": [
                        {"field": "cost.monthlyActualCost", "operator": "gt", "value": 0},
                    ],
                },
                "recommendation": "Review disk cost",
            },
            {
                "id": "disk_security_json",
                "pillar": "security",
                "severity": "high",
                "enabled": True,
                "condition": {
                    "type": "all",
                    "conditions": [
                        {"field": "signals.publicAccessEnabled", "operator": "is_true"},
                    ],
                },
                "recommendation": "Should not fire from JSON",
            },
        ],
    }

    advisor_row = SimpleNamespace(
        category="Security",
        impact="High",
        summary="Restrict network access",
        description="Disable public network access.",
        potential_savings_monthly=0.0,
        resource_id="/subscriptions/sub-a/resourcegroups/rg/providers/microsoft.compute/disks/d1",
        recommendation_id="adv-sec-1",
        recommendation_type_id="",
    )

    ctx = AnalysisContext(
        subscription_id="sub-a",
        rules={},
        cost_by_resource={},
        vm_metrics={},
        node_metrics={},
        resource_metrics={},
        resource_facts={},
        global_config={},
        advisor_by_resource={
            "/subscriptions/sub-a/resourcegroups/rg/providers/microsoft.compute/disks/d1": [advisor_row],
        },
    )
    engine = _AdvisorSubEngine(MagicMock(), ctx)

    from app.optimizer.platform.runtime import base as base_mod

    original_get = base_mod.get_assessment_for_arm_type
    base_mod.get_assessment_for_arm_type = lambda _arm: assessment
    try:
        resource = {
            "id": "/subscriptions/sub-a/resourcegroups/rg/providers/microsoft.compute/disks/d1",
            "name": "d1",
            "location": "eastus",
            "type": "Microsoft.Compute/disks",
            "_technical_facts": {},
            "_canonical_type": "compute/disk",
            "_resource_elements": {"cost": {"monthly_usd": 5.0}, "runtime": {}},
        }
        findings = engine.evaluate_assessment_findings([resource])
    finally:
        base_mod.get_assessment_for_arm_type = original_get

    rule_ids = {f.rule_id for f in findings}
    assert "disk_cost_rule" in rule_ids
    assert "disk_security_json" not in rule_ids
    assert "advisor_adv-sec-1" in rule_ids
    advisor_finding = next(f for f in findings if f.rule_id == "advisor_adv-sec-1")
    assert advisor_finding.evidence.get("rule_source") == "azure_advisor"
    assert advisor_finding.category == "security"


def test_resource_to_assessment_record_includes_advisor_policy_signals():
    advisor_row = SimpleNamespace(
        category="Security",
        impact="High",
        recommendation_id="sec-1",
    )
    ctx = AnalysisContext(
        subscription_id="sub-a",
        rules={},
        cost_by_resource={},
        vm_metrics={},
        node_metrics={},
        resource_metrics={},
        resource_facts={},
        global_config={},
        advisor_by_resource={
            "/subscriptions/sub-a/resourcegroups/rg/providers/microsoft.compute/disks/d1": [advisor_row],
        },
    )
    resource = {
        "id": "/subscriptions/sub-a/resourcegroups/rg/providers/microsoft.compute/disks/d1",
        "name": "d1",
        "location": "eastus",
        "_technical_facts": {},
        "_canonical_type": "compute/disk",
        "_resource_elements": {"cost": {"monthly_usd": 5.0}, "runtime": {}},
    }
    record = resource_to_assessment_record(resource, ctx)
    assert record["policy"]["anyHighSecurityFinding"] is True
    assert record["signals"]["anyHighSecurityFinding"] is True

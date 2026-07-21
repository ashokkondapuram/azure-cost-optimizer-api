"""Tests for deterministic assessment runtime evaluation."""

from __future__ import annotations

import pytest

from app.assessment.catalog import get_assessment_for_arm_type
from app.assessment.runtime import (
    assess_data_quality,
    evaluate_assessment_rules,
    evaluate_condition,
    rule_to_finding,
)


def test_evaluate_condition_uses_path_alias():
    resource = {"properties": {"diskState": "Unattached"}}
    assert evaluate_condition(resource, {"path": "properties.diskState", "operator": "eq", "value": "Unattached"})
    assert not evaluate_condition(resource, {"field": "properties.diskState", "operator": "eq", "value": "Attached"})


def test_missing_required_metrics_caps_score():
    assessment = get_assessment_for_arm_type("Microsoft.Compute/disks")
    assert assessment is not None

    resource = {
        "resource_id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        "resource_type": "Microsoft.Compute/disks",
        "properties": {"diskState": "Attached"},
        "metrics": {},
        "cost": {"monthlyActualCost": 10.0},
        "tags": {},
        "policy": {},
        "signals": {
            "missingRequiredMetrics": True,
            "missingCostData": False,
        },
    }
    quality = assess_data_quality(assessment, resource)
    assert quality["score"] <= 74


def test_missing_cost_data_caps_score():
    assessment = get_assessment_for_arm_type("Microsoft.Compute/disks")
    assert assessment is not None

    resource = {
        "resource_id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        "resource_type": "Microsoft.Compute/disks",
        "properties": {"diskState": "Attached"},
        "metrics": {"Composite Disk Read Bytes/sec": 1.0},
        "cost": {},
        "tags": {},
        "policy": {},
        "signals": {
            "missingRequiredMetrics": False,
            "missingCostData": True,
        },
    }
    quality = assess_data_quality(assessment, resource)
    assert quality["score"] <= 74


def test_disk_delete_unattached_rule_matches():
    assessment = get_assessment_for_arm_type("Microsoft.Compute/disks")
    assert assessment is not None

    schema = str(assessment.get("schema_version") or assessment.get("schemaVersion") or "")
    if schema.startswith("2"):
        rule_ids = {rule["rule_id"] for rule in assessment.get("rules") or []}
        assert "DISK_UNUSED_EXTENDED" in rule_ids
        case_ids = {case["case_id"] for case in assessment.get("cases") or []}
        assert "unattached_stale" in case_ids
        return

    resource = {
        "resource_id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        "resource_type": "Microsoft.Compute/disks",
        "resource": {"name": "d1", "resource_group": "rg", "location": "eastus"},
        "properties": {"diskState": "Unattached"},
        "metrics": {},
        "cost": {"monthlyActualCost": 25.0},
        "tags": {},
        "policy": {},
        "signals": {},
    }
    matched = evaluate_assessment_rules(
        assessment,
        resource,
        include_assessment_rules=True,
        include_recommendation_rules=True,
        exclude_investigate=True,
    )
    rule_ids = {rule.get("id") for rule in matched}
    assert "disk_delete_unattached" in rule_ids

    rule = next(r for r in matched if r.get("id") == "disk_delete_unattached")
    finding = rule_to_finding(rule, resource=resource, assessment_file="disk-assessment.json")
    assert finding["rule_id"] == "disk_delete_unattached"
    assert finding["severity"] == "HIGH"


def test_disabled_rules_are_skipped():
    assessment = {
        "assessmentRules": [
            {
                "id": "disabled_rule",
                "enabled": False,
                "condition": {"type": "all", "conditions": [{"field": "properties.x", "operator": "present"}]},
            }
        ],
        "recommendationRules": [],
    }
    resource = {"properties": {"x": 1}}
    matched = evaluate_assessment_rules(assessment, resource)
    assert matched == []


def test_exclude_metric_gaps_skips_missing_metric_rules():
    assessment = {
        "recommendationRules": [
            {
                "id": "metric_transactions_missing",
                "recommendationAction": "downgrade",
                "condition": {
                    "type": "all",
                    "conditions": [
                        {"field": "metrics.transactions", "operator": "missing"},
                    ],
                },
            },
            {
                "id": "storage_tier_downgrade",
                "recommendationAction": "downgrade",
                "condition": {
                    "type": "all",
                    "conditions": [
                        {"field": "properties.accessTier", "operator": "eq", "value": "Hot"},
                    ],
                },
            },
        ],
    }
    resource = {
        "properties": {"accessTier": "Hot"},
        "metrics": {},
    }
    with_gaps = evaluate_assessment_rules(assessment, resource)
    without_gaps = evaluate_assessment_rules(assessment, resource, exclude_metric_gaps=True)
    assert {r.get("id") for r in with_gaps} == {"metric_transactions_missing", "storage_tier_downgrade"}
    assert {r.get("id") for r in without_gaps} == {"storage_tier_downgrade"}


def test_rule_to_finding_uses_human_readable_rule_name():
    rule = {
        "id": "metric_transactions_missing",
        "severity": "medium",
        "output": {
            "message": "Transaction metrics are missing for this storage account.",
            "recommendedActionText": "Sync Azure Monitor metrics, then rerun analysis.",
        },
    }
    resource = {
        "resource_id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/sa1",
        "resource_type": "Microsoft.Storage/storageAccounts",
        "resource": {"name": "sa1"},
    }
    finding = rule_to_finding(rule, resource=resource)
    assert finding["rule_name"] == "Transaction metrics are missing for this storage account."
    assert finding["rule_name"] != "metric_transactions_missing"


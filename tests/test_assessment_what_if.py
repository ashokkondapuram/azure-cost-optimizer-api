"""Tests for assessment what-if scenarios and Key Vault consolidation."""

from __future__ import annotations

import json
import pathlib

import pytest

from app.assessment.runtime import evaluate_assessment_rules, rule_applies_to_resource, rule_to_finding
from app.assessment.what_if import (
    _merge_template_impacts,
    build_what_if_index,
    build_what_if_scenario,
    lookup_what_if_scenario,
)

DATA = pathlib.Path(__file__).resolve().parents[1] / "data"


def test_build_what_if_scenario_stop_or_delete():
    rule = {
        "id": "disk_delete_unattached",
        "recommendation": "Delete unattached managed disk.",
        "recommendationAction": "stop_or_delete",
    }
    scenario = build_what_if_scenario(rule)
    assert scenario["action"] == "stop_or_delete"
    assert scenario["reversible"] is False
    assert scenario["prerequisites"]
    assert scenario["performanceImpact"]["direction"] == "degraded"
    assert scenario["reliabilityImpact"]["direction"] == "degraded"


def test_merge_template_impacts_backfills_legacy_scenario():
    legacy = {
        "ruleId": "disk_delete_unattached",
        "action": "stop_or_delete",
        "title": "Delete disk",
    }
    merged = _merge_template_impacts(dict(legacy))
    assert merged["performanceImpact"]["before"]
    assert merged["reliabilityImpact"]["after"]


def test_rule_applies_to_resource_child_scope():
    rule = {
        "id": "metric_secretAgeDays_stale_delete",
        "appliesToResourceTypes": ["Microsoft.KeyVault/vaults/secrets"],
        "condition": {"type": "all", "conditions": []},
    }
    assert rule_applies_to_resource(
        rule,
        "Microsoft.KeyVault/vaults/secrets",
        primary_resource_type="Microsoft.KeyVault/vaults",
    )
    assert not rule_applies_to_resource(
        rule,
        "Microsoft.KeyVault/vaults",
        primary_resource_type="Microsoft.KeyVault/vaults",
    )


def test_rule_to_finding_includes_what_if():
    assessment = {
        "resourceType": "Microsoft.Compute/disks",
        "whatIfScenarios": {
            "disk_delete_unattached": {
                "ruleId": "disk_delete_unattached",
                "action": "stop_or_delete",
                "title": "Delete disk",
            },
        },
    }
    rule = {
        "id": "disk_delete_unattached",
        "pillar": "cost",
        "severity": "high",
        "recommendation": "Delete unattached disk.",
        "recommendationAction": "stop_or_delete",
        "condition": {"type": "all", "conditions": [{"field": "signals.x", "operator": "eq", "value": True}]},
    }
    resource = {"resource_id": "/subscriptions/x/resourcegroups/rg/providers/Microsoft.Compute/disks/d1", "resource_type": "Microsoft.Compute/disks"}
    finding = rule_to_finding(rule, resource=resource, assessment=assessment)
    assert finding["evidence"]["what_if"]["action"] == "stop_or_delete"


def test_keyvault_child_files_removed():
    for name in (
        "keyvault-key-assessment.json",
        "keyvault-secret-assessment.json",
        "keyvault-certificate-assessment.json",
    ):
        assert not (DATA / name).exists(), f"{name} should be consolidated"


def test_keyvault_index_points_to_single_file():
    index = json.loads((DATA / "assessment-index.json").read_text(encoding="utf-8"))
    kv_items = [
        item for item in index.get("items") or []
        if str(item.get("resourceType", "")).startswith("Microsoft.KeyVault/vaults")
    ]
    files = {item["assessmentFile"] for item in kv_items}
    assert "keyvault-assessment.json" in files
    assert "keyvault-key-assessment.json" not in files


@pytest.mark.parametrize("path", sorted(DATA.glob("*-assessment.json"))[:5])
def test_sample_assessments_have_what_if(path):
    if path.name == "assessment-case-matrix.json":
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    scenarios = data.get("whatIfScenarios") or {}
    rules = data.get("recommendationRules") or []
    if not rules:
        pytest.skip("no recommendation rules")
    first_id = rules[0]["id"]
    assert first_id in scenarios or lookup_what_if_scenario(data, first_id, rule=rules[0])

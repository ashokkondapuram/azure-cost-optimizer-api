"""Tests for assessment JSON integration inside sub-engines."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.assessment.bridge import resource_to_assessment_record, assessment_dict_to_extended_finding
from app.optimizer.platform.runtime.base import ResourceSubEngine
from app.optimizer.platform.runtime.context import AnalysisContext


class _DiskLikeSubEngine(ResourceSubEngine):
    component = "Managed Disks"
    bucket_keys = ("disks",)

    def analyze(self, buckets):
        return []


def test_resource_to_assessment_record_builds_metrics_and_cost():
    ctx = AnalysisContext(
        subscription_id="sub-a",
        rules={},
        cost_by_resource={"/subscriptions/sub-a/resourcegroups/rg/providers/microsoft.compute/disks/d1": 12.5},
        vm_metrics={},
        node_metrics={},
        resource_metrics={},
        resource_facts={
            "/subscriptions/sub-a/resourcegroups/rg/providers/microsoft.compute/disks/d1": {
                "avg_iops": 4.0,
            }
        },
        global_config={},
    )
    resource = {
        "id": "/subscriptions/sub-a/resourcegroups/rg/providers/microsoft.compute/disks/d1",
        "name": "d1",
        "location": "eastus",
        "tags": {"owner": "team-a"},
        "properties": {"diskSizeGB": 128},
        "_technical_facts": {"sku": "Premium_LRS"},
        "_canonical_type": "compute/disk",
        "_resource_elements": {
            "cost": {"monthly_usd": 12.5},
            "runtime": {"metrics_available": True},
        },
    }

    record = resource_to_assessment_record(resource, ctx)
    assert record["resource_id"].endswith("/disks/d1")
    assert record["cost"]["monthly_cost_usd"] == 12.5
    assert record["metrics"]["avg_iops"] == 4.0
    assert "signals" in record


def test_sub_engine_evaluates_assessment_json_rules(monkeypatch):
    assessment = {
        "_file": "disk-assessment.json",
        "recommendationRules": [
            {
                "id": "disk_orphan",
                "severity": "high",
                "enabled": True,
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
        vm_metrics={},
        node_metrics={},
        resource_metrics={},
        resource_facts={},
        global_config={},
    )
    engine = _DiskLikeSubEngine(MagicMock(), ctx)
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
    assert len(findings) == 1
    assert findings[0].rule_id == "disk_orphan"
    assert findings[0].evidence.get("rule_source") == "assessment_json"


def test_assessment_dict_to_extended_finding_maps_string_confidence():
    finding = assessment_dict_to_extended_finding(
        {
            "rule_id": "kv_soft_delete",
            "severity": "medium",
            "detail": "Enable soft delete",
            "evidence": {"confidence": "medium"},
        },
        subscription_id="sub-a",
        resource={"id": "/subscriptions/sub-a/resourcegroups/rg/providers/microsoft.keyvault/vaults/kv1", "name": "kv1"},
    )
    assert finding.confidence_score == 70


def test_assessment_dict_to_extended_finding_maps_high_and_low_confidence():
    high = assessment_dict_to_extended_finding(
        {"rule_id": "r1", "evidence": {"confidence": "high"}},
        subscription_id="sub-a",
        resource={"id": "/subscriptions/sub-a/rg/r/providers/microsoft.compute/disks/d1", "name": "d1"},
    )
    low = assessment_dict_to_extended_finding(
        {"rule_id": "r2", "evidence": {"confidence": "low"}},
        subscription_id="sub-a",
        resource={"id": "/subscriptions/sub-a/rg/r/providers/microsoft.compute/disks/d2", "name": "d2"},
    )
    assert high.confidence_score == 85
    assert low.confidence_score == 50

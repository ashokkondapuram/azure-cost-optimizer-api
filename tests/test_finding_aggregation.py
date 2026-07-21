"""Tests for resource-level finding aggregation."""

from app.finding_aggregation import aggregate_findings_by_resource


def _finding(**kwargs):
    base = {
        "id": "f1",
        "subscription_id": "sub-a",
        "resource_id": "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        "resource_name": "disk-1",
        "resource_type": "Microsoft.Compute/disks",
        "rule_id": "DISK_UNUSED_EXTENDED",
        "rule_name": "Unused disk",
        "category": "STORAGE",
        "severity": "MEDIUM",
        "estimated_savings_usd": 10.0,
        "waste_score": 40,
        "confidence_score": 70,
        "detail": "Disk appears unused",
        "recommendation": "Delete unused disk",
        "evidence": {},
        "status": "open",
        "detected_at": "2026-01-01T00:00:00Z",
    }
    base.update(kwargs)
    return base


def test_aggregate_findings_by_resource_keeps_single_rule():
    findings = [_finding(id="f1")]
    result = aggregate_findings_by_resource(findings)
    assert len(result) == 1
    assert result[0]["id"] == "f1"
    assert "aggregated" not in result[0]


def test_aggregate_findings_by_resource_groups_three_rules_same_resource():
    resource_id = "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/disks/d1"
    findings = [
        _finding(id="f1", rule_id="DISK_UNUSED_EXTENDED", severity="MEDIUM", estimated_savings_usd=10),
        _finding(id="f2", rule_id="DISK_PREMIUM_TIER", severity="HIGH", estimated_savings_usd=20),
        _finding(id="f3", rule_id="DISK_OLD_SNAPSHOT", severity="LOW", estimated_savings_usd=5),
    ]
    for row in findings:
        row["resource_id"] = resource_id

    result = aggregate_findings_by_resource(findings)
    assert len(result) == 1
    grouped = result[0]
    assert grouped["aggregated"] is True
    assert grouped["recommendation_count"] == 3
    assert grouped["rule_id"] == "DISK_PREMIUM_TIER"
    assert grouped["severity"] == "HIGH"
    assert grouped["estimated_savings_usd"] == 35.0
    assert len(grouped["recommendations"]) == 3
    assert set(grouped["child_finding_ids"]) == {"f1", "f2", "f3"}
    assert grouped["recommendations"][0]["rule_id"] == "DISK_PREMIUM_TIER"


def test_aggregate_findings_by_resource_keeps_different_resources_separate():
    findings = [
        _finding(
            id="f1",
            resource_id="/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        ),
        _finding(
            id="f2",
            rule_id="DISK_PREMIUM_TIER",
            resource_id="/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/disks/d2",
        ),
    ]
    result = aggregate_findings_by_resource(findings)
    assert len(result) == 2

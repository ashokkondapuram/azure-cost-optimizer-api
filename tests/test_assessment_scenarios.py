"""End-to-end scenario tests for assessment JSON rule evaluation."""

from __future__ import annotations

from app.assessment.catalog import get_assessment_for_arm_type
from app.assessment.normalizer import build_normalized_record
from app.assessment.runtime import evaluate_assessment_rules, rule_to_finding
from app.assessment.what_if import lookup_what_if_scenario


def _base_row(
    *,
    arm_type: str,
    name: str,
    location: str = "eastus",
    sku: str = "",
    monthly_cost: float = 100.0,
) -> dict:
    return {
        "subscription_id": "sub",
        "resource_id": f"/subscriptions/sub/resourceGroups/rg/providers/{arm_type}/{name}",
        "resource_name": name,
        "resource_type": arm_type,
        "resource_group": "rg",
        "location": location,
        "sku": sku,
        "state": "Active",
        "properties": {"sku": sku} if sku else {},
        "tags": {"Environment": "prod"},
        "monthly_cost_usd": monthly_cost,
    }


def test_servicebus_premium_rightsize_scenario():
    assessment = get_assessment_for_arm_type("Microsoft.ServiceBus/namespaces")
    assert assessment is not None

    record = build_normalized_record(
        _base_row(arm_type="Microsoft.ServiceBus/namespaces", name="sb-premium", sku="Premium"),
        metrics={"incoming_messages": 50, "avg_cpu_pct": 5, "avg_memory_pct": 5},
        assessment=assessment,
    )
    assert record["signals"]["premiumUnderutilized"] is True

    matched = evaluate_assessment_rules(assessment, record, exclude_investigate=True)
    rule_ids = {rule["id"] for rule in matched}
    assert "servicebus_premium_rightsize" in rule_ids

    rule = next(rule for rule in matched if rule["id"] == "servicebus_premium_rightsize")
    finding = rule_to_finding(rule, resource=record, assessment=assessment)
    what_if = finding["evidence"]["what_if"]
    assert what_if["action"] == "downgrade"
    assert finding["evidence"]["signals"]["premiumUnderutilized"] is True


def test_servicebus_deadletter_and_throttle_scenarios():
    assessment = get_assessment_for_arm_type("Microsoft.ServiceBus/namespaces")
    assert assessment is not None

    record = build_normalized_record(
        _base_row(arm_type="Microsoft.ServiceBus/namespaces", name="sb-busy", sku="Premium"),
        metrics={
            "incoming_messages": 500,
            "deadletter_messages": 12,
            "throttledrequests": 4,
            "avg_cpu_pct": 20,
            "avg_memory_pct": 25,
        },
        assessment=assessment,
    )
    matched = evaluate_assessment_rules(assessment, record, exclude_investigate=True)
    rule_ids = {rule["id"] for rule in matched}
    # Reliability rules are Advisor-sourced; performance throttle rule stays in JSON.
    assert "servicebus_deadletter_high" not in rule_ids
    assert "servicebus_throttle_or_errors" in rule_ids

    throttle_rule = next(rule for rule in matched if rule["id"] == "servicebus_throttle_or_errors")
    finding = rule_to_finding(throttle_rule, resource=record, assessment=assessment)
    assert finding["evidence"]["signals"]["throttledOrServerErrors"] is True


def test_servicebus_unapproved_region_migration_scenario():
    assessment = get_assessment_for_arm_type("Microsoft.ServiceBus/namespaces")
    assert assessment is not None

    record = build_normalized_record(
        _base_row(arm_type="Microsoft.ServiceBus/namespaces", name="sb-eastus", location="eastus", sku="Standard"),
        metrics={"incoming_messages": 200},
        assessment=assessment,
    )
    assert record["signals"]["regionApproved"] is False
    assert record["signals"]["recommendedRegion"] == "canadacentral"

    matched = evaluate_assessment_rules(assessment, record, exclude_investigate=True)
    assert "best_unapproved_region" in {rule["id"] for rule in matched}

    rule = next(rule for rule in matched if rule["id"] == "best_unapproved_region")
    finding = rule_to_finding(rule, resource=record, assessment=assessment)
    what_if = finding["evidence"]["what_if"]
    assert what_if["recommendedTargetRegion"] == "canadacentral"
    assert what_if["proposedState"]["region"] == "canadacentral"
    assert finding["evidence"]["signals"]["recommendedRegionDisplay"] == "Canada Central"


def test_disk_unattached_delete_scenario():
    assessment = get_assessment_for_arm_type("Microsoft.Compute/disks")
    assert assessment is not None

    record = build_normalized_record(
        _base_row(arm_type="Microsoft.Compute/disks", name="disk1", monthly_cost=25.0),
        metrics={},
        assessment=assessment,
    )
    record["properties"]["diskState"] = "Unattached"

    matched = evaluate_assessment_rules(assessment, record, exclude_investigate=True)
    assert "disk_delete_unattached" in {rule["id"] for rule in matched}

    rule = next(rule for rule in matched if rule["id"] == "disk_delete_unattached")
    scenario = lookup_what_if_scenario(assessment, rule["id"], rule=rule, resource=record)
    assert scenario is not None
    assert scenario["action"] == "stop_or_delete"


def test_disk_unapproved_region_migration_scenario():
    assessment = get_assessment_for_arm_type("Microsoft.Compute/disks")
    assert assessment is not None

    record = build_normalized_record(
        _base_row(arm_type="Microsoft.Compute/disks", name="disk-eastus", location="eastus"),
        metrics={},
        assessment=assessment,
    )
    assert record["signals"]["regionApproved"] is False
    assert record["signals"]["recommendedRegion"] == "canadacentral"

    matched = evaluate_assessment_rules(assessment, record, exclude_investigate=True)
    assert "best_unapproved_region" in {rule["id"] for rule in matched}

    rule = next(rule for rule in matched if rule["id"] == "best_unapproved_region")
    finding = rule_to_finding(rule, resource=record, assessment=assessment)
    assert finding["evidence"]["what_if"]["recommendedTargetRegion"] == "canadacentral"
    assert "eastus" in finding["recommendation"].lower()
    assert "canada central" in finding["recommendation"].lower()
    assert finding["evidence"]["recommendation_action"] == "migrate_region"
    assert finding["rule_name"] == "Move from East US to Canada Central"


def test_storage_account_region_and_cost_signals():
    assessment = get_assessment_for_arm_type("Microsoft.Storage/storageAccounts")
    assert assessment is not None

    record = build_normalized_record(
        _base_row(arm_type="Microsoft.Storage/storageAccounts", name="sa1", location="westeurope"),
        metrics={"transactions": 1000, "avg_cpu_pct": 10},
        assessment=assessment,
    )
    signals = record["signals"]
    assert signals["regionApproved"] is False
    assert signals["recommendedRegion"] == "canadacentral"
    assert "performanceSaturated" in signals
    assert "lowUtilization" in signals

    matched = evaluate_assessment_rules(assessment, record, exclude_investigate=True)
    assert "best_unapproved_region" in {rule["id"] for rule in matched}

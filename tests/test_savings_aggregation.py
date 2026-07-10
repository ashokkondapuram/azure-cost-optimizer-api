"""Tests for cross-source savings aggregation."""
from __future__ import annotations

from types import SimpleNamespace

from app.savings_aggregation import (
    SavingsActionClass,
    aggregate_findings_savings,
    classify_advisor_recommendation,
    classify_engine_finding,
    resolve_resource_savings,
)


def _advisor(summary: str, savings: float = 100.0) -> SimpleNamespace:
    return SimpleNamespace(
        status="Active",
        category="Cost",
        summary=summary,
        description="",
        recommendation_id="rec-1",
        potential_savings_monthly=savings,
    )


def _finding(rule_id: str, savings: float, **kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        status="open",
        rule_id=rule_id,
        rule_name=kwargs.get("rule_name", rule_id),
        category=kwargs.get("category", "COST"),
        detail=kwargs.get("detail", ""),
        recommendation=kwargs.get("recommendation", ""),
        estimated_savings_usd=savings,
        evidence_json=kwargs.get("evidence_json", "{}"),
        resource_id=kwargs.get("resource_id", "/subscriptions/s/rg/vm1"),
    )


def test_classify_decommission_advisor_and_engine():
    assert classify_advisor_recommendation(_advisor("Shut down or delete the virtual machine")) == SavingsActionClass.DECOMMISSION
    assert classify_engine_finding(_finding("VM_IDLE", 400.0)) == SavingsActionClass.DECOMMISSION


def test_classify_rightsize_engine():
    assert classify_engine_finding(_finding("VM_SKU_SIZING_EXTENDED", 120.0)) == SavingsActionClass.RIGHTSIZE


def test_resolve_resource_does_not_sum_duplicate_decommission():
    breakdown = resolve_resource_savings(
        resource_id="/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        advisor_recs=[_advisor("Shut down underutilized virtual machine", 500.0)],
        findings=[_finding("VM_IDLE", 480.0)],
    )
    assert breakdown.unified_monthly == 500.0
    assert breakdown.advisor_raw_monthly == 500.0
    assert breakdown.engine_raw_monthly == 480.0
    assert "decommission" in breakdown.overlap_action_classes


def test_decommission_supersedes_rightsize_on_same_resource():
    breakdown = resolve_resource_savings(
        resource_id="/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        advisor_recs=[_advisor("Delete idle virtual machine", 600.0)],
        findings=[
            _finding("VM_SKU_SIZING_EXTENDED", 180.0),
            _finding("VM_IDLE", 550.0),
        ],
    )
    assert breakdown.unified_monthly == 600.0
    assert "rightsize" not in breakdown.by_action_class


def test_rightsize_kept_when_no_decommission():
    breakdown = resolve_resource_savings(
        resource_id="/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        advisor_recs=[_advisor("Right-size virtual machine to a smaller SKU", 150.0)],
        findings=[_finding("VM_SKU_SIZING_EXTENDED", 120.0)],
    )
    assert breakdown.unified_monthly == 150.0
    assert breakdown.by_action_class.get("rightsize") == 150.0


def test_engine_savings_kept_when_advisor_savings_missing():
    """Advisor SKU alignment must not zero engine-computed savings."""
    breakdown = resolve_resource_savings(
        resource_id="/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        advisor_recs=[_advisor("Right-size virtual machine to a smaller SKU", 0.0)],
        findings=[_finding("VM_SKU_SIZING_EXTENDED", 122.0)],
    )
    assert breakdown.unified_monthly == 122.0
    assert breakdown.engine_raw_monthly == 122.0
    assert breakdown.advisor_raw_monthly == 0.0


def test_aggregate_findings_savings_dedupes_per_resource():
    findings = [
        _finding("VM_IDLE", 300.0, resource_id="/subscriptions/s/rg/vm1"),
        _finding("VM_OVERSIZE", 80.0, resource_id="/subscriptions/s/rg/vm1"),
    ]
    result = aggregate_findings_savings(findings)
    assert result["total_estimated_savings_usd"] == 300.0
    assert result["raw_total_estimated_savings_usd"] == 380.0
    assert result["double_count_avoided_usd"] == 80.0

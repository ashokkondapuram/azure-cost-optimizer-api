"""Tests for finding quality ranking and filtering."""

from __future__ import annotations

from types import SimpleNamespace

from app.finding_quality import (
    filter_valuable_findings,
    finding_value_score,
    is_valuable_finding,
)


def _finding(**kwargs):
    defaults = {
        "id": "f1",
        "rule_id": "VM_UNDERUTILIZED_EXTENDED",
        "rule_name": "VM underutilized",
        "category": "COMPUTE",
        "severity": "HIGH",
        "estimated_savings_usd": 120.0,
        "confidence_score": 82,
        "waste_score": 75,
        "evidence_json": '{"data_quality":"full_monitor","sizing_action":"downgrade"}',
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_rightsizing_with_monitor_is_valuable():
    finding = _finding()
    assert is_valuable_finding(finding) is True
    assert finding_value_score(finding) >= 48


def test_governance_tag_noise_is_filtered():
    finding = _finding(
        rule_id="VM_MISSING_GOVERNANCE_TAGS",
        rule_name="Missing tags",
        category="GOVERNANCE",
        severity="LOW",
        estimated_savings_usd=0,
        confidence_score=70,
        waste_score=20,
        evidence_json="{}",
    )
    assert is_valuable_finding(finding) is False
    assert filter_valuable_findings([finding]) == []


def test_high_savings_low_confidence_still_ranked():
    finding = _finding(
        estimated_savings_usd=85.0,
        confidence_score=58,
        waste_score=60,
    )
    assert is_valuable_finding(finding) is True


def test_filter_valuable_findings_limits_and_orders():
    low = _finding(
        id="low",
        estimated_savings_usd=5,
        confidence_score=40,
        waste_score=25,
        severity="INFO",
        category="GOVERNANCE",
        rule_id="STORAGE_MISSING_TAGS_EXTENDED",
        evidence_json="{}",
    )
    high = _finding(id="high", estimated_savings_usd=200, confidence_score=90, waste_score=88)
    medium = _finding(id="medium", estimated_savings_usd=60, confidence_score=70, waste_score=65)
    ranked = filter_valuable_findings([low, high, medium], limit=2)
    assert [f.id for f in ranked] == ["high", "medium"]

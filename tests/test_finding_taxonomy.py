"""Tests for finding taxonomy helpers."""

from app.finding_taxonomy import (
    build_ordered_breakdown,
    category_from_resource_type,
    format_category_label,
    sort_findings_by_priority,
)


def test_sort_findings_by_priority_orders_severity_then_savings():
    findings = [
        {"severity": "LOW", "estimated_savings_usd": 500, "detected_at": "2026-01-02"},
        {"severity": "HIGH", "estimated_savings_usd": 10, "detected_at": "2026-01-03"},
        {"severity": "HIGH", "estimated_savings_usd": 90, "detected_at": "2026-01-01"},
    ]
    ordered = sort_findings_by_priority(findings)
    assert [row["severity"] for row in ordered] == ["HIGH", "HIGH", "LOW"]
    assert ordered[0]["estimated_savings_usd"] == 90


def test_build_ordered_breakdown_returns_stable_category_order():
    rows = build_ordered_breakdown(
        {"STORAGE": 2, "COMPUTE": 5, "NETWORK": 1},
        savings={"STORAGE": 10, "COMPUTE": 100, "NETWORK": 0},
        kind="category",
    )
    assert [row["key"] for row in rows] == ["COMPUTE", "STORAGE", "NETWORK"]
    assert rows[0]["label"] == "Compute"
    assert rows[0]["estimated_savings_usd"] == 100.0


def test_category_from_resource_type_maps_canonical_prefix():
    assert category_from_resource_type("compute/vm") == "COMPUTE"
    assert category_from_resource_type("containers/managed_cluster") == "KUBERNETES"
    assert format_category_label("governance") == "Governance"

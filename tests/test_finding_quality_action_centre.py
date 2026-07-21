"""Tests for action-centre finding filters."""

from app.finding_quality import filter_action_centre_findings, is_action_centre_finding


def test_is_action_centre_finding_excludes_metric_gap_rules():
    finding = {
        "rule_id": "metric_transactions_missing",
        "evidence": {"rule_source": "assessment_json", "recommendation_action": "downgrade"},
    }
    assert is_action_centre_finding(finding) is False


def test_is_action_centre_finding_includes_actionable_recommendations():
    finding = {
        "rule_id": "storage_archive_candidate",
        "evidence": {"rule_source": "assessment_json", "recommendation_action": "downgrade"},
    }
    assert is_action_centre_finding(finding) is True


def test_filter_action_centre_findings():
    findings = [
        {"rule_id": "metric_transactions_missing", "evidence": {}},
        {"rule_id": "VM_IDLE", "evidence": {}},
    ]
    filtered = filter_action_centre_findings(findings)
    assert [f["rule_id"] for f in filtered] == ["VM_IDLE"]


def test_is_action_centre_finding_excludes_vmss():
    finding = {
        "rule_id": "VMSS_AUTOSCALE_TUNING",
        "resource_id": (
            "/subscriptions/sub-a/resourceGroups/MC_rg/providers/"
            "Microsoft.Compute/virtualMachineScaleSets/aks-system-vmss"
        ),
        "resource_type": "compute/vmss",
    }
    assert is_action_centre_finding(finding) is False

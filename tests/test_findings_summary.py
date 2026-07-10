"""Tests for findings summary aggregation."""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.findings_summary import build_findings_summary
from app.models import Base, OptimizationFinding, RecommendationExecution


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _finding(**kwargs):
    defaults = {
        "id": str(uuid.uuid4()),
        "run_id": "run-1",
        "rule_id": "RULE",
        "rule_name": "Rule",
        "category": "COMPUTE",
        "severity": "HIGH",
        "resource_id": "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1",
        "resource_name": "vm-1",
        "resource_type": "compute/vm",
        "subscription_id": "sub-1",
        "detail": "Detail",
        "recommendation": "Fix",
        "status": "open",
    }
    defaults.update(kwargs)
    return OptimizationFinding(**defaults)


def test_build_findings_summary_counts_status_severity_and_type(db_session):
    db_session.add_all([
        _finding(id="f1", severity="HIGH", estimated_savings_usd=50.0, status="open"),
        _finding(id="f2", severity="MEDIUM", estimated_savings_usd=0.0, status="acknowledged", category="SECURITY"),
        _finding(id="f3", severity="LOW", estimated_savings_usd=None, status="resolved", category="NETWORK",
                 rule_id="IP_UNASSOCIATED",
                 resource_id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip-1"),
    ])
    db_session.commit()

    summary = build_findings_summary(db_session, "sub-1")

    assert summary["total_findings"] == 2
    assert summary["open_findings"] == 1
    assert summary["by_status"]["open"] == 1
    assert summary["by_status"]["acknowledged"] == 1
    assert summary["by_status"]["implemented"] == 0
    assert summary["by_severity"]["HIGH"] == 1
    assert "MEDIUM" not in summary["by_severity"]
    assert summary["by_category"]["COMPUTE"] == 1
    assert "SECURITY" not in summary["by_category"]
    assert summary["with_savings_findings"] == 1
    assert summary["governance_findings"] == 2
    assert summary["total_estimated_savings_usd"] == 50.0


def test_build_findings_summary_rightsizing_evidence_counts_as_cost_optimization(db_session):
    db_session.add(
        _finding(
            id="f-rightsize",
            rule_id="CUSTOM_RULE",
            estimated_savings_usd=0.0,
            status="open",
            evidence_json='{"sizing_action": "downgrade", "current_sku": "Standard_D4s_v3"}',
        )
    )
    db_session.commit()

    summary = build_findings_summary(db_session, "sub-1")

    assert summary["cost_optimization_findings"] == 1
    assert summary["governance_findings"] == 0


def test_build_findings_summary_excludes_superseded_resolved(db_session):
    resource_id = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"
    db_session.add_all([
        _finding(
            id="open-1",
            rule_id="VM_IDLE",
            resource_id=resource_id,
            status="open",
        ),
        _finding(
            id="resolved-old",
            rule_id="VM_IDLE",
            resource_id=resource_id,
            status="resolved",
        ),
        _finding(
            id="resolved-real",
            rule_id="DISK_UNATTACHED",
            resource_id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-1",
            status="resolved",
        ),
    ])
    db_session.commit()

    summary = build_findings_summary(db_session, "sub-1")

    assert summary["open_findings"] == 1
    assert summary["by_status"]["implemented"] == 0
    assert summary["total_findings"] == 1


def test_build_findings_summary_implemented_counts_execution_logged_findings(db_session):
    finding = _finding(
        id="implemented-1",
        status="resolved",
        rule_id="DISK_UNATTACHED",
        resource_id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-1",
    )
    db_session.add(finding)
    db_session.add(
        RecommendationExecution(
            id="exec-1",
            finding_id="implemented-1",
            executed_by="tester",
            action_type="apply",
        )
    )
    db_session.add(
        _finding(
            id="resolved-only",
            status="resolved",
            rule_id="IP_UNASSOCIATED",
            resource_id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip-1",
        )
    )
    db_session.commit()

    summary = build_findings_summary(db_session, "sub-1")

    assert summary["by_status"]["implemented"] == 1
    assert summary["total_findings"] == 1

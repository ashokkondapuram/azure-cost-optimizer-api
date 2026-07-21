"""Tests for optimization actions and decision engine."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    AdvisorRecommendation,
    Base,
    OptimizationAction,
    OptimizationFinding,
    ResourceSnapshot,
    SubscriptionCache,
)
from app.optimization_actions import (
    bulk_update_optimization_actions,
    evidence_summary_from_row,
    list_optimization_actions,
    serialize_action,
    update_optimization_action,
    _distinct_action_savings,
)
from app.optimizer.decision_engine import generate_optimization_actions


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(SubscriptionCache(subscription_id="sub-1", display_name="Test", state="Enabled"))
    session.commit()
    yield session
    session.close()


def _advisor(**kwargs):
    defaults = dict(
        id=str(uuid.uuid4()),
        recommendation_id="rec-1",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        subscription_id="sub-1",
        category="Cost",
        impact="High",
        summary="Resize VM",
        status="Active",
        generated_at=datetime.now(timezone.utc),
        raw_json={},
    )
    defaults.update(kwargs)
    return AdvisorRecommendation(**defaults)


def _finding(**kwargs):
    defaults = dict(
        id=str(uuid.uuid4()),
        run_id="run-1",
        rule_id="VM_UNDERUTILIZED_EXTENDED",
        rule_name="Underutilized VM",
        category="cost",
        severity="medium",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        resource_name="vm1",
        resource_type="compute/vm",
        subscription_id="sub-1",
        status="open",
        confidence_score=80,
        estimated_savings_usd=100.0,
    )
    defaults.update(kwargs)
    return OptimizationFinding(**defaults)


def test_generate_actions_from_advisor_and_findings(db_session):
    db_session.add(_advisor())
    db_session.add(_finding())
    db_session.commit()

    result = generate_optimization_actions(db_session, "sub-1")
    assert result["created"] == 1
    assert result["by_action_type"]["resize_down"] == 1

    listed = list_optimization_actions(db_session, "sub-1")
    assert listed["total"] == 1
    assert listed["items"][0]["action_type"] == "resize_down"
    assert listed["items"][0]["confidence"] == "High"


def test_generate_actions_stores_json_fields_as_strings(db_session):
    db_session.add(_advisor())
    db_session.add(_finding())
    db_session.commit()

    generate_optimization_actions(db_session, "sub-1")
    action = db_session.query(OptimizationAction).one()

    assert isinstance(action.cost_evidence, str)
    assert isinstance(action.utilization_evidence, str)
    assert isinstance(action.decision_rules_applied, str)
    assert isinstance(action.advisor_finding, str)


def test_manual_review_when_performance_conflict(db_session):
    db_session.add(_advisor(category="Cost", impact="High"))
    db_session.add(_advisor(
        recommendation_id="rec-2",
        category="Performance",
        impact="High",
        summary="Disk latency",
    ))
    db_session.commit()

    result = generate_optimization_actions(db_session, "sub-1")
    assert result["created"] == 1
    action = db_session.query(OptimizationAction).one()
    assert action.action_type == "manual_review"
    assert action.confidence == "Manual review"


def test_list_actions_includes_resource_group_and_filtered_savings(db_session):
    db_session.add(OptimizationAction(
        id="act-1",
        resource_id="/subscriptions/sub-1/resourcegroups/prod-rg/providers/microsoft.compute/virtualmachines/vm1",
        subscription_id="sub-1",
        resource_type="compute/vm",
        resource_name="vm1",
        action_type="resize_down",
        confidence="High",
        performance_risk="Low",
        estimated_monthly_savings=100.0,
        workflow_status="proposed",
    ))
    db_session.add(OptimizationAction(
        id="act-2",
        resource_id="/subscriptions/sub-1/resourcegroups/prod-rg/providers/microsoft.compute/virtualmachines/vm2",
        subscription_id="sub-1",
        resource_type="compute/vm",
        resource_name="vm2",
        action_type="investigate",
        confidence="Medium",
        performance_risk="Low",
        estimated_monthly_savings=50.0,
        workflow_status="approved",
    ))
    db_session.commit()

    listed = list_optimization_actions(db_session, "sub-1", workflow_status="proposed")
    assert listed["total"] == 1
    assert listed["total_estimated_monthly_savings"] == 100.0
    assert listed["page_estimated_monthly_savings"] == 100.0
    assert listed["items"][0]["resource_group"] == "prod-rg"
    assert listed["summary"]["proposed"] == 1
    assert listed["summary"]["approved"] == 1


def test_generate_actions_uses_evidence_backed_action_reason(db_session):
    evidence_json = json.dumps({
        "summary": "VM average CPU is 8.5% (extended idle analysis).",
        "avg_cpu_pct": 8.5,
        "vm_size": "Standard_D4s_v3",
        "suggested_sku": "Standard_D2s_v3",
        "checks": [
            {
                "signal": "Average CPU utilization",
                "value": 8.5,
                "value_display": "8.5%",
                "threshold_display": "≤ 5%",
            }
        ],
        "optimization_metrics": {
            "performance": [
                {"id": "avg_cpu", "label": "Avg CPU", "formatted": "8.5%", "status": "underutilized"},
            ],
        },
    })
    db_session.add(_advisor())
    db_session.add(_finding(evidence_json=evidence_json))
    db_session.commit()

    generate_optimization_actions(db_session, "sub-1")
    action = db_session.query(OptimizationAction).one()

    assert "8.5%" in (action.action_reason or "")
    util = json.loads(action.utilization_evidence) if isinstance(action.utilization_evidence, str) else action.utilization_evidence
    assert util.get("narrative_highlights")
    assert any("CPU" in h.get("label", "") for h in util["narrative_highlights"])


def test_generate_actions_uses_advanced_analysis(db_session):
    db_session.add(_advisor())
    db_session.add(_finding())
    db_session.commit()

    generate_optimization_actions(db_session, "sub-1")
    action = db_session.query(OptimizationAction).one()

    assert action.recommendation_tier is not None
    assert action.overall_score is not None
    cost = json.loads(action.cost_evidence) if isinstance(action.cost_evidence, str) else action.cost_evidence
    util = json.loads(action.utilization_evidence) if isinstance(action.utilization_evidence, str) else action.utilization_evidence
    assert "dimensions" in util
    assert cost.get("overall_score") is not None
    assert action.advisor_finding in ("{}", {}, None) or json.loads(action.advisor_finding or "{}") == {}


def test_combined_evidence_and_evidence_summary(db_session):
    evidence_json = json.dumps({
        "optimization_metrics": {
            "cost": [{"id": "mtd_cost", "label": "MTD cost", "value": 120, "formatted": "$120.00"}],
            "performance": [
                {"id": "avg_cpu", "label": "Avg CPU", "value": 8.5, "formatted": "8.5%", "status": "underutilized"},
            ],
            "data_quality": "azure_monitor",
        },
        "avg_cpu_pct": 8.5,
    })
    db_session.add(_advisor(potential_savings_monthly=75.0))
    db_session.add(_finding(evidence_json=evidence_json, estimated_savings_usd=100.0))
    db_session.commit()

    generate_optimization_actions(db_session, "sub-1")
    action = db_session.query(OptimizationAction).one()
    cost = json.loads(action.cost_evidence) if isinstance(action.cost_evidence, str) else action.cost_evidence
    util = json.loads(action.utilization_evidence) if isinstance(action.utilization_evidence, str) else action.utilization_evidence

    combined = cost.get("combined_evidence") or {}
    assert combined.get("sources_merged") is True
    assert combined.get("has_advisor") is True
    assert combined.get("has_findings") is True
    assert combined.get("advisor_count", 0) >= 1
    assert combined.get("findings_count", 0) >= 1
    assert combined.get("metrics_count", 0) >= 2
    assert util.get("optimization_metrics", {}).get("performance")

    summary = evidence_summary_from_row(action)
    assert summary["has_advisor"] is True
    assert summary["has_findings"] is True
    assert summary["has_metrics"] is True
    assert summary["findings_count"] >= 1
    assert summary["metrics_count"] >= 2

    payload = serialize_action(action)
    assert payload["evidence_summary"]["has_advisor"] is True
    assert payload["evidence_summary"]["has_findings"] is True
    assert payload["evidence_summary"]["has_metrics"] is True

    listed = list_optimization_actions(db_session, "sub-1")
    assert listed["items"][0]["evidence_summary"]["has_advisor"] is True


def test_list_actions_uses_distinct_savings_per_resource(db_session):
    rid = "/subscriptions/sub-1/resourcegroups/prod-rg/providers/microsoft.compute/virtualmachines/vm1"
    db_session.add(OptimizationAction(
        id="act-dup-1",
        resource_id=rid,
        subscription_id="sub-1",
        resource_type="compute/vm",
        resource_name="vm1",
        action_type="resize_down",
        confidence="High",
        performance_risk="Low",
        estimated_monthly_savings=100.0,
        workflow_status="proposed",
    ))
    db_session.add(OptimizationAction(
        id="act-dup-2",
        resource_id=rid.upper(),
        subscription_id="sub-1",
        resource_type="compute/vm",
        resource_name="vm1",
        action_type="investigate",
        confidence="Medium",
        performance_risk="Low",
        estimated_monthly_savings=40.0,
        workflow_status="proposed",
    ))
    db_session.add(OptimizationAction(
        id="act-other",
        resource_id="/subscriptions/sub-1/resourcegroups/prod-rg/providers/microsoft.compute/virtualmachines/vm2",
        subscription_id="sub-1",
        resource_type="compute/vm",
        resource_name="vm2",
        action_type="investigate",
        confidence="Medium",
        performance_risk="Low",
        estimated_monthly_savings=50.0,
        workflow_status="proposed",
    ))
    db_session.commit()

    assert _distinct_action_savings(db_session.query(OptimizationAction).all()) == 150.0

    listed = list_optimization_actions(db_session, "sub-1")
    assert listed["total_estimated_monthly_savings"] == 150.0
    assert listed["distinct_estimated_monthly_savings"] == 150.0


def test_workflow_update_and_bulk(db_session):
    action = OptimizationAction(
        id="act-wf-1",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        subscription_id="sub-1",
        resource_type="compute/vm",
        resource_name="vm1",
        action_type="investigate",
        confidence="Medium",
        performance_risk="Low",
        workflow_status="proposed",
    )
    db_session.add(action)
    db_session.commit()

    update_optimization_action(
        db_session,
        action,
        workflow_status="approved",
        user={"id": "u1", "display_name": "Admin"},
        note="Looks good",
    )
    db_session.commit()

    payload = serialize_action(action)
    assert payload["workflow_status"] == "approved"
    assert len(payload["workflow_history"]) == 1

    bulk_update_optimization_actions(
        db_session,
        subscription_id="sub-1",
        action_ids=["act-wf-1"],
        workflow_status="executed",
        user={"id": "u1", "display_name": "Admin"},
    )
    db_session.refresh(action)
    assert action.workflow_status == "executed"


def test_workflow_note_without_status_change(db_session):
    action = OptimizationAction(
        id="act-note-1",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        subscription_id="sub-1",
        resource_type="compute/vm",
        resource_name="vm1",
        action_type="investigate",
        confidence="Medium",
        performance_risk="Low",
        workflow_status="approved",
    )
    db_session.add(action)
    db_session.commit()

    update_optimization_action(
        db_session,
        action,
        note="Waiting on change window",
        user={"id": "u1", "display_name": "Admin"},
    )
    db_session.commit()

    payload = serialize_action(action)
    assert payload["workflow_status"] == "approved"
    assert len(payload["workflow_history"]) == 1
    assert payload["workflow_history"][0]["event"] == "note"
    assert payload["workflow_history"][0]["note"] == "Waiting on change window"


def test_workflow_owner_change(db_session):
    action = OptimizationAction(
        id="act-owner-1",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        subscription_id="sub-1",
        resource_type="compute/vm",
        resource_name="vm1",
        action_type="investigate",
        confidence="Medium",
        performance_risk="Low",
        workflow_status="proposed",
        owner=None,
    )
    db_session.add(action)
    db_session.commit()

    update_optimization_action(
        db_session,
        action,
        owner="platform-team@example.com",
        user={"id": "u1", "display_name": "Admin"},
    )
    db_session.commit()

    payload = serialize_action(action)
    assert payload["owner"] == "platform-team@example.com"
    assert payload["workflow_history"][0]["event"] == "owner_change"
    assert payload["workflow_history"][0]["owner_to"] == "platform-team@example.com"

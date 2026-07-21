"""Tests for optimization trends summary."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, OptimizationAction, OptimizationRolloutStage, OptimizationScoring, SubscriptionCache
from app.optimization_trends import get_optimization_trends


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


def test_trends_summary(db_session):
    today = date.today().isoformat()
    db_session.add(OptimizationScoring(
        id=str(uuid.uuid4()),
        subscription_id="sub-1",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        evaluation_date=today,
        recommendation_tier="tier1_safe",
        cost_savings_monthly=100.0,
        overall_recommendation_score=80.0,
    ))
    db_session.add(OptimizationRolloutStage(
        id="stage-1",
        subscription_id="sub-1",
        stage_number=1,
        stage_tier="tier1_safe",
        action_ids_json="[]",
        resources_in_stage=2,
        status="completed",
    ))
    db_session.commit()

    result = get_optimization_trends(db_session, "sub-1")
    assert result["resources_scored"] == 1
    assert result["scoring"]["total"] == 1
    assert result["scoring"]["average_score"] == 80.0
    assert result["tier_counts"]["tier1_safe"] == 1
    assert result["total_estimated_monthly_savings"] == 100.0
    assert result["unified_estimated_monthly_savings"] == 0.0
    assert result["distinct_scoreboard_savings"] == 100.0
    assert result["distinct_estimated_monthly_savings"] == 0.0
    assert result["action_pipeline_savings"] == 0.0
    assert result["rollout"]["completed"] == 1
    assert result["rollout"]["success_rate_pct"] == 100.0


def test_pipeline_action_breakdowns(db_session):
    db_session.add(OptimizationAction(
        id="act-1",
        subscription_id="sub-1",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/disks/d1",
        resource_type="compute/disk",
        resource_name="d1",
        action_type="downgrade_disk",
        workflow_status="proposed",
        estimated_monthly_savings=120.0,
    ))
    db_session.add(OptimizationAction(
        id="act-2",
        subscription_id="sub-1",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        resource_type="compute/vm",
        resource_name="vm1",
        action_type="resize_down",
        workflow_status="approved",
        estimated_monthly_savings=80.0,
    ))
    db_session.add(OptimizationAction(
        id="act-3",
        subscription_id="sub-1",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm2",
        resource_type="compute/vm",
        resource_name="vm2",
        action_type="resize_down",
        workflow_status="executed",
        estimated_monthly_savings=50.0,
    ))
    db_session.add(OptimizationAction(
        id="act-4",
        subscription_id="sub-1",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/disks/d2",
        resource_type="compute/disk",
        resource_name="d2",
        action_type="downgrade_disk",
        workflow_status="rejected",
        estimated_monthly_savings=200.0,
    ))
    db_session.commit()

    result = get_optimization_trends(db_session, "sub-1")

    assert result["pipeline_actions_by_status"] == {
        "proposed": 1,
        "approved": 1,
        "executed": 1,
    }
    assert result["actions_by_status"]["rejected"] == 1

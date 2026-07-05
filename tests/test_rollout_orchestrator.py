"""Tests for rollout orchestration."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, OptimizationAction, OptimizationRolloutStage, SubscriptionCache
from app.optimizer.rollout_orchestrator import (
    expand_rollout_stage,
    plan_rollout_stages,
    rollback_rollout_stage,
    serialize_rollout_stage,
    start_rollout_stage,
)


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


def _action(**kwargs):
    defaults = dict(
        id=str(uuid.uuid4()),
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        subscription_id="sub-1",
        resource_type="compute/vm",
        resource_name="vm1",
        action_type="resize_down",
        confidence="High",
        performance_risk="Low",
        workflow_status="proposed",
        recommendation_tier="tier1_safe",
    )
    defaults.update(kwargs)
    return OptimizationAction(**defaults)


def test_plan_rollout_creates_tier1_batch(db_session):
    db_session.add(_action())
    db_session.add(_action(
        id=str(uuid.uuid4()),
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm2",
        resource_name="vm2",
    ))
    db_session.commit()

    result = plan_rollout_stages(db_session, "sub-1")
    assert result["stages_created"] == 1
    stage = db_session.query(OptimizationRolloutStage).one()
    assert stage.stage_tier == "tier1_safe"
    assert stage.resources_in_stage == 2


def test_tier3_one_stage_per_action(db_session):
    for i in range(2):
        db_session.add(_action(
            id=str(uuid.uuid4()),
            resource_id=f"/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm{i}",
            resource_name=f"vm{i}",
            recommendation_tier="tier3_risky",
        ))
    db_session.commit()

    result = plan_rollout_stages(db_session, "sub-1")
    assert result["stages_created"] == 2


def test_start_and_expand_tier1(db_session):
    action = _action()
    db_session.add(action)
    stage = OptimizationRolloutStage(
        id="stage-1",
        subscription_id="sub-1",
        stage_number=1,
        stage_tier="tier1_safe",
        action_ids_json=[action.id],
        resources_in_stage=1,
        observation_window_days=0,
        status="proposed",
    )
    db_session.add(stage)
    db_session.commit()

    start_rollout_stage(db_session, stage, user={"id": "u1", "display_name": "Admin"})
    db_session.commit()
    assert stage.status == "in_progress"
    db_session.refresh(action)
    assert action.workflow_status == "approved"

    result = expand_rollout_stage(db_session, stage, user={"id": "u1"}, force=True)
    assert result["status"] == "completed"
    db_session.refresh(action)
    assert action.workflow_status == "executed"


def test_rollback_rejects_actions(db_session):
    action = _action(workflow_status="approved", recommendation_tier="tier3_risky")
    db_session.add(action)
    stage = OptimizationRolloutStage(
        id="stage-2",
        subscription_id="sub-1",
        stage_number=3,
        stage_tier="tier3_risky",
        action_ids_json=[action.id],
        resources_in_stage=1,
        observation_window_days=14,
        observation_start_date=date.today().isoformat(),
        status="in_progress",
    )
    db_session.add(stage)
    db_session.commit()

    result = rollback_rollout_stage(db_session, stage, reason="CPU spike after resize", user={"id": "u1"})
    assert result["status"] == "rolled_back"
    db_session.refresh(action)
    assert action.workflow_status == "rejected"
    payload = serialize_rollout_stage(stage)
    assert payload["rollback_triggered"] is True

"""Tests for optimization trends summary."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, OptimizationRolloutStage, OptimizationScoring, SubscriptionCache
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
    assert result["rollout"]["completed"] == 1
    assert result["rollout"]["success_rate_pct"] == 100.0

"""Tests for advanced optimization engine scoring."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, SubscriptionCache
from app.optimizer.advanced_engine import assign_recommendation_tier, score_resource, synthesize_overall
from app.optimizer.advanced_engine import DimensionScores
from app.optimizer.workload_profiler import profile_resource


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


def test_tier1_safe_assignment():
    tier = assign_recommendation_tier(
        overall=80.0,
        perf_risk=15.0,
        blast_radius=1,
        compliance_locked=False,
        sla="none",
        monthly_savings=100.0,
    )
    assert tier == "tier1_safe"


def test_blocked_compliance_locked():
    tier = assign_recommendation_tier(
        overall=90.0,
        perf_risk=5.0,
        blast_radius=0,
        compliance_locked=True,
        sla="none",
        monthly_savings=200.0,
    )
    assert tier == "blocked"


def test_blocked_gold_sla():
    tier = assign_recommendation_tier(
        overall=85.0,
        perf_risk=10.0,
        blast_radius=0,
        compliance_locked=False,
        sla="gold",
        monthly_savings=200.0,
    )
    assert tier == "blocked"


def test_synthesize_overall_weighted():
    dims = DimensionScores(cost=100, safety=100, effort=100, workload=100, business=100)
    assert synthesize_overall(dims) == 100.0


def test_score_resource_resize_candidate():
    scorecard = score_resource(
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        resource_name="vm1",
        resource_type="compute/vm",
        monthly_cost=500.0,
        tags={"environment": "dev"},
        facts={"avg_cpu_pct": 8.0, "max_cpu_pct": 15.0},
        workload={
            "workload_type": "steady",
            "burstiness_score": 12.0,
            "utilization_trend": "stable",
            "detected_seasonality": False,
        },
        dependencies={
            "blast_radius": 0,
            "max_criticality": "low",
            "sla_tier": "none",
            "compliance_locked": False,
        },
        trends={"utilization_volatility": 0.05, "confidence_penalty": 0},
        advisor_savings=120.0,
        finding_savings=100.0,
        rule_ids={"VM_UNDERUTILIZED_EXTENDED"},
        has_cost_advisor=True,
        has_perf_advisor=False,
    )
    assert scorecard["primary_action"] == "resize_down"
    assert scorecard["overall_recommendation_score"] > 50
    assert scorecard["recommendation_tier"] in {"tier1_safe", "tier2_balanced", "tier3_risky"}


def test_score_resource_manual_review_on_perf_conflict():
    scorecard = score_resource(
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm2",
        resource_name="vm2",
        resource_type="compute/vm",
        monthly_cost=800.0,
        tags={"environment": "production"},
        facts={"avg_cpu_pct": 45.0, "max_cpu_pct": 92.0},
        workload={
            "workload_type": "bursty",
            "burstiness_score": 55.0,
            "utilization_trend": "increasing",
            "detected_seasonality": True,
        },
        dependencies={
            "blast_radius": 4,
            "max_criticality": "critical",
            "sla_tier": "silver",
            "compliance_locked": False,
        },
        trends={"utilization_volatility": 0.4, "confidence_penalty": 0},
        advisor_savings=200.0,
        finding_savings=0.0,
        rule_ids={"VM_DISK_BOTTLENECK"},
        has_cost_advisor=True,
        has_perf_advisor=True,
    )
    assert scorecard["primary_action"] == "manual_review"
    assert scorecard["performance_risk_score"] >= 40


def test_workload_profiler_steady_vm(db_session):
    from app.models import ResourceSnapshot

    snap = ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id="sub-1",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        resource_name="vm1",
        resource_type="compute/vm",
        tags_json='{"environment":"dev"}',
        monthly_cost_usd=100.0,
        is_active=True,
    )
    db_session.add(snap)
    db_session.commit()

    fields = profile_resource(db_session, snap, {"avg_cpu_pct": 5.0, "max_cpu_pct": 8.0})
    assert fields["workload_type"] in {"steady", "interactive"}
    assert fields["classifier_class"] in {"idle", "zombie", "interactive"}

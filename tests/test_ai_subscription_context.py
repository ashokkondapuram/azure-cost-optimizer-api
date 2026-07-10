"""Tests for AI subscription context enrichment."""

from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai_subscription_context import (
    _NETWORK_SERVICE_PATTERN,
    _STORAGE_SERVICE_PATTERN,
    build_category_cost_analysis,
    build_governance_impact,
    enrich_subscription_context,
    filter_resolved_data_gaps,
)
from app.models import (
    Base,
    CostByResourceSnapshot,
    CostByResourceTypeSnapshot,
    CostByServiceSnapshot,
    OptimizationFinding,
    ResourceSnapshot,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _seed_costs(db_session, sub: str, month: str = "2026-07"):
    db_session.add(CostByResourceTypeSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        arm_resource_type="microsoft.network/publicipaddresses",
        canonical_resource_type="network/publicip",
        month=month,
        cost_usd=40.0,
        cost_billing=50.0,
        billing_currency="CAD",
    ))
    db_session.add(CostByResourceTypeSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        arm_resource_type="microsoft.storage/storageaccounts",
        canonical_resource_type="storage/account",
        month=month,
        cost_usd=120.0,
        cost_billing=150.0,
        billing_currency="CAD",
    ))
    db_session.add(CostByServiceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        service_name="Storage",
        month=month,
        cost_usd=120.0,
        cost_billing=150.0,
        billing_currency="CAD",
    ))
    db_session.add(CostByServiceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        service_name="Virtual Network",
        month=month,
        cost_usd=40.0,
        cost_billing=50.0,
        billing_currency="CAD",
    ))


def test_build_governance_impact_includes_tag_and_spend(db_session):
    sub = "sub-1"
    month = "2026-07"
    rid = f"/subscriptions/{sub}/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1"
    db_session.add(ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        resource_id=rid,
        resource_name="vm1",
        resource_group="rg",
        resource_type="Microsoft.Compute/virtualMachines",
        tags_json="{}",
        is_active=True,
        is_cost_export_only=False,
        synced_at=datetime.now(timezone.utc),
    ))
    db_session.add(OptimizationFinding(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        rule_id="VM_MISSING_GOVERNANCE_TAGS",
        rule_name="Missing governance tags",
        category="GOVERNANCE",
        severity="MEDIUM",
        resource_id=rid,
        resource_name="vm1",
        resource_type="Microsoft.Compute/virtualMachines",
        resource_group="rg",
        detail="Missing tags",
        recommendation="Add tags",
        estimated_savings_usd=0,
        status="open",
        detected_at=datetime.now(timezone.utc),
    ))
    db_session.add(CostByResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        resource_id=rid,
        service_name="Virtual Machines",
        resource_group="rg",
        resource_type="Microsoft.Compute/virtualMachines",
        month=month,
        cost_usd=80.0,
        cost_billing=100.0,
        billing_currency="CAD",
    ))
    db_session.commit()

    out = build_governance_impact(
        db_session,
        sub,
        mtd_pretax=1000.0,
        billing_currency="CAD",
        month=month,
    )

    assert out["open_governance_findings"] == 1
    assert out["mtd_spend_on_governance_flagged_resources"] == 100.0
    assert out["pct_subscription_mtd_on_governance_flagged_resources"] == 10.0
    assert out["non_compliant_resources"] == 1


def test_build_category_cost_analysis_for_network_and_storage(db_session):
    sub = "sub-1"
    month = "2026-07"
    _seed_costs(db_session, sub, month)
    db_session.commit()

    network = build_category_cost_analysis(
        db_session,
        sub,
        domain="network",
        service_pattern=_NETWORK_SERVICE_PATTERN,
        findings=[],
        mtd_pretax=1000.0,
        billing_currency="CAD",
        month=month,
    )
    storage = build_category_cost_analysis(
        db_session,
        sub,
        domain="storage",
        service_pattern=_STORAGE_SERVICE_PATTERN,
        findings=[],
        mtd_pretax=1000.0,
        billing_currency="CAD",
        month=month,
    )

    assert network["mtd_spend_by_resource_type"] == 50.0
    assert storage["mtd_spend_by_resource_type"] == 150.0
    assert network["pct_of_subscription_mtd"] == 5.0
    assert storage["pct_of_subscription_mtd"] == 15.0


def test_filter_resolved_data_gaps():
    context = {
        "governance_impact": {"available": True, "open_governance_findings": 2, "tag_compliance_score_pct": 80},
        "network_cost_analysis": {"available": True, "mtd_spend_by_resource_type": 50},
        "storage_cost_analysis": {"available": True, "mtd_spend_by_resource_type": 150},
    }
    gaps = [
        "No specific data on the impact of governance findings on overall costs.",
        "Lack of detailed cost analysis for network and storage categories.",
        "No reservation coverage data.",
    ]
    kept = filter_resolved_data_gaps(gaps, context)
    assert kept == ["No reservation coverage data."]


def test_enrich_subscription_context_attaches_sections(db_session):
    sub = "sub-1"
    _seed_costs(db_session, sub)
    db_session.commit()
    enriched = enrich_subscription_context(
        db_session,
        sub,
        {"mtd_spend": {"pretax_total": 1000.0, "billing_currency": "CAD"}},
    )
    assert "governance_impact" in enriched
    assert "network_cost_analysis" in enriched
    assert "storage_cost_analysis" in enriched

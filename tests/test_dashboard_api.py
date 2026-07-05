"""Tests for DB-backed dashboard API."""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.dashboard.api import utilization_by_resource_type
from app.dashboard import (
    get_resource_detail,
    get_sync_status,
    get_top_spend,
    list_advisor_recommendations,
    list_underutil_outliers,
)
from app.models import (
    AdvisorRecommendation,
    Base,
    CostSyncRun,
    OptimizationFinding,
    ResourceSnapshot,
    ResourceUtilizationHistory,
    SubscriptionCache,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def dashboard_db_cost_path(monkeypatch):
    """Dashboard API tests assert DB fallbacks — skip live Azure cost bundle."""
    monkeypatch.setattr("app.dashboard.api._live_cost_token", lambda db: None)
    monkeypatch.setattr("app.dashboard.api._enqueue_cost_sync", lambda *a, **k: None)


def _add_resource(db, *, rid, name="vm-1", rtype="compute/vm", cost_usd=0.0):
    db.add(ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id="sub-1",
        resource_id=rid.lower(),
        resource_name=name,
        resource_type=rtype,
        resource_group="rg-1",
        location="eastus",
        sku="Standard_D2s_v3",
        properties_json="{}",
        monthly_cost_usd=cost_usd,
        synced_at=datetime.now(timezone.utc),
    ))


def test_sync_status_reports_inventory_and_cost(db_session):
    sub = "sub-1"
    db_session.add(SubscriptionCache(
        subscription_id=sub,
        display_name="Prod",
        state="Enabled",
        synced_at=datetime.now(timezone.utc),
    ))
    _add_resource(
        db_session,
        rid="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1",
    )
    db_session.add(CostSyncRun(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        month="2026-06",
        mtd_start="2026-06-01",
        mtd_end="2026-06-24",
        total_billing=100.0,
        total_usd=80.0,
        billing_currency="USD",
        synced_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    status = get_sync_status(db_session, sub)
    assert status["inventory"]["resource_count"] == 1
    assert status["inventory"]["status"] == "success"
    assert status["cost"]["total_usd"] == 80.0
    assert status["cost"]["total_billing"] == 100.0
    assert status["cost"]["billing_currency"] == "USD"
    assert status["cost"]["status"] == "success"


def test_resource_detail_includes_open_findings(db_session):
    rid = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"
    _add_resource(db_session, rid=rid, name="vm-1")
    db_session.add(OptimizationFinding(
        id=str(uuid.uuid4()),
        run_id="run-1",
        rule_id="VM_IDLE",
        rule_name="Idle VM",
        category="COMPUTE",
        severity="HIGH",
        resource_id=rid.lower(),
        resource_name="vm-1",
        resource_type="compute/vm",
        subscription_id="sub-1",
        detail="Low CPU",
        recommendation="Resize",
        estimated_savings_usd=50.0,
        evidence_json=json.dumps({"optimization_metrics": {"performance": [
            {"id": "avg_cpu", "formatted": "2.1%"},
        ]}}),
        status="open",
    ))
    db_session.commit()

    detail = get_resource_detail(db_session, "sub-1", rid)
    assert detail is not None
    assert detail["name"] == "vm-1"
    assert detail["open_findings_count"] == 1


def test_top_spend_orders_by_cost(db_session):
    from app.cost_db import month_for_timeframe
    from app.models import CostByResourceTypeSnapshot

    sub = "sub-1"
    month = month_for_timeframe("MonthToDate")
    for arm_type, cost in (
        ("microsoft.compute/disks", 120.0),
        ("microsoft.storage/storageaccounts", 45.0),
        ("microsoft.compute/virtualmachines", 200.0),
    ):
        db_session.add(CostByResourceTypeSnapshot(
            id=str(uuid.uuid4()),
            subscription_id=sub,
            arm_resource_type=arm_type,
            canonical_resource_type="compute/disk",
            month=month,
            cost_usd=cost,
            cost_billing=cost,
            billing_currency="CAD",
        ))
    db_session.commit()

    result = get_top_spend(db_session, sub, limit=2, timeframe="MonthToDate")
    assert len(result["items"]) == 2
    assert result["granularity"] == "resource_type"
    assert result["items"][0]["cost_billing"] >= result["items"][1]["cost_billing"]


def test_underutil_outliers_filters_idle_rules(db_session):
    rid = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"
    db_session.add(OptimizationFinding(
        id=str(uuid.uuid4()),
        run_id="run-1",
        rule_id="VM_IDLE",
        rule_name="Idle VM",
        category="COMPUTE",
        severity="HIGH",
        resource_id=rid.lower(),
        resource_name="vm-1",
        resource_type="compute/vm",
        subscription_id="sub-1",
        detail="Idle",
        recommendation="Stop",
        estimated_savings_usd=80.0,
        waste_score=90,
        status="open",
    ))
    db_session.add(OptimizationFinding(
        id=str(uuid.uuid4()),
        run_id="run-1",
        rule_id="BUDGET_THRESHOLD",
        rule_name="Budget",
        category="COST",
        severity="MEDIUM",
        resource_id="",
        resource_name="",
        resource_type="",
        subscription_id="sub-1",
        detail="Budget",
        recommendation="Review",
        estimated_savings_usd=10.0,
        status="open",
    ))
    db_session.commit()

    result = list_underutil_outliers(db_session, "sub-1", limit=5)
    assert result["count"] == 1
    assert result["items"][0]["rule_id"] == "VM_IDLE"


def test_advisor_lists_open_findings(db_session):
    db_session.add(OptimizationFinding(
        id=str(uuid.uuid4()),
        run_id="run-1",
        rule_id="DISK_UNATTACHED",
        rule_name="Unattached disk",
        category="COMPUTE",
        severity="HIGH",
        resource_id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        resource_name="d1",
        resource_type="compute/disk",
        subscription_id="sub-1",
        detail="Unattached",
        recommendation="Delete",
        estimated_savings_usd=25.0,
        status="open",
    ))
    db_session.commit()

    result = list_advisor_recommendations(db_session, "sub-1", limit=10)
    assert result["count"] == 1
    assert result["total_estimated_savings_usd"] == 25.0


def test_dashboard_overview_aggregates_sections(db_session):
    from app.dashboard import get_dashboard_overview, get_findings_summary_db

    sub = "sub-1"
    rid = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"
    _add_resource(db_session, rid=rid, name="vm-1", cost_usd=10.0)
    db_session.add(OptimizationFinding(
        id=str(uuid.uuid4()),
        run_id="run-1",
        rule_id="VM_IDLE",
        rule_name="Idle VM",
        category="COMPUTE",
        severity="HIGH",
        resource_id=rid.lower(),
        resource_name="vm-1",
        resource_type="compute/vm",
        subscription_id=sub,
        detail="Idle",
        recommendation="Stop",
        estimated_savings_usd=40.0,
        status="open",
    ))
    db_session.commit()

    summary = get_findings_summary_db(db_session, sub)
    assert summary["open_findings"] == 1
    assert summary["by_severity"]["HIGH"] == 1

    overview = get_dashboard_overview(db_session, sub)
    assert overview["data_source"] == "postgresql"
    assert overview["sync"]["inventory"]["resource_count"] == 1
    assert overview["optimization"]["summary"]["open_findings"] == 1
    assert "counts" in overview["inventory"]
    assert "points" in overview["cost"]["daily"]
    assert "ytd" in overview["cost"]
    assert overview["cost"]["ytd"]["billing_currency"] == "CAD"
    assert overview["portal"]["kpis"]
    assert len(overview["portal"]["panels"]) == 4
    assert "subtitle" not in overview["portal"]
    kpi_ids = {k["id"] for k in overview["portal"]["kpis"]}
    assert "open_findings" in kpi_ids
    assert "advisor_findings" in kpi_ids
    assert "estimated_savings" in kpi_ids
    savings_kpi = next(k for k in overview["portal"]["kpis"] if k["id"] == "estimated_savings")
    assert savings_kpi["value"] == 40.0
    assert savings_kpi["currency"] == "CAD"
    findings_kpi = next(k for k in overview["portal"]["kpis"] if k["id"] == "open_findings")
    assert findings_kpi["value"] == 1
    assert findings_kpi["href"] == "/optimization-hub?tab=recommendations"
    assert overview["portal"]["hero_actions"]
    assert any(a["id"] == "recommendations" for a in overview["portal"]["hero_actions"])
    for panel in overview["portal"]["panels"].values():
        assert "description" not in panel
    assert overview["portal"]["panels"]["resource_health_status"]["segments"]
    assert "token" in overview["sync"]


def test_utilization_by_resource_type_from_findings(db_session):
    rid = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"
    db_session.add(OptimizationFinding(
        id=str(uuid.uuid4()),
        run_id="run-1",
        rule_id="NETWORK_VNET_EMPTY",
        rule_name="Empty VNet",
        category="NETWORK",
        severity="MEDIUM",
        resource_id=rid.lower(),
        resource_name="vm-1",
        resource_type="compute/vm",
        subscription_id="sub-1",
        detail="Low CPU",
        recommendation="Review",
        estimated_savings_usd=0.0,
        status="open",
        evidence_json=json.dumps({
            "optimization_metrics": {
                "performance": [
                    {"id": "avg_cpu_pct", "formatted": "4.2%", "status": "underutilized"},
                ],
            },
        }),
    ))
    db_session.commit()

    items = utilization_by_resource_type(db_session, "sub-1")
    assert len(items) == 1
    assert items[0]["count"] == 1
    assert items[0]["utilization_label"] == "4.2%"


def test_utilization_by_resource_type_falls_back_to_open_findings(db_session):
    db_session.add(OptimizationFinding(
        id=str(uuid.uuid4()),
        run_id="run-1",
        rule_id="STORAGE_TIER",
        rule_name="Storage tier",
        category="STORAGE",
        severity="LOW",
        resource_id="/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.storage/storageaccounts/sa1",
        resource_name="sa1",
        resource_type="storage/account",
        subscription_id="sub-1",
        detail="Review tier",
        recommendation="Review",
        estimated_savings_usd=5.0,
        status="open",
        evidence_json="{}",
    ))
    db_session.commit()

    items = utilization_by_resource_type(db_session, "sub-1")
    assert len(items) == 1
    assert items[0]["count"] == 1
    assert items[0]["utilization_label"] == "Open findings"


def test_utilization_by_resource_type_from_history(db_session):
    rid = "/subscriptions/sub-1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm-1"
    db_session.add(ResourceSnapshot(
        id=str(uuid.uuid4()),
        subscription_id="sub-1",
        resource_id=rid,
        resource_name="vm-1",
        resource_type="compute/vm",
        resource_group="rg",
        location="eastus",
    ))
    db_session.add(ResourceUtilizationHistory(
        id=str(uuid.uuid4()),
        subscription_id="sub-1",
        resource_id=rid.lower(),
        metric_name="avg_cpu_pct",
        snapshot_date="2026-06-30",
        value_avg=12.5,
        period_days=7,
    ))
    db_session.commit()

    items = utilization_by_resource_type(db_session, "sub-1")
    assert len(items) == 1
    assert items[0]["count"] == 1
    assert items[0]["utilization_label"] == "12.5%"
    assert items[0]["avg_utilization_pct"] == 12.5


def test_advisor_findings_kpi_in_portal(db_session):
    from app.dashboard.api import get_advisor_findings_summary, get_dashboard_overview

    sub = "sub-advisor-kpi"
    db_session.add(SubscriptionCache(
        subscription_id=sub,
        display_name="Test Sub",
        tenant_id="tenant-1",
    ))
    rid = f"/subscriptions/{sub}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"
    _add_resource(db_session, rid=rid)
    db_session.add(AdvisorRecommendation(
        id=str(uuid.uuid4()),
        recommendation_id="rec-1",
        resource_id=rid.lower(),
        subscription_id=sub,
        category="Cost",
        impact="High",
        summary="Resize VM",
        potential_savings_monthly=120.0,
        status="Active",
        generated_at=datetime.now(timezone.utc),
        synced_at=datetime.now(timezone.utc),
    ))
    db_session.add(AdvisorRecommendation(
        id=str(uuid.uuid4()),
        recommendation_id="rec-2",
        resource_id=rid.lower(),
        subscription_id=sub,
        category="HighAvailability",
        impact="Medium",
        summary="Enable zone redundancy",
        status="Active",
        generated_at=datetime.now(timezone.utc),
        synced_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    summary = get_advisor_findings_summary(db_session, sub)
    assert summary["active_count"] == 2
    assert summary["high_impact"] == 1
    assert summary["total_savings_monthly"] == 120.0

    overview = get_dashboard_overview(db_session, sub)
    advisor_kpi = next(k for k in overview["portal"]["kpis"] if k["id"] == "advisor_findings")
    assert advisor_kpi["value"] == 2
    assert advisor_kpi["href"] == "/optimization-hub?tab=advisor"
    assert "high impact" in advisor_kpi["sub"]
    assert overview["optimization"]["advisor"]["active_count"] == 2


def test_dashboard_overview_prefers_db_costs_over_live(db_session, monkeypatch):
    from app.dashboard import get_dashboard_overview
    from datetime import date

    monkeypatch.setattr("app.dashboard.api._live_cost_token", lambda db: "fake-token")

    def _live_should_not_win(*args, **kwargs):
        return {"pretax_total": 9999.0, "cost_usd_total": 9999.0, "source": "azure"}

    monkeypatch.setattr("app.dashboard.api.query_cost_summary_live", _live_should_not_win)
    monkeypatch.setattr("app.dashboard.api.query_daily_costs_live", _live_should_not_win)
    monkeypatch.setattr("app.dashboard.api._enqueue_cost_sync", lambda *a, **k: None)

    sub = "sub-live-off"
    month = date.today().strftime("%Y-%m")
    db_session.add(CostSyncRun(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        month=month,
        mtd_start=f"{month}-01",
        mtd_end=date.today().isoformat(),
        total_billing=250.0,
        total_usd=200.0,
        billing_currency="CAD",
        services_json="[]",
        changes_json="[]",
        synced_at=datetime.now(timezone.utc),
    ))
    _add_resource(
        db_session,
        rid="/subscriptions/sub-live-off/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1",
        cost_usd=5.0,
    )
    db_session.commit()

    overview = get_dashboard_overview(db_session, sub)
    assert overview["data_source"] == "postgresql"
    assert overview["cost"]["summary"]["pretax_total"] == 250.0
    assert overview["cost"]["summary"]["source"] == "database"

"""Tests for new cost-export waste rules and dashboard monthly trend KPI."""

from __future__ import annotations

from app.cost_export_recommendations import analyze_cost_export_resources
from app.dashboard.api import _monthly_cost_trend_from_points
from app.optimizer.component_map import resolve_batches
from app.optimizer.extended_engine import ExtendedOptimizationEngine


def _row(**kwargs):
    base = {
        "id": "/subscriptions/sub/resourcegroups/rg/providers/microsoft.test/resource/r1",
        "name": "r1",
        "type": "compute/vm",
        "monthlyCostBilling": 0,
        "monthlyCostUsd": 0,
        "properties": {},
    }
    base.update(kwargs)
    return base


def test_idle_app_service_plan_rule():
    rows = [
        _row(
            id="/subscriptions/sub/resourcegroups/rg/providers/microsoft.web/serverfarms/plan1",
            name="plan1",
            type="appservice/plan",
            monthlyCostBilling=180.0,
            properties={"numberOfSites": 0, "armResourceType": "microsoft.web/serverfarms"},
        ),
    ]
    findings = analyze_cost_export_resources("sub-id", rows)
    assert any(f["rule_id"] == "IDLE_APP_SERVICE_PLANS" for f in findings)


def test_unused_nic_rule():
    rows = [
        _row(
            id="/subscriptions/sub/resourcegroups/rg/providers/microsoft.network/networkinterfaces/nic1",
            name="nic1",
            type="network/nic",
            monthlyCostBilling=12.0,
            properties={"virtualMachine": None, "armResourceType": "microsoft.network/networkinterfaces"},
        ),
    ]
    findings = analyze_cost_export_resources("sub-id", rows)
    assert any(f["rule_id"] == "UNUSED_NIC" for f in findings)


def test_idle_nat_gateway_rule():
    rows = [
        _row(
            id="/subscriptions/sub/resourcegroups/rg/providers/microsoft.network/natgateways/nat1",
            name="nat1",
            type="network/nat",
            monthlyCostBilling=32.0,
            properties={"subnets": [], "armResourceType": "microsoft.network/natgateways"},
        ),
    ]
    findings = analyze_cost_export_resources("sub-id", rows)
    assert any(f["rule_id"] == "IDLE_NAT_GATEWAY" for f in findings)


def test_idle_db_flexible_server_rule():
    rows = [
        _row(
            id="/subscriptions/sub/resourcegroups/rg/providers/microsoft.dbforpostgresql/flexibleservers/pg1",
            name="pg1",
            type="database/postgresql",
            monthlyCostBilling=45.0,
            properties={"state": "Stopped", "armResourceType": "microsoft.dbforpostgresql/flexibleservers"},
        ),
    ]
    findings = analyze_cost_export_resources("sub-id", rows)
    assert any(f["rule_id"] == "IDLE_DB_FLEXIBLE_SERVER" for f in findings)


def test_networking_extended_batch_present():
    batches = resolve_batches(["Networking Extended"])
    assert len(batches) == 1
    assert batches[0]["buckets"] == [
        "vnets", "private_endpoints", "private_link_services", "private_dns_zones",
    ]


def test_extended_engine_analyzes_private_dns_zone():
    engine = ExtendedOptimizationEngine()
    zone = {
        "id": "/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net",
        "name": "privatelink.blob.core.windows.net",
        "type": "network/privatedns",
        "properties": {"numberOfRecordSets": 2},
    }
    result = engine.analyze(
        subscription_id="sub",
        private_dns_zones=[zone],
    )
    assert any(f["rule_id"] == "PRIVATE_DNS_EMPTY_EXTENDED" for f in result["findings"])


def test_private_dns_empty_threshold_override():
    zone = {
        "id": "/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net",
        "name": "privatelink.blob.core.windows.net",
        "type": "network/privatedns",
        "properties": {"numberOfRecordSets": 3},
    }
    default_engine = ExtendedOptimizationEngine()
    default_result = default_engine.analyze(subscription_id="sub", private_dns_zones=[zone])
    assert not any(f["rule_id"] == "PRIVATE_DNS_EMPTY_EXTENDED" for f in default_result["findings"])

    raised_engine = ExtendedOptimizationEngine(
        rule_overrides={"PRIVATE_DNS_EMPTY_EXTENDED": {"private_dns_max_default_record_sets": 3}},
    )
    raised_result = raised_engine.analyze(subscription_id="sub", private_dns_zones=[zone])
    assert any(f["rule_id"] == "PRIVATE_DNS_EMPTY_EXTENDED" for f in raised_result["findings"])


def test_private_dns_evidence_reflects_record_set_threshold():
    from app.finding_evidence import build_rule_evidence

    evidence = build_rule_evidence(
        "PRIVATE_DNS_EMPTY_EXTENDED",
        {
            "record_set_count": 1,
            "private_dns_max_default_record_sets": 3,
            "determination": "empty_dns_zone",
        },
    )
    record_check = next(c for c in evidence["checks"] if c["signal"] == "Record sets")
    assert record_check["value"] == 1
    assert record_check["threshold"] == "> 3"
    assert record_check["passed"] is False


def test_monthly_cost_trend_projects_vs_last_month():
    import calendar
    from datetime import date, timedelta

    today = date.today()
    current_key = today.strftime("%Y-%m")
    last_key = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    points = [
        {"date": f"{last_key}-01", "cost_billing": 100.0},
        {"date": f"{last_key}-15", "cost_billing": 100.0},
        {"date": f"{current_key}-01", "cost_billing": 50.0},
        {"date": f"{current_key}-15", "cost_billing": 50.0},
    ]
    trend = _monthly_cost_trend_from_points(points, mtd_amount=100.0)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_elapsed = max(1, today.day)
    assert trend["last_month"] == 200.0
    assert trend["projected"] == round(100.0 * (days_in_month / days_elapsed), 2)
    assert trend["delta_pct"] is not None


def test_weekly_cost_differs_from_mtd_projection():
    from app.dashboard.api import _monthly_cost_trend_from_points, _weekly_cost_from_daily_points

    points = [
        {"date": "2026-07-01", "cost_billing": 40.0},
        {"date": "2026-07-02", "cost_billing": 35.0},
        {"date": "2026-07-03", "cost_billing": 30.0},
        {"date": "2026-07-04", "cost_billing": 25.0},
        {"date": "2026-07-05", "cost_billing": 20.0},
        {"date": "2026-07-06", "cost_billing": 15.0},
        {"date": "2026-07-07", "cost_billing": 10.0},
        {"date": "2026-06-24", "cost_billing": 12.0},
        {"date": "2026-06-25", "cost_billing": 12.0},
        {"date": "2026-06-26", "cost_billing": 12.0},
        {"date": "2026-06-27", "cost_billing": 12.0},
        {"date": "2026-06-28", "cost_billing": 12.0},
        {"date": "2026-06-29", "cost_billing": 12.0},
        {"date": "2026-06-30", "cost_billing": 12.0},
    ]
    weekly = _weekly_cost_from_daily_points(points)
    trend = _monthly_cost_trend_from_points(points, mtd_amount=175.0)
    assert weekly["amount"] == 175.0
    assert trend["projected"] != weekly["amount"]

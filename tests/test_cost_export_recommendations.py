"""Tests for cost-export-based optimization recommendations."""

from app.cost_export_recommendations import (
    COST_EXPORT_RULES,
    analyze_cost_export_resources,
)
from app.finding_evidence import enrich_evidence
from app.resource_type_map import internal_resource_type


def _row(**kwargs):
    base = {
        "id": "/subscriptions/sub/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
        "name": "vm1",
        "type": "compute/vm",
        "monthlyCostBilling": 0,
        "monthlyCostUsd": 0,
        "azureServiceName": "",
        "properties": {},
    }
    base.update(kwargs)
    return base


def test_log_analytics_maps_to_monitoring_type():
    rid = (
        "/subscriptions/x/resourcegroups/rg/providers/"
        "microsoft.operationalinsights/workspaces/log-ws"
    )
    assert internal_resource_type(rid) == "monitoring/loganalytics"


def test_high_spend_finding_generated():
    rows = [_row(monthlyCostBilling=600.0, name="big-vm")]
    findings = analyze_cost_export_resources("sub-id", rows)
    rule_ids = {f["rule_id"] for f in findings}
    assert "COST_HIGH_SPEND_REVIEW" in rule_ids


def test_log_analytics_ingestion_rule():
    rid = (
        "/subscriptions/x/resourcegroups/rg/providers/"
        "microsoft.operationalinsights/workspaces/log-ws"
    )
    rows = [
        _row(
            id=rid,
            name="log-ws",
            type="monitoring/loganalytics",
            monthlyCostBilling=120.0,
            azureServiceName="Log Analytics",
            properties={"armResourceType": "microsoft.operationalinsights/workspaces"},
        )
    ]
    findings = analyze_cost_export_resources("sub-id", rows)
    assert any(f["rule_id"] == "LOG_ANALYTICS_INGESTION" for f in findings)


def test_cost_export_only_governance_rule():
    rows = [
        _row(
            monthlyCostBilling=50.0,
            costExportOnly=True,
            name="orphan-disk",
            type="compute/disk",
        )
    ]
    findings = analyze_cost_export_resources("sub-id", rows)
    assert any(f["rule_id"] == "COST_EXPORT_ONLY_RESOURCE" for f in findings)


def test_one_rule_per_resource():
    rows = [
        _row(
            monthlyCostBilling=800.0,
            costExportOnly=True,
            azureServiceName="Log Analytics",
            type="monitoring/loganalytics",
        )
    ]
    findings = analyze_cost_export_resources("sub-id", rows)
    assert len(findings) == 1


def test_all_cost_rules_have_unique_ids():
    ids = [r.id for r in COST_EXPORT_RULES]
    assert len(ids) == len(set(ids))


def test_bandwidth_review_does_not_apply_to_vmss():
    vmss_rid = (
        "/subscriptions/sub/resourcegroups/rg/providers/"
        "microsoft.compute/virtualmachinescalesets/vmss-prod"
    )
    rows = [
        _row(
            id=vmss_rid,
            name="vmss-prod",
            type="compute/vmss",
            monthlyCostBilling=120.0,
            billingServiceName="Bandwidth",
            azureServiceName="Virtual Machine Scale Sets",
        )
    ]
    findings = analyze_cost_export_resources("sub-id", rows)
    assert not any(f["rule_id"] == "BANDWIDTH_REVIEW" for f in findings)


def test_bandwidth_review_applies_to_nat_gateway():
    nat_rid = (
        "/subscriptions/sub/resourcegroups/rg/providers/"
        "microsoft.network/natgateways/nat-prod"
    )
    rows = [
        _row(
            id=nat_rid,
            name="nat-prod",
            type="network/nat",
            monthlyCostBilling=150.0,
            billingServiceName="Bandwidth",
            properties={"armResourceType": "microsoft.network/natgateways"},
        )
    ]
    findings = analyze_cost_export_resources("sub-id", rows)
    assert any(f["rule_id"] == "BANDWIDTH_REVIEW" for f in findings)


def test_log_analytics_rule_does_not_apply_to_vm_with_billing_service_name():
    rows = [
        _row(
            monthlyCostBilling=120.0,
            billingServiceName="Log Analytics",
            azureServiceName="Virtual Machines",
            type="compute/vm",
        )
    ]
    findings = analyze_cost_export_resources("sub-id", rows)
    assert not any(f["rule_id"] == "LOG_ANALYTICS_INGESTION" for f in findings)


def test_cost_export_evidence_prioritizes_cost_over_missing_inventory():
    rows = [
        _row(
            monthlyCostBilling=1888.28,
            azureServiceName="SQL Database",
            type="database/sql",
            id="/subscriptions/sub/resourcegroups/rg/providers/Microsoft.Sql/servers/myserver",
            name="myserver",
        )
    ]
    finding = analyze_cost_export_resources("sub-id", rows)[0]
    ev = enrich_evidence(finding["rule_id"], finding["evidence"], finding)
    by_signal = {c["signal"]: c for c in ev["checks"]}
    cost_ids = {m["id"]: m for m in ev["optimization_metrics"]["cost"]}

    assert cost_ids["mtd_cost"]["formatted"] == "$1,888.28"
    assert cost_ids["mtd_cost"]["status"] == "above_threshold"
    assert cost_ids["azure_service"]["status"] == "informational"
    assert by_signal["ARM resource type"]["passed"] is True
    assert cost_ids["azure_service"]["value"] == "SQL Database"
    assert "Location" not in by_signal or by_signal["Location"]["status"] == "na"
    assert "SKU" not in by_signal or by_signal["SKU"]["status"] == "na"
    assert "optimization_metrics" in ev
    assert ev["optimization_metrics"]["component"] == "cost/export"
    perf_ids = {m["id"] for m in ev["optimization_metrics"]["performance"]}
    assert "sku" not in perf_ids or all(m.get("status") != "unavailable" for m in ev["optimization_metrics"]["performance"] if m["id"] == "sku")
    assert "arm_resource_type" in perf_ids

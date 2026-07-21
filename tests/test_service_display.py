"""Tests for shared service display formatting across all IT services."""

from app.finding_evidence import build_rule_evidence
from app.resource_utilization import is_low_storage_utilization
from app.service_display import (
    azure_service_display_name,
    format_access_tier,
    format_replication_sku,
    format_service_fact,
    format_storage_fact,
    make_service_check,
    make_storage_check,
    missing_display,
    resolve_canonical_type,
)


def test_missing_vs_zero_cpu_all_services():
    assert format_service_fact("compute/vm", "avg_cpu_pct", None) == missing_display("compute/vm")
    assert format_service_fact("compute/vm", "avg_cpu_pct", 0) == "0% CPU"
    assert format_service_fact("containers/aks", "cluster_cpu_pct", 0) == "0% cluster CPU"
    assert format_service_fact("database/redis", "api_hits", None) == missing_display()


def test_missing_vs_zero_storage():
    assert format_storage_fact("used_capacity_bytes", None) == missing_display("storage/account")
    assert format_storage_fact("used_capacity_bytes", 0) == "0 GB used"
    assert format_storage_fact("transaction_count", None) == missing_display("storage/account")
    assert format_storage_fact("transaction_count", 0) == "0 transactions"


def test_replication_and_tier_labels():
    assert format_access_tier("Hot") == "Hot"
    assert "geo-redundant" in format_replication_sku("STANDARD_GRS").lower()


def test_low_storage_utilization_distinguishes_missing_and_zero():
    assert is_low_storage_utilization({"_technical_facts": {"used_capacity_bytes": None}}) is None
    assert is_low_storage_utilization({"_technical_facts": {"used_capacity_bytes": 0}}) is False
    assert is_low_storage_utilization({"_technical_facts": {"storage_pct": 10}}) is True


def test_make_storage_check_missing_is_not_synced():
    check = make_storage_check("Monthly egress", "egress_bytes", None, "≥ 100 GB/month", passed=False)
    assert check["status"] == "na"
    assert check["value_display"] == missing_display("storage/account")


def test_make_storage_check_formats_bytes():
    check = make_storage_check(
        "Monthly egress",
        "egress_bytes",
        200_000_000_000,
        "≥ 100 GB/month",
        passed=True,
    )
    assert "GB" in check["value_display"]
    assert check["threshold_display"] == "≥ 100 GB/month"


def test_resolve_canonical_from_rule_prefix():
    assert resolve_canonical_type("", "VM_IDLE") == "compute/vm"
    assert resolve_canonical_type("", "COSMOS_THROTTLING_DETECTED") == "database/cosmosdb"
    assert resolve_canonical_type("network/nat", "") == "network/nat"


def test_make_service_check_missing_is_not_synced():
    check = make_service_check(
        "compute/vm",
        "Average CPU utilization",
        "avg_cpu_pct",
        None,
        "≤ 5%",
        passed=False,
    )
    assert check["status"] == "na"
    assert check["value_display"] == missing_display("compute/vm")


def test_vm_idle_evidence_has_human_checks():
    out = build_rule_evidence(
        "VM_IDLE",
        {"avg_cpu_pct": 2.1, "cpu_threshold_pct": 5},
        finding={"resource_type": "compute/vm"},
    )
    cpu_check = next(c for c in out["checks"] if "CPU" in c["signal"])
    assert cpu_check["value_display"] == "2.1%"
    assert "5" in cpu_check["threshold_display"]


def test_aks_evidence_missing_metric():
    out = build_rule_evidence(
        "AKS_IDLE_POOL_EXTENDED",
        {"idle_nodes": None, "node_count": 3},
        finding={"resource_type": "containers/aks"},
    )
    idle_check = next((c for c in out.get("checks", []) if c.get("fact_key") == "idle_nodes"), None)
    if idle_check:
        assert idle_check.get("value_display") == missing_display("containers/aks")


def test_azure_service_display_name_prefers_billing():
    assert azure_service_display_name(
        azure_service_name="Virtual Machines",
        canonical_type="compute/vm",
    ) == "Virtual Machines"


def test_azure_service_display_name_from_canonical_type():
    assert azure_service_display_name(
        azure_service_name=None,
        canonical_type="compute/disk",
    ) == "Managed Disks"


def test_azure_service_display_name_from_arm_type():
    assert azure_service_display_name(
        azure_service_name="",
        arm_type="microsoft.compute/disks",
    ) == "Managed Disks"


def test_azure_service_display_name_from_resource_id():
    rid = (
        "/subscriptions/abc/resourceGroups/rg/providers/"
        "Microsoft.OperationalInsights/workspaces/logs"
    )
    assert azure_service_display_name(
        azure_service_name=None,
        resource_id=rid,
    ) == "Monitoring"


def test_azure_service_display_name_stub_analytics_type():
    assert azure_service_display_name(
        azure_service_name=None,
        canonical_type="analytics/databricks",
    ) == "Analytics"

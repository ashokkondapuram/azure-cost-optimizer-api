"""Tests for per-resource Azure Monitor utilization metric registry."""

from app.resources import (
    RESOURCE_MONITOR_PROFILES,
    get_monitor_profile,
    get_technical_fetch_spec,
    monitor_arm_type,
    profiles_for_canonical,
)


SQL_DB_ID = (
    "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Sql/servers/sqlsrv/databases/appdb"
)
SQL_SERVER_ID = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Sql/servers/sqlsrv"
WEBAPP_ID = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Web/sites/myapp"
WEBAPP_PLAN_ID = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Web/serverFarms/plan1"


def test_monitor_arm_type_detects_sql_database():
    assert monitor_arm_type(SQL_DB_ID) == "microsoft.sql/servers/databases"
    assert monitor_arm_type(SQL_SERVER_ID) == "microsoft.sql/servers"


def test_sql_server_has_no_monitor_profile():
    assert get_monitor_profile(SQL_SERVER_ID, "database/sql") is None


def test_sql_database_has_cpu_percent_metrics():
    profile = get_monitor_profile(SQL_DB_ID, "database/sql")
    assert profile is not None
    names = set(profile.metric_names())
    assert "cpu_percent" in names
    assert "storage_percent" in names


def test_webapp_and_plan_use_different_metrics():
    webapp = get_monitor_profile(WEBAPP_ID, "appservice/webapp")
    plan = get_monitor_profile(WEBAPP_PLAN_ID, "appservice/plan")
    assert webapp is not None and plan is not None
    assert "CpuTime" in webapp.metric_names()
    assert "CpuPercentage" in plan.metric_names()
    assert "CpuPercentage" not in webapp.metric_names()


def test_technical_fetch_specs_receive_registry_metrics():
    vm = get_technical_fetch_spec("compute/vm")
    assert any(m.metric_name == "Percentage CPU" for m in vm.usage_metrics)
    assert all(m.source == "azure_monitor" for m in vm.usage_metrics if m.fact_key == "avg_cpu_pct")

    sql = get_technical_fetch_spec("database/sql")
    sql_metrics = {m.metric_name for m in sql.usage_metrics if m.source == "azure_monitor"}
    assert "cpu_percent" in sql_metrics

    log = get_technical_fetch_spec("monitoring/loganalytics")
    sources = {m.source for m in log.usage_metrics}
    assert "azure_monitor" in sources
    assert "cost_export" in sources


def test_all_profiles_have_unique_arm_types():
    assert len(RESOURCE_MONITOR_PROFILES) == len({p.monitor_arm_type for p in RESOURCE_MONITOR_PROFILES.values()})


def test_new_generic_types_have_monitor_profiles():
    for canonical in (
        "messaging/eventhub",
        "messaging/servicebus",
        "integration/apim",
        "search/cognitivesearch",
        "analytics/adx",
    ):
        assert profiles_for_canonical(canonical), canonical


def test_enrich_derived_vm_memory_percent():
    from app.monitor_metrics import enrich_derived_monitor_facts

    resource = {
        "properties": {"hardwareProfile": {"vmSize": "Standard_D4s_v3"}},
    }
    payload = {
        "value": [
            {
                "name": {"value": "Percentage CPU"},
                "timeseries": [{"data": [{"average": 8.0}]}],
            },
            {
                "name": {"value": "Available Memory Bytes"},
                "timeseries": [{"data": [{"average": 13 * 1024**3}]}],
            },
        ],
    }
    facts = enrich_derived_monitor_facts(resource, "compute/vm", {}, payload)
    assert facts["avg_cpu_pct"] == 8.0
    assert facts["avg_memory_pct"] is not None
    assert 15 < facts["avg_memory_pct"] < 35


def test_analysis_inventory_buckets_include_vmss():
    from app.metrics_loader import analysis_inventory_buckets, group_resources_by_canonical_type

    vmss = [{
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachineScaleSets/myvmss",
        "type": "compute/vmss",
    }]
    buckets = analysis_inventory_buckets(vmss=vmss, public_ips=[{"id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip1"}])
    grouped = group_resources_by_canonical_type(buckets)
    assert "compute/vmss" in grouped
    assert "network/publicip" in grouped

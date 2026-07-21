"""Tests for spec-driven Azure Monitor metrics loading."""

from app.monitor_metrics import (
    average_from_monitor_payload,
    extract_monitor_facts,
    metric_value_from_monitor_payload,
    monitor_fetch_plan,
)
from app.resources import get_technical_fetch_spec


def _payload(cpu: float, memory_bytes: float) -> dict:
    return {
        "value": [
            {
                "name": {"value": "Percentage CPU"},
                "timeseries": [{"data": [{"average": cpu}]}],
            },
            {
                "name": {"value": "Available Memory Bytes"},
                "timeseries": [{"data": [{"average": memory_bytes}]}],
            },
        ]
    }


def test_average_from_monitor_payload():
    assert average_from_monitor_payload(_payload(42.5, 0), "Percentage CPU") == 42.5


def test_extract_monitor_facts_for_vm():
    spec = get_technical_fetch_spec("compute/vm")
    facts = extract_monitor_facts(_payload(15.0, 8 * 1024**3), spec)
    assert facts["avg_cpu_pct"] == 15.0


def test_monitor_fetch_plan_covers_major_types():
    plan = monitor_fetch_plan()
    assert "compute/vm" in plan
    assert "appservice/webapp" in plan
    assert "database/redis" in plan
    assert "storage/account" in plan
    webapp_metrics = {m["name"] for m in plan["appservice/webapp"]["metrics"]}
    assert "CpuTime" in webapp_metrics
    assert "Requests" in webapp_metrics
    assert "AverageMemoryWorkingSet" in webapp_metrics
    assert "CpuPercentage" not in webapp_metrics
    assert any(m["name"] == "CpuPercentage" for m in plan["appservice/plan"]["metrics"])
    disk_metrics = {m["name"] for m in plan["compute/disk"]["metrics"]}
    assert "Composite Disk Read Bytes/sec" in disk_metrics
    assert "Composite Disk Write Bytes/sec" in disk_metrics
    assert "Composite Disk Read Operations/sec" in disk_metrics
    assert "Composite Disk Write Operations/sec" in disk_metrics
    assert "DiskPaidBurstIOPS" in disk_metrics
    assert "Disk Queue Depth" not in disk_metrics
    assert "Used Size Percentage" not in disk_metrics
    agw_plan = plan["network/appgateway"]
    agw_names = {m["name"] for m in agw_plan["metrics"]}
    assert "TotalRequests" in agw_names
    assert "Throughput" in agw_names
    assert "Total" in agw_plan["aggregations"]


def test_metric_value_from_monitor_payload_prefers_total():
    payload = {
        "value": [
            {
                "name": {"value": "TotalRequests"},
                "timeseries": [{"data": [{"total": 42}, {"total": 58}]}],
            },
        ],
    }
    assert metric_value_from_monitor_payload(payload, "TotalRequests", aggregation="Total") == 100


def test_metric_value_from_monitor_payload_uses_maximum():
    payload = {
        "value": [
            {
                "name": {"value": "Percentage CPU"},
                "timeseries": [{"data": [{"maximum": 12.0}, {"maximum": 48.5}, {"maximum": 31.0}]}],
            },
        ],
    }
    assert metric_value_from_monitor_payload(payload, "Percentage CPU", aggregation="Maximum") == 48.5


def test_monitor_fetch_plan_includes_maximum_aggregation():
    plan = monitor_fetch_plan()
    assert "Maximum" in plan["compute/vm"]["aggregations"]


def test_extract_monitor_facts_skips_memory_bytes_as_pct():
    spec = get_technical_fetch_spec("compute/vm")
    facts = extract_monitor_facts(_payload(15.0, 8 * 1024**3), spec)
    assert facts.get("avg_cpu_pct") == 15.0
    assert "avg_mem_pct" not in facts


def test_extract_monitor_facts_for_webapp():
    spec = get_technical_fetch_spec("appservice/webapp")
    payload = {
        "value": [
            {
                "name": {"value": "CpuTime"},
                "timeseries": [{"data": [{"total": 900.0}]}],
            },
            {
                "name": {"value": "AverageMemoryWorkingSet"},
                "timeseries": [{"data": [{"average": 128 * 1024**2}]}],
            },
            {
                "name": {"value": "Requests"},
                "timeseries": [{"data": [{"total": 250.0}]}],
            },
        ],
    }
    facts = extract_monitor_facts(payload, spec)
    assert facts["cpu_time_sec"] == 900.0
    assert facts["avg_memory_bytes"] == 128 * 1024**2
    assert facts["request_count"] == 250.0


def test_group_resources_by_canonical_type():
    from app.metrics_loader import group_resources_by_canonical_type

    grouped = group_resources_by_canonical_type({
        "vms": [{"id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"}],
        "redis_caches": [{"id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Cache/redis/cache1"}],
        "postgresql": [{"id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.DBforPostgreSQL/flexibleServers/pg1"}],
    })
    assert "compute/vm" in grouped
    assert "database/redis" in grouped
    assert "database/postgresql" in grouped


def test_monitor_fetch_plan_includes_redis_analysis_metrics():
    plan = monitor_fetch_plan()
    redis = plan["database/redis"]
    names = {m["name"] for m in redis["metrics"]}
    assert "usedmemorypercentage" in names
    assert "cachehits" in names
    assert "cachemisses" in names
    assert "operationsPerSecond" in names
    assert "serverLoad" in names
    assert "evictedkeys" in names
    assert "connectedclients" in names
    assert "cachemissrate" in names
    assert "cachehitrate" not in names
    assert "Maximum" in redis["aggregations"]
    assert "Total" in redis["aggregations"]


def test_enrich_derived_monitor_facts_computes_redis_hit_rate():
    from app.monitor_metrics import enrich_derived_monitor_facts

    resource = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Cache/redis/cache1",
        "sku": {"family": "Premium", "capacity": 1},
    }
    facts = {"cache_hits": 800.0, "cache_misses": 200.0, "memory_pct": 42.0}
    enriched = enrich_derived_monitor_facts(resource, "database/redis", facts, metrics={})
    assert enriched["cache_hit_rate"] == 80.0


def test_extract_monitor_facts_for_redis_profile():
    from app.monitor_metrics import extract_monitor_facts_from_profile
    from app.resources.registry import get_monitor_profile

    profile = get_monitor_profile(
        "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Cache/redis/cache1",
        "database/redis",
    )
    payload = {
        "value": [
            {"name": {"value": "usedmemorypercentage"}, "timeseries": [{"data": [{"maximum": 72.5}]}]},
            {"name": {"value": "operationsPerSecond"}, "timeseries": [{"data": [{"maximum": 0.0}]}]},
            {"name": {"value": "evictedkeys"}, "timeseries": [{"data": [{"total": 15.0}]}]},
            {"name": {"value": "serverLoad"}, "timeseries": [{"data": [{"maximum": 12.0}]}]},
        ],
    }
    facts = extract_monitor_facts_from_profile(payload, profile)
    assert facts["memory_pct"] == 72.5
    assert facts["ops_per_sec"] == 0.0
    assert facts["evicted_keys"] == 15.0
    assert facts["server_load_pct"] == 12.0


def test_monitor_fetch_plan_includes_postgresql_analysis_metrics():
    plan = monitor_fetch_plan()
    pg = plan["database/postgresql"]
    names = {m["name"] for m in pg["metrics"]}
    aggregations = {m["name"]: m["aggregation"] for m in pg["metrics"]}
    assert "cpu_percent" in names
    assert "memory_percent" in names
    assert "storage_percent" in names
    assert "disk_iops_consumed_percentage" in names
    assert "active_connections" in names
    assert "max_connections" in names
    assert "physical_replication_delay_in_seconds" in names
    assert aggregations["cpu_percent"] == "Average"
    assert aggregations["disk_iops_consumed_percentage"] == "Maximum"
    assert "Maximum" in pg["aggregations"]
    assert "Total" in pg["aggregations"]


def test_enrich_derived_monitor_facts_computes_postgresql_connection_utilization():
    from app.monitor_metrics import enrich_derived_monitor_facts

    resource = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.DBforPostgreSQL/flexibleServers/pg1",
        "sku": {"name": "Standard_D4s_v3", "tier": "GeneralPurpose"},
    }
    facts = {"active_connections": 4000.0, "max_connections": 5000.0}
    enriched = enrich_derived_monitor_facts(resource, "database/postgresql", facts, metrics={})
    assert enriched["connection_utilization_pct"] == 80.0


def test_extract_monitor_facts_for_postgresql_profile():
    from app.monitor_metrics import extract_monitor_facts_from_profile
    from app.resources.registry import get_monitor_profile

    profile = get_monitor_profile(
        "/subscriptions/s/resourceGroups/rg/providers/Microsoft.DBforPostgreSQL/flexibleServers/pg1",
        "database/postgresql",
    )
    payload = {
        "value": [
            {"name": {"value": "cpu_percent"}, "timeseries": [{"data": [{"average": 42.5, "maximum": 95.0}]}]},
            {"name": {"value": "memory_percent"}, "timeseries": [{"data": [{"average": 61.0}]}]},
            {"name": {"value": "disk_iops_consumed_percentage"}, "timeseries": [{"data": [{"maximum": 88.0}]}]},
            {"name": {"value": "active_connections"}, "timeseries": [{"data": [{"maximum": 1200.0}]}]},
            {"name": {"value": "max_connections"}, "timeseries": [{"data": [{"maximum": 5000.0}]}]},
        ],
    }
    facts = extract_monitor_facts_from_profile(payload, profile)
    assert facts["cpu_pct"] == 42.5
    assert facts["memory_pct"] == 61.0
    assert facts["disk_iops_pct"] == 88.0
    assert facts["active_connections"] == 1200.0
    assert facts["max_connections"] == 5000.0


def test_monitor_fetch_plan_includes_cosmos_analysis_metrics():
    plan = monitor_fetch_plan()
    cosmos = plan["database/cosmosdb"]
    names = {m["name"] for m in cosmos["metrics"]}
    aggregations = {m["name"]: m["aggregation"] for m in cosmos["metrics"]}
    assert "TotalRequests" in names
    assert "TotalRequestUnits" in names
    assert "NormalizedRUConsumption" in names
    assert "DataUsage" in names
    assert "IndexUsage" in names
    assert "DocumentCountV2" in names
    normalized = [m for m in cosmos["metrics"] if m["name"] == "NormalizedRUConsumption"]
    assert len(normalized) == 2
    assert {m["aggregation"] for m in normalized} == {"Average", "Maximum"}
    assert "Count" in cosmos["aggregations"]
    assert "Total" in cosmos["aggregations"]


def test_enrich_derived_monitor_facts_computes_cosmos_skew_and_index_ratio():
    from app.monitor_metrics import enrich_derived_monitor_facts

    resource = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/cosmos1",
        "kind": "GlobalDocumentDB",
    }
    facts = {
        "normalized_ru_pct": 25.0,
        "normalized_ru_peak_pct": 80.0,
        "data_usage_bytes": 1000.0,
        "index_usage_bytes": 2000.0,
        "document_count": 10.0,
    }
    enriched = enrich_derived_monitor_facts(resource, "database/cosmosdb", facts, metrics={})
    assert enriched["ru_skew_ratio"] == 3.2
    assert enriched["index_to_data_ratio"] == 2.0
    assert enriched["avg_item_bytes"] == 100.0


def test_extract_monitor_facts_for_cosmos_profile():
    from app.monitor_metrics import extract_monitor_facts_from_profile
    from app.resources.registry import get_monitor_profile

    profile = get_monitor_profile(
        "/subscriptions/s/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/cosmos1",
        "database/cosmosdb",
    )
    payload = {
        "value": [
            {"name": {"value": "TotalRequests"}, "timeseries": [{"data": [{"count": 1200.0}]}]},
            {"name": {"value": "TotalRequestUnits"}, "timeseries": [{"data": [{"total": 45000.0}]}]},
            {"name": {"value": "NormalizedRUConsumption"}, "timeseries": [{"data": [{"average": 18.0, "maximum": 72.0}]}]},
            {"name": {"value": "DataUsage"}, "timeseries": [{"data": [{"total": 5000000.0}]}]},
            {"name": {"value": "IndexUsage"}, "timeseries": [{"data": [{"total": 9000000.0}]}]},
        ],
    }
    facts = extract_monitor_facts_from_profile(payload, profile)
    assert facts["request_count"] == 1200.0
    assert facts["total_ru"] == 45000.0
    assert facts["normalized_ru_pct"] == 18.0
    assert facts["normalized_ru_peak_pct"] == 72.0
    assert facts["data_usage_bytes"] == 5000000.0
    assert facts["index_usage_bytes"] == 9000000.0


def test_enrich_derived_monitor_facts_disk_string_sku():
    from app.monitor_metrics import enrich_derived_monitor_facts

    resource = {
        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/disks/data1",
        "sku": "Premium_LRS",
        "properties": {"diskSizeGB": 256, "diskIOPSReadWrite": 5000},
    }
    facts = {"disk_read_iops": 100.0, "disk_write_iops": 50.0}
    enriched = enrich_derived_monitor_facts(resource, "compute/disk", facts, metrics={})
    assert enriched["disk_iops_utilization_pct"] == 3.0

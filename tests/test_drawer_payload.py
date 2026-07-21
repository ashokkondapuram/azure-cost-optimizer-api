"""Tests for slim insight-drawer API payloads."""

import pytest

from app.drawer_payload import slim_analysis_payload, slim_metrics_payload


def test_slim_metrics_drops_raw_and_summary():
    full = {
        "ok": True,
        "resource_id": "/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        "canonical_type": "compute/disk",
        "display_name": "Disk",
        "timespan": "P7D",
        "data_quality": "azure_monitor",
        "metrics": [
            {
                "fact_key": "disk_read_bps",
                "label": "Read B/s",
                "stats": {"average": 100},
                "trigger": {"severity": "low"},
                "rules": ["DISK_OVERSIZE"],
                "impact": "high",
            },
        ],
        "derived": [],
        "metrics_summary": [{"fact_key": "disk_read_bps"}],
        "metrics_detail": [{"fact_key": "disk_read_bps"}],
        "metrics_raw": {"value": [{"name": "Composite Disk Read Bytes/sec"}]},
        "metric_names": ["Composite Disk Read Bytes/sec"],
        "aggregations": ["Average"],
        "facts": {"disk_read_bps": 100, "monthly_cost_usd": 12.5},
        "cost_driver_mapping": {
            "cost_drivers": [{"id": "tier", "label": "Tier"}],
            "properties": [{"path": "sku.name"}],
            "metrics": [{"fact_key": "disk_read_bps"}],
        },
    }
    slim = slim_metrics_payload(full)
    assert "metrics_raw" not in slim
    assert "metrics_summary" not in slim
    assert "metric_names" not in slim
    assert slim["metrics"][0]["fact_key"] == "disk_read_bps"
    assert "rules" not in slim["metrics"][0]
    assert slim["cost_driver_mapping"] == {"cost_drivers": [{"id": "tier", "label": "Tier"}]}
    assert slim["facts"] == {"disk_read_bps": 100}
    assert "monthly_cost_usd" not in slim.get("facts", {})


def test_slim_metrics_keeps_series_points():
    full = {
        "ok": True,
        "resource_id": "/subscriptions/x/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/c1",
        "canonical_type": "database/cosmosdb",
        "timespan": "P7D",
        "metrics": [
            {
                "fact_key": "normalized_ru_pct",
                "label": "RU utilization",
                "value": 0.2,
                "series_points": [
                    {"date": "2026-07-08", "value": 0.15},
                    {"date": "2026-07-09", "value": 0.2},
                ],
            },
        ],
        "derived": [],
        "cost_driver_mapping": {"cost_drivers": []},
    }
    slim = slim_metrics_payload(full)
    assert slim["metrics"][0]["series_points"] == full["metrics"][0]["series_points"]


def test_slim_metrics_backfills_series_points_from_metrics_detail():
    full = {
        "ok": True,
        "resource_id": "/subscriptions/x/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/c1",
        "canonical_type": "database/cosmosdb",
        "timespan": "P7D",
        "metrics": [
            {
                "fact_key": "normalized_ru_pct",
                "label": "RU utilization",
                "value": 18.0,
                "stats": {"average": 18.0},
            },
        ],
        "metrics_detail": [
            {
                "fact_key": "normalized_ru_pct",
                "label": "RU utilization",
                "stats": {"average": 18.0},
                "series_points": [
                    {"date": "2026-07-08", "value": 15.0},
                    {"date": "2026-07-09", "value": 18.0},
                ],
            },
        ],
        "derived": [],
        "cost_driver_mapping": {"cost_drivers": []},
    }
    slim = slim_metrics_payload(full)
    assert slim["metrics"][0]["series_points"] == full["metrics_detail"][0]["series_points"]


@pytest.mark.parametrize(
    ("resource_id", "canonical_type", "fact_key"),
    [
        (
            "/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
            "compute/vm",
            "avg_cpu_pct",
        ),
        (
            "/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
            "compute/disk",
            "disk_read_iops",
        ),
        (
            "/subscriptions/x/resourceGroups/rg/providers/Microsoft.ContainerService/managedClusters/aks1",
            "containers/aks",
            "cluster_cpu_pct",
        ),
    ],
)
def test_slim_metrics_backfills_series_points_for_all_resource_types(
    resource_id,
    canonical_type,
    fact_key,
):
    series_points = [
        {"date": "2026-07-08", "value": 15.0},
        {"date": "2026-07-09", "value": 18.0},
    ]
    full = {
        "ok": True,
        "resource_id": resource_id,
        "canonical_type": canonical_type,
        "timespan": "P7D",
        "metrics": [
            {
                "fact_key": fact_key,
                "label": fact_key,
                "value": 18.0,
                "stats": {"average": 18.0},
            },
        ],
        "metrics_detail": [
            {
                "fact_key": fact_key,
                "label": fact_key,
                "stats": {"average": 18.0},
                "series_points": series_points,
            },
        ],
        "derived": [],
        "cost_driver_mapping": {"cost_drivers": []},
    }
    slim = slim_metrics_payload(full)
    assert slim["metrics"][0]["series_points"] == series_points


def test_slim_metrics_preserves_pool_metrics_and_utilization_facts():
    full = {
        "ok": True,
        "resource_id": "/subscriptions/x/resourceGroups/rg/providers/Microsoft.ContainerService/managedClusters/aks1",
        "canonical_type": "containers/aks",
        "timespan": "P7D",
        "metrics": [{"fact_key": "cluster_cpu_pct", "label": "Cluster CPU", "value": 42.0}],
        "derived": [],
        "facts": {
            "cluster_cpu_pct": 42.0,
            "cluster_mem_pct": 55.0,
            "monthly_cost_usd": 120.0,
        },
        "pool_metrics": [
            {
                "name": "system",
                "cpu_pct": 25.0,
                "mem_pct": 55.0,
                "source": "vmss",
                "vmss_instances": [
                    {
                        "id": "/subscriptions/x/.../virtualMachines/0",
                        "name": "aks-system-vmss000000",
                        "instance_id": "0",
                        "power_state": "running",
                        "cpu_pct": 25.0,
                        "mem_pct": 55.0,
                        "source": "k8s_agent",
                        "metrics_detail": [{"fact_key": "node_cpu_pct"}],
                    },
                ],
            },
        ],
        "cost_driver_mapping": {"cost_drivers": []},
    }
    slim = slim_metrics_payload(full)
    assert slim["pool_metrics"][0]["name"] == "system"
    assert slim["pool_metrics"][0]["vmss_instances"][0]["name"] == "aks-system-vmss000000"
    assert "metrics_detail" not in slim["pool_metrics"][0]["vmss_instances"][0]
    assert slim["facts"]["cluster_cpu_pct"] == 42.0
    assert slim["facts"]["cluster_mem_pct"] == 55.0
    assert "monthly_cost_usd" not in slim.get("facts", {})


def test_slim_analysis_keeps_insights_only():
    full = {
        "subscription_id": "sub",
        "resource_id": "rid",
        "workload_profile": {"workload_type": "steady"},
        "utilization_evidence": {"avg_cpu_pct": 12},
        "dependencies": {
            "direct_outbound": ["/subscriptions/x/.../disks/d2"],
            "direct_inbound": [],
            "transitive_dependent_count": 2,
            "blast_radius": 5,
        },
        "actionable_findings": [{"id": 1, "rule_id": "VM_IDLE"}],
        "scorecard": {
            "id": 9,
            "overall_recommendation_score": 72,
            "recommendation_tier": "tier2_balanced",
            "primary_action": "rightsizing",
            "cost_savings_monthly": 50.0,
            "dimensions": {"cost": 80, "safety": 60, "effort": 70, "workload": 55, "business": 50},
            "evidence": {"blob": True},
        },
        "insights": {"headline": "Underutilized", "workload": [], "dependencies": [], "cost": []},
        "trends": {"cpu_trend": {"direction": "down"}, "cost_vs_prev_month_pct": -5},
        "mode": "advisory",
    }
    slim = slim_analysis_payload(full)
    assert set(slim.keys()) == {"insights", "trends", "dependencies"}
    assert slim["insights"]["headline"] == "Underutilized"
    assert slim["dependencies"]["direct_outbound"] == ["/subscriptions/x/.../disks/d2"]
    assert "blast_radius" not in slim["dependencies"]
    assert "scorecard" not in slim
    assert "actionable_findings" not in slim

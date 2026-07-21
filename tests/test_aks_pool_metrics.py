"""Tests for AKS per-pool utilization aggregation in metrics_api."""

from app.metrics_api import (
    _aggregate_aks_pool_metrics,
    _match_aks_node_to_pool,
)


def test_match_aks_node_to_pool_by_prefix():
    pools = [{"name": "system"}, {"name": "user"}]
    assert _match_aks_node_to_pool("prod-aks-system-abc123", "prod-aks", pools) == "system"
    assert _match_aks_node_to_pool("prod-aks/aks-user-node0", "prod-aks", pools) == "user"


def test_aggregate_aks_pool_metrics_from_instances():
    pools = [
        {"name": "system", "count": 2},
        {"name": "user", "count": 1},
    ]
    instances = [
        {
            "name": "prod-aks-system-node1",
            "metrics_detail": [
                {"fact_key": "node_cpu_pct", "stats": {"average": 20}},
                {"fact_key": "node_mem_pct", "stats": {"average": 40}},
            ],
        },
        {
            "pool_name": "user",
            "metrics_detail": [
                {"fact_key": "node_cpu_pct", "stats": {"average": 80}},
                {"fact_key": "node_mem_pct", "stats": {"average": 70}},
            ],
        },
    ]
    rows = _aggregate_aks_pool_metrics("prod-aks", pools, instances)
    by_name = {row["name"]: row for row in rows}
    assert by_name["system"]["cpu_pct"] == 20.0
    assert by_name["system"]["mem_pct"] == 40.0
    assert by_name["system"]["source"] == "node"
    assert by_name["user"]["cpu_pct"] == 80.0


def test_aggregate_aks_pool_metrics_cluster_fallback():
    pools = [{"name": "system", "count": 2}]
    rows = _aggregate_aks_pool_metrics(
        "prod-aks",
        pools,
        [],
        {"cluster_cpu_pct": 15.0, "cluster_mem_pct": 45.0},
    )
    assert rows[0]["cpu_pct"] == 15.0
    assert rows[0]["mem_pct"] == 45.0
    assert rows[0]["source"] == "cluster"


def test_aggregate_aks_pool_metrics_ignores_cluster_when_nodes_exist():
    pools = [{"name": "system", "count": 2}]
    instances = [{
        "name": "prod-aks-system-node1",
        "metrics_detail": [
            {"fact_key": "node_cpu_pct", "stats": {"average": 22}},
            {"fact_key": "node_mem_pct", "stats": {"average": 38}},
        ],
    }]
    rows = _aggregate_aks_pool_metrics(
        "prod-aks",
        pools,
        instances,
        {"cluster_cpu_pct": 99.0, "cluster_mem_pct": 99.0},
    )
    assert rows[0]["cpu_pct"] == 22.0
    assert rows[0]["mem_pct"] == 38.0
    assert rows[0]["source"] == "node"
    assert rows[0]["cpu_pct"] != 99.0

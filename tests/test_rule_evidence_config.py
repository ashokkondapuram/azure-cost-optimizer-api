"""Tests for per-rule required_evidence JSON contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.finding_evidence import build_rule_evidence
from app.optimization_metrics import build_optimization_metrics
from app.rule_evidence_config import (
    INVENTORY_PROPERTY_FACT_KEYS,
    canonical_type_for_rule,
    metric_ids_from_required_evidence,
    required_evidence_for_rule,
    rules_with_required_evidence,
)

_ROOT = Path(__file__).resolve().parents[1]
_MASTER = _ROOT / "data" / "rule_evidence_contracts.json"


@pytest.fixture(scope="module")
def master_contracts() -> dict:
    return json.loads(_MASTER.read_text(encoding="utf-8"))["analysis_rules"]


@pytest.mark.parametrize(
    "rule_id,canonical,expected_signals",
    [
        ("AKS_IDLE_POOL_EXTENDED", "containers/aks", {"cluster_cpu_utilization_pct", "idle_node_count"}),
        ("DISK_OVERSIZE_EXTENDED", "compute/disk", {"disk_iops_utilization_pct", "disk_read_throughput"}),
        ("VM_IDLE", "compute/vm", {"cpu_utilization_pct"}),
        ("SQL_IDLE", "database/sql", {"dtu_utilization_pct"}),
        ("LOAD_BALANCER_SNAT_PRESSURE", "network/loadbalancer", {"snat_port_utilization_pct"}),
        ("PUBLIC_IP_IDLE_EXTENDED", "network/publicip", {"network_bytes"}),
        ("STORAGE_COOL_TIER_CANDIDATE_EXTENDED", "storage/account", {"transaction_count"}),
        ("COSMOS_RU_RIGHT_SIZING_UNDER", "database/cosmosdb", {"ru_utilization_pct"}),
        ("REDIS_IDLE_DETECTION", "database/redis", {"operations_per_second"}),
    ],
)
def test_required_evidence_loaded(rule_id, canonical, expected_signals):
    evidence = required_evidence_for_rule(rule_id, canonical)
    signals = {item["signal"] for item in evidence}
    assert expected_signals.issubset(signals)
    for item in evidence:
        assert item.get("pillar") in (None, "performance", "cost", "reliability", "security")
        assert item.get("signal") not in INVENTORY_PROPERTY_FACT_KEYS


@pytest.mark.parametrize(
    "rule_id,canonical",
    [
        ("VM_IDLE", "compute/vm"),
        ("DISK_UNDERPROVISIONED", "compute/disk"),
        ("AKS_NODE_IDLE", "containers/aks"),
        ("SQL_SERVERLESS_EXTENDED", "database/sql"),
        ("LOAD_BALANCER_IDLE_EXTENDED", "network/loadbalancer"),
        ("STORAGE_LIFECYCLE_EXTENDED", "storage/account"),
        ("COSMOS_SERVERLESS", "database/cosmosdb"),
        ("POSTGRESQL_LOW_COMPUTE_UTILIZATION", "database/postgresql"),
    ],
)
def test_metric_profile_scoped_from_json(rule_id, canonical):
    profile = metric_ids_from_required_evidence(rule_id, canonical)
    assert profile is not None
    assert "sku" not in profile
    assert "node_count" not in profile


def test_master_contracts_coverage(master_contracts):
    with_evidence = [rid for rid, cfg in master_contracts.items() if cfg.get("required_evidence")]
    assert len(with_evidence) >= 180
    for rid, cfg in master_contracts.items():
        assert cfg.get("exclude_inventory_facts") is True


def test_aks_finding_excludes_inventory_properties_from_performance_metrics():
    finding = {
        "resource_type": "containers/aks",
        "estimated_savings_usd": 120.0,
    }
    evidence = build_rule_evidence(
        "AKS_IDLE_POOL_EXTENDED",
        {
            "idle_nodes": 2,
            "idle_node_ratio": 0.5,
            "node_count": 4,
            "pool_count": 7,
            "kubernetes_version": "1.33.2",
            "sku": "Base",
            "state": "Running",
            "cluster_cpu_pct": 8.2,
            "cluster_mem_pct": 11.5,
            "monthly_cost_usd": 400,
            "aks_max_idle_node_ratio": 0.3,
        },
        finding=finding,
        estimated_savings_usd=120.0,
    )
    perf = evidence.get("optimization_metrics", {}).get("performance") or []
    labels = {m.get("label") for m in perf}
    fact_keys = {m.get("fact_key") for m in perf}

    assert "Node count" not in labels
    assert "Node pools" not in labels
    assert "Kubernetes version" not in labels
    assert "SKU" not in labels
    assert "Resource state" not in labels
    assert "cluster_cpu_pct" in fact_keys or "Cluster CPU utilization" in labels
    assert evidence.get("required_evidence")


def test_disk_oversize_evidence_shape():
    evidence = build_rule_evidence(
        "DISK_OVERSIZE_EXTENDED",
        {
            "disk_state": "Attached",
            "sku": "Premium_LRS",
            "size_gb": 512,
            "disk_read_bps": 128,
            "disk_write_bps": 64,
            "disk_iops_utilization_pct": 4.2,
            "disk_io_idle_bps": 1024,
            "disk_iops_block_downgrade_pct": 20,
            "monthly_cost_usd": 80,
        },
        finding={"resource_type": "compute/disk"},
        estimated_savings_usd=40.0,
    )
    perf_ids = {m.get("id") for m in evidence.get("optimization_metrics", {}).get("performance") or []}
    assert "disk_iops_utilization" in perf_ids or "disk_read" in perf_ids
    check_signals = {c.get("signal") for c in evidence.get("checks") or []}
    assert "Disk SKU" in check_signals or "Combined disk I/O" in check_signals
    assert "Node count" not in check_signals
    req_signals = {r.get("signal") for r in evidence.get("required_evidence") or []}
    assert "disk_iops_utilization_pct" in req_signals


def test_vm_idle_evidence_uses_cpu_not_inventory():
    evidence = build_rule_evidence(
        "VM_IDLE",
        {
            "avg_cpu_pct": 2.5,
            "cpu_threshold_pct": 5,
            "vm_size": "Standard_D2s_v3",
            "state": "Running",
            "sku": "Standard",
            "monthly_cost_usd": 90,
        },
        finding={"resource_type": "compute/vm"},
        estimated_savings_usd=81.0,
    )
    metrics = build_optimization_metrics(
        evidence,
        finding={"resource_type": "compute/vm", "estimated_savings_usd": 81.0},
        rule_id="VM_IDLE",
        resource_type="compute/vm",
    )
    perf_labels = {m.get("label") for m in metrics.get("performance") or []}
    assert "Average CPU utilization" in perf_labels
    assert "Resource state" not in perf_labels
    assert "SKU" not in perf_labels


def test_governance_rule_empty_evidence_still_has_contract():
    cfg = required_evidence_for_rule("GOVERNANCE_TAG_ENFORCEMENT", "governance")
    assert cfg == []
    profile = metric_ids_from_required_evidence("GOVERNANCE_TAG_ENFORCEMENT", "governance")
    assert profile == ()


def test_no_contract_rule_does_not_dump_all_metrics():
    facts = {
        "avg_cpu_pct": 3.0,
        "node_count": 5,
        "sku": "Premium",
        "monthly_cost_usd": 50,
    }
    metrics = build_optimization_metrics(
        facts,
        finding={"resource_type": "compute/vm", "estimated_savings_usd": 10},
        rule_id="UNKNOWN_RULE_XYZ",
        resource_type="compute/vm",
    )
    perf_labels = {m.get("label") for m in metrics.get("performance") or []}
    assert "Average CPU utilization" not in perf_labels
    assert "Node count" not in perf_labels


def test_inventory_property_keys_cover_common_leaks():
    for key in ("node_count", "pool_count", "kubernetes_version", "sku", "state", "vm_size"):
        assert key in INVENTORY_PROPERTY_FACT_KEYS


def test_canonical_type_resolution():
    assert canonical_type_for_rule("DISK_OVERSIZE_EXTENDED") == "compute/disk"
    assert canonical_type_for_rule("SQL_IDLE") == "database/sql"
    assert canonical_type_for_rule("LOAD_BALANCER_SNAT_PRESSURE") == "network/loadbalancer"
    assert canonical_type_for_rule("COSMOS_SERVERLESS") == "database/cosmosdb"


def test_rules_with_required_evidence_helper():
    mapped = rules_with_required_evidence()
    assert "VM_IDLE" in mapped
    assert "DISK_OVERSIZE_EXTENDED" in mapped
    assert len(mapped) >= 180

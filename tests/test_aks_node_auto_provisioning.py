"""Tests for AKS Node Auto Provisioning (NAP) sync, analysis guards, and helpers."""

from __future__ import annotations

from app.optimizer.extended_engine import ExtendedOptimizationEngine
from it_services.containers_aks.engine.analysis import analyze_aks
from it_services.containers_aks.engine.helpers import is_node_auto_provisioning_enabled


def _nap_cluster(*, nap_mode: str | None = "Auto") -> tuple[dict, dict]:
    cid = (
        "/subscriptions/abc/resourceGroups/rg/providers/"
        "Microsoft.ContainerService/managedClusters/nap-cluster"
    )
    properties: dict = {
        "kubernetesVersion": "1.29.2",
        "agentPoolProfiles": [
            {
                "name": "userpool",
                "count": 5,
                "vmSize": "Standard_D2s_v3",
                "mode": "User",
                "enableAutoScaling": False,
            },
        ],
    }
    if nap_mode is not None:
        properties["nodeProvisioningProfile"] = {
            "mode": nap_mode,
            "defaultNodePools": "Auto",
        }
    cluster = {
        "id": cid,
        "name": "nap-cluster",
        "location": "eastus",
        "properties": properties,
        "_technical_facts": {
            "cluster_cpu_pct": 5.0,
            "cluster_mem_pct": 5.0,
            "node_cpu_pct": 5.0,
        },
    }
    pools = {cid: properties["agentPoolProfiles"]}
    return cluster, pools


def test_is_node_auto_provisioning_enabled():
    assert is_node_auto_provisioning_enabled({"nodeProvisioningProfile": {"mode": "Auto"}}) is True
    assert is_node_auto_provisioning_enabled({"nodeProvisioningProfile": {"mode": "Manual"}}) is False
    assert is_node_auto_provisioning_enabled({}) is False
    assert is_node_auto_provisioning_enabled(None) is False


def test_compute_node_auto_provisioning_fact():
    from app.resources.computed import compute_node_auto_provisioning

    assert compute_node_auto_provisioning({}, {"nodeProvisioningProfile": {"mode": "Auto"}}) == "Enabled"
    assert compute_node_auto_provisioning({}, {"nodeProvisioningProfile": {"mode": "Manual"}}) == "Disabled"
    assert compute_node_auto_provisioning({}, {}) == "Disabled"


def test_aks_needs_arm_enrichment_when_nap_profile_missing():
    from app.arm_resource_enrichment import needs_arm_enrichment
    from app.resources.registry import get_technical_fetch_spec

    spec = get_technical_fetch_spec("containers/aks")
    cluster = {
        "name": "nap-aks",
        "properties": {
            "kubernetesVersion": "1.29.2",
            "agentPoolProfiles": [{"name": "system", "count": 2}],
            "powerState": {"code": "Running"},
            "networkProfile": {"networkPlugin": "azure"},
            "provisioningState": "Succeeded",
        },
    }
    assert needs_arm_enrichment(cluster, spec) is True
    cluster["properties"]["nodeProvisioningProfile"] = {"mode": "Auto"}
    cluster["properties"]["nodeResourceGroup"] = "MC_rg_nap_eastus"
    assert needs_arm_enrichment(cluster, spec) is False


def test_aks_nap_suppresses_pool_scaling_rules(monkeypatch):
    monkeypatch.setattr(
        "it_services.containers_aks.engine.analysis.aks_supported_minors",
        lambda *_args, **_kwargs: {"1.29"},
    )
    monkeypatch.setattr(
        "it_services.containers_aks.engine.analysis.aks_version_catalog",
        lambda *_args, **_kwargs: {"supported_minors": ["1.29"], "default_version": "1.29.2"},
    )
    eng = ExtendedOptimizationEngine()
    cluster, pools = _nap_cluster(nap_mode="Auto")
    cid = cluster["id"]
    findings = analyze_aks(eng, "abc", [cluster], pools, {}, {cid.lower(): 500.0})
    rule_ids = {f.rule_id for f in findings}
    assert "AKS_NO_AUTOSCALER_EXTENDED" not in rule_ids
    assert "AKS_POOL_CONSOLIDATION" not in rule_ids
    assert "AKS_IDLE_POOL_EXTENDED" not in rule_ids


def test_aks_without_nap_emits_pool_scaling_rules(monkeypatch):
    monkeypatch.setattr(
        "it_services.containers_aks.engine.analysis.aks_supported_minors",
        lambda *_args, **_kwargs: {"1.29"},
    )
    monkeypatch.setattr(
        "it_services.containers_aks.engine.analysis.aks_version_catalog",
        lambda *_args, **_kwargs: {"supported_minors": ["1.29"], "default_version": "1.29.2"},
    )
    eng = ExtendedOptimizationEngine()
    cluster, pools = _nap_cluster(nap_mode="Manual")
    cid = cluster["id"]
    findings = analyze_aks(eng, "abc", [cluster], pools, {}, {cid.lower(): 500.0})
    rule_ids = {f.rule_id for f in findings}
    assert "AKS_NO_AUTOSCALER_EXTENDED" in rule_ids
    assert "AKS_POOL_CONSOLIDATION" in rule_ids
    assert "AKS_IDLE_POOL_EXTENDED" in rule_ids

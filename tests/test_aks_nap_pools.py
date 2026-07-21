"""Tests for NAP (Node Auto Provisioning) pool merge during AKS sync."""

from __future__ import annotations

import json

from app.arm_resource_enrichment import enrich_arm_resources_for_type
from app.db_sync import _aks_properties, build_aks_sync_properties, refresh_aks_cluster_snapshot
from it_services.containers_aks.nap_pools import (
    NAP_POOL_MODE_LABEL,
    merge_aks_pool_profiles,
    merge_nap_pools_from_vmss,
    pool_name_from_vmss,
)


def _vmss(name: str, rg: str = "MC_rg_prod_aks_eastus", *, capacity: int = 2) -> dict:
    return {
        "name": name,
        "id": (
            f"/subscriptions/sub-a/resourceGroups/{rg}"
            f"/providers/Microsoft.Compute/virtualMachineScaleSets/{name}"
        ),
        "sku": {"name": "Standard_D4s_v3", "capacity": capacity},
        "properties": {"storageProfile": {"osDisk": {"osType": "Linux"}}},
    }


def test_pool_name_from_vmss_strips_aks_prefix_and_hash():
    assert pool_name_from_vmss("aks-user-87654321-vmss") == "user"
    assert pool_name_from_vmss("aks-default-abc12345-vmss") == "default"


def test_merge_aks_pool_profiles_by_name():
    merged = merge_aks_pool_profiles(
        [{"name": "system", "count": 2, "vmSize": "Standard_D2s_v3"}],
        [{"name": "system", "properties": {"mode": "System"}, "enableAutoScaling": True}],
        [{"name": "napwork", "count": 1, "mode": "Auto provisioning"}],
    )
    by_name = {pool["name"]: pool for pool in merged}
    assert len(merged) == 2
    assert by_name["system"]["enableAutoScaling"] is True
    assert by_name["system"]["count"] == 2
    assert by_name["napwork"]["mode"] == "Auto provisioning"


def test_merge_nap_pools_from_vmss_adds_unmatched_vmss():
    pools = [{"name": "system", "count": 2, "vmSize": "Standard_D2s_v3", "mode": "System"}]
    vmss_list = [
        _vmss("aks-system-12345678-vmss"),
        _vmss("aks-gpu-abcdef01-vmss", capacity=3),
    ]
    merged = merge_nap_pools_from_vmss(
        pools,
        vmss_list,
        cluster_props={"nodeProvisioningProfile": {"mode": "Auto"}},
        node_resource_group="MC_rg_prod_aks_eastus",
    )
    names = {pool["name"] for pool in merged}
    assert "system" in names
    assert "gpu" in names
    gpu_pool = next(pool for pool in merged if pool["name"] == "gpu")
    assert gpu_pool["mode"] == NAP_POOL_MODE_LABEL
    assert gpu_pool["_napPool"] is True
    assert gpu_pool["virtualMachineScaleSet"]["name"] == "aks-gpu-abcdef01-vmss"
    assert gpu_pool["count"] == 3


def test_merge_nap_pools_from_vmss_skips_when_nap_disabled():
    pools = [{"name": "system", "count": 2}]
    merged = merge_nap_pools_from_vmss(
        pools,
        [_vmss("aks-gpu-abcdef01-vmss")],
        cluster_props={"nodeProvisioningProfile": {"mode": "Manual"}},
        node_resource_group="MC_rg_prod_aks_eastus",
    )
    assert merged == pools


def test_aks_properties_includes_nap_vmss_pools():
    cluster = {
        "properties": {
            "nodeResourceGroup": "MC_rg_prod_aks_eastus",
            "kubernetesVersion": "1.29.0",
            "nodeProvisioningProfile": {"mode": "Auto"},
        },
    }
    pools = [{"name": "system", "count": 2, "vmSize": "Standard_D2s_v3"}]
    vmss_list = [
        _vmss("aks-system-12345678-vmss"),
        _vmss("aks-gpu-abcdef01-vmss"),
    ]
    props = _aks_properties(cluster, pools, vmss_list)
    pool_names = {pool["name"] for pool in props["agentPoolProfiles"]}
    assert "system" in pool_names
    assert "gpu" in pool_names
    assert props["_vmssByPool"]["gpu"]["name"] == "aks-gpu-abcdef01-vmss"


def test_enrich_arm_resources_for_type_aks_merges_nap_after_get():
    """ARM GET must run before NAP merge so nodeProvisioningProfile is available."""
    thin_cluster = {
        "id": (
            "/subscriptions/sub-a/resourceGroups/rg/providers/"
            "Microsoft.ContainerService/managedClusters/prod"
        ),
        "name": "prod",
        "properties": {
            "kubernetesVersion": "1.29.0",
            "agentPoolProfiles": [
                {"name": "system", "count": 2, "vmSize": "Standard_D2s_v3", "mode": "System"},
            ],
            "provisioningState": "Succeeded",
            "networkProfile": {"networkPlugin": "azure"},
        },
    }
    full_cluster = {
        **thin_cluster,
        "properties": {
            **thin_cluster["properties"],
            "nodeProvisioningProfile": {"mode": "Auto"},
            "nodeResourceGroup": "MC_rg_prod_aks_eastus",
        },
    }
    vmss_list = [
        _vmss("aks-system-12345678-vmss"),
        _vmss("aks-gpu-abcdef01-vmss"),
    ]

    class _FakeClient:
        def get_aks_cluster(self, subscription_id, resource_group, cluster_name):
            return full_cluster

        def list_aks_node_pools(self, subscription_id, resource_group, cluster_name):
            return []

        def list_vm_scale_sets_in_resource_group(self, subscription_id, resource_group):
            return vmss_list

        def list_vm_scale_set_vms(self, subscription_id, resource_group, vmss_name):
            return []

    enriched = enrich_arm_resources_for_type(
        _FakeClient(), "sub-a", [dict(thin_cluster)], "containers/aks",
    )
    pool_names = {pool["name"] for pool in enriched[0]["properties"]["agentPoolProfiles"]}
    assert "system" in pool_names
    assert "gpu" in pool_names


def test_build_aks_sync_properties_includes_nap_pools():
    cluster = {
        "id": (
            "/subscriptions/sub-a/resourceGroups/rg/providers/"
            "Microsoft.ContainerService/managedClusters/prod"
        ),
        "name": "prod",
        "properties": {
            "nodeResourceGroup": "MC_rg_prod_aks_eastus",
            "nodeProvisioningProfile": {"mode": "Auto"},
            "agentPoolProfiles": [{"name": "system", "count": 2, "vmSize": "Standard_D2s_v3"}],
        },
    }
    vmss_list = [
        _vmss("aks-system-12345678-vmss"),
        _vmss("aks-gpu-abcdef01-vmss"),
    ]

    class _FakeClient:
        def list_aks_node_pools(self, subscription_id, resource_group, cluster_name):
            return []

        def list_vm_scale_sets_in_resource_group(self, subscription_id, resource_group):
            return vmss_list

        def list_vm_scale_set_vms(self, subscription_id, resource_group, vmss_name):
            return []

    props = build_aks_sync_properties(_FakeClient(), "sub-a", cluster)
    pool_names = {pool["name"] for pool in props["agentPoolProfiles"]}
    assert "gpu" in pool_names


def test_refresh_aks_cluster_snapshot_persists_nap_pools():
    cluster_id = (
        "/subscriptions/sub-a/resourceGroups/rg/providers/"
        "Microsoft.ContainerService/managedClusters/prod"
    )

    class _Snapshot:
        resource_id = cluster_id
        resource_name = "prod"
        properties_json = json.dumps({"agentPoolProfiles": [{"name": "system", "count": 2}]})
        state = None
        synced_at = None

    snapshot = _Snapshot()

    cluster = {
        "id": cluster_id,
        "name": "prod",
        "properties": {
            "nodeResourceGroup": "MC_rg_prod_aks_eastus",
            "nodeProvisioningProfile": {"mode": "Auto"},
            "agentPoolProfiles": [{"name": "system", "count": 2, "vmSize": "Standard_D2s_v3"}],
        },
    }
    vmss_list = [
        _vmss("aks-system-12345678-vmss"),
        _vmss("aks-gpu-abcdef01-vmss"),
    ]

    class _FakeClient:
        def get_aks_cluster(self, subscription_id, resource_group, cluster_name):
            return cluster

        def list_aks_node_pools(self, subscription_id, resource_group, cluster_name):
            return []

        def list_vm_scale_sets_in_resource_group(self, subscription_id, resource_group):
            return vmss_list

        def list_vm_scale_set_vms(self, subscription_id, resource_group, vmss_name):
            return []

    result = refresh_aks_cluster_snapshot(None, _FakeClient(), "sub-a", snapshot)
    assert result["status"] == "ok"
    assert result["nap_pool_count"] >= 1

    props = json.loads(snapshot.properties_json)
    pool_names = {pool["name"] for pool in props["agentPoolProfiles"]}
    assert "gpu" in pool_names

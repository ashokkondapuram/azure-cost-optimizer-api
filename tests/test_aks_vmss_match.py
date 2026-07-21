from it_services.containers_aks.vmss_match import (
    enrich_pools_with_vmss,
    filter_vmss_for_resource_group,
    match_pool_vmss,
    resolve_pool_vmss,
    vmss_by_pool_map,
    vmss_id_for_pool,
)


def _vmss(name: str, rg: str = "MC_rg_prod_aks_eastus") -> dict:
    return {
        "name": name,
        "id": (
            f"/subscriptions/sub-a/resourceGroups/{rg}"
            f"/providers/Microsoft.Compute/virtualMachineScaleSets/{name}"
        ),
    }


def test_match_pool_vmss_by_aks_prefix():
    vmss_list = [
        _vmss("aks-system-12345678-vmss"),
        _vmss("aks-user-87654321-vmss"),
    ]
    matched = match_pool_vmss("system", vmss_list)
    assert matched is not None
    assert matched["name"] == "aks-system-12345678-vmss"


def test_filter_vmss_for_resource_group():
    vmss_list = [
        _vmss("aks-system-1", "MC_rg_prod_aks_eastus"),
        _vmss("other-vmss", "other-rg"),
    ]
    scoped = filter_vmss_for_resource_group(vmss_list, "MC_rg_prod_aks_eastus")
    assert len(scoped) == 1
    assert scoped[0]["name"] == "aks-system-1"


def test_enrich_pools_with_vmss_scopes_to_node_resource_group():
    pools = [{"name": "system", "count": 2, "vmSize": "Standard_D2s_v3"}]
    vmss_list = [
        _vmss("aks-system-12345678-vmss", "MC_rg_prod_aks_eastus"),
        _vmss("aks-system-99999999-vmss", "other-rg"),
    ]
    enriched = enrich_pools_with_vmss(
        pools,
        vmss_list,
        node_resource_group="MC_rg_prod_aks_eastus",
    )
    vmss_ref = enriched[0]["virtualMachineScaleSet"]
    assert vmss_ref["id"].endswith("/aks-system-12345678-vmss")
    assert vmss_ref["name"] == "aks-system-12345678-vmss"


def test_enrich_pools_with_vmss_stores_vmss_metadata():
    pools = [{"name": "user", "count": 3}]
    vmss_list = [{
        **_vmss("aks-user-87654321-vmss"),
        "sku": {"name": "Standard_D4s_v3", "capacity": 3},
        "properties": {"provisioningState": "Succeeded"},
    }]
    enriched = enrich_pools_with_vmss(
        pools,
        vmss_list,
        node_resource_group="MC_rg_prod_aks_eastus",
    )
    vmss_ref = enriched[0]["virtualMachineScaleSet"]
    assert vmss_ref["sku"] == "Standard_D4s_v3"
    assert vmss_ref["capacity"] == 3
    assert vmss_ref["provisioningState"] == "Succeeded"


def test_vmss_by_pool_map_indexes_enriched_pools():
    pools = enrich_pools_with_vmss(
        [{"name": "system", "count": 2}],
        [_vmss("aks-system-12345678-vmss")],
        node_resource_group="MC_rg_prod_aks_eastus",
    )
    vmss_map = vmss_by_pool_map(pools)
    assert "system" in vmss_map
    assert vmss_map["system"]["name"] == "aks-system-12345678-vmss"


def test_enrich_pools_with_vmss_skips_match_without_node_resource_group():
    pools = [{"name": "system", "count": 2}]
    vmss_list = [_vmss("aks-system-12345678-vmss")]
    enriched = enrich_pools_with_vmss(pools, vmss_list, node_resource_group="")
    assert "virtualMachineScaleSet" not in enriched[0]


def test_resolve_pool_vmss_prefers_synced_reference():
    pool = {
        "name": "system",
        "virtualMachineScaleSet": {
            "id": "/subscriptions/sub-a/resourceGroups/MC_rg/providers/Microsoft.Compute/virtualMachineScaleSets/aks-system-synced-vmss",
        },
    }
    resolved = resolve_pool_vmss(pool, node_resource_group="MC_rg", vmss_list=[_vmss("aks-user-1")])
    assert resolved is not None
    assert resolved["name"] == "aks-system-synced-vmss"


def test_enrich_pools_with_vmss_accepts_string_vmss_reference():
    pools = [{
        "name": "system",
        "count": 3,
        "vmSize": "Standard_D2s_v3",
        "virtualMachineScaleSet": (
            "/subscriptions/sub-a/resourceGroups/MC_rg/providers/"
            "Microsoft.Compute/virtualMachineScaleSets/aks-system-synced-vmss"
        ),
    }]
    enriched = enrich_pools_with_vmss(
        pools,
        [_vmss("aks-user-87654321-vmss")],
        node_resource_group="MC_rg_prod_aks_eastus",
    )
    assert enriched[0]["virtualMachineScaleSet"]["id"].endswith("/aks-system-synced-vmss")


def test_resolve_pool_vmss_derives_from_node_resource_group():
    pool = {"name": "user", "count": 3}
    vmss_list = [_vmss("aks-user-87654321-vmss")]
    resolved = resolve_pool_vmss(
        pool,
        node_resource_group="MC_rg_prod_aks_eastus",
        vmss_list=vmss_list,
    )
    assert resolved is not None
    assert resolved["name"] == "aks-user-87654321-vmss"


def test_vmss_id_for_pool_uses_vmss_by_pool_when_pool_omits_direct_ref():
    pool = {"name": "user", "count": 3, "vmSize": "Standard_D4s_v3"}
    vmss_by_pool = {
        "user": {
            "id": (
                "/subscriptions/sub-a/resourceGroups/MC_rg_prod_aks_eastus/providers/"
                "Microsoft.Compute/virtualMachineScaleSets/aks-user-87654321-vmss"
            ),
        },
    }
    vmss_id = vmss_id_for_pool(pool, vmss_by_pool=vmss_by_pool)
    assert vmss_id.endswith("/aks-user-87654321-vmss")


def test_aks_properties_embeds_vmss_by_pool():
    from app.db_sync import _aks_properties

    cluster = {
        "properties": {
            "nodeResourceGroup": "MC_rg_prod_aks_eastus",
            "kubernetesVersion": "1.29.0",
        },
    }
    pools = [{"name": "system", "count": 2, "vmSize": "Standard_D2s_v3"}]
    vmss_list = [_vmss("aks-system-12345678-vmss", "MC_rg_prod_aks_eastus")]
    props = _aks_properties(cluster, pools, vmss_list)

    assert props["nodeResourceGroup"] == "MC_rg_prod_aks_eastus"
    pool_ref = props["agentPoolProfiles"][0]["virtualMachineScaleSet"]
    assert pool_ref["name"] == "aks-system-12345678-vmss"
    assert props["_vmssByPool"]["system"]["id"].endswith("/aks-system-12345678-vmss")


def test_resolve_aks_node_resource_group_fetches_when_list_omits_field():
    from app.db_sync import _resolve_aks_node_resource_group

    class _Client:
        def get_aks_cluster(self, subscription_id, rg, name):
            assert subscription_id == "sub-a"
            assert rg == "rg-prod"
            assert name == "prod-aks"
            return {
                "properties": {
                    "nodeResourceGroup": "MC_rg-prod_prod-aks_eastus",
                },
            }

    cluster = {
        "id": "/subscriptions/sub-a/resourceGroups/rg-prod/providers/Microsoft.ContainerService/managedClusters/prod-aks",
        "name": "prod-aks",
        "properties": {
            "agentPoolProfiles": [{"name": "system", "count": 2}],
        },
    }
    node_rg = _resolve_aks_node_resource_group(_Client(), "sub-a", cluster)
    assert node_rg == "MC_rg-prod_prod-aks_eastus"

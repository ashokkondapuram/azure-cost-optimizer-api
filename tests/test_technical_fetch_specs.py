"""Tests for technical fetch spec registry and extraction."""

from app.resources.registry import ALL_RESOURCE_MODULES, TECHNICAL_FETCH_SPECS
from app.resources import (
    extract_technical_facts,
    get_technical_fetch_spec,
    list_technical_fetch_specs,
    pick_sync_properties,
)

VM_ID = (
    "/subscriptions/abc/resourceGroups/prod-rg/providers/"
    "Microsoft.Compute/virtualMachines/prod-vm-01"
)
LB_ID = (
    "/subscriptions/abc/resourceGroups/net-rg/providers/"
    "Microsoft.Network/loadBalancers/prod-lb"
)

ALL_CANONICAL_TYPES = {
    getattr(mod, "CANONICAL_TYPE", None)
    for mod in ALL_RESOURCE_MODULES
    if getattr(mod, "TECHNICAL_FETCH_SPEC", None) is not None
}


def test_all_resource_modules_have_fetch_specs():
    assert len(ALL_CANONICAL_TYPES) >= 32
    for canonical in ALL_CANONICAL_TYPES:
        assert get_technical_fetch_spec(canonical) is not None


def test_all_synced_types_have_specs():
    synced = {
        "compute/vm", "compute/disk", "compute/snapshot",
        "containers/aks", "containers/acr",
        "storage/account",
        "network/publicip", "network/loadbalancer", "network/appgateway",
        "network/nsg", "network/nic", "network/nat",
        "database/sql", "database/cosmosdb", "database/postgresql", "database/redis",
        "appservice/webapp", "appservice/plan",
        "security/keyvault",
        "monitoring/loganalytics", "monitoring/appinsights",
        "integration/apim", "integration/datafactory", "integration/logicapp",
        "messaging/eventhub", "messaging/servicebus",
        "analytics/databricks", "analytics/synapse", "analytics/adx", "analytics/mlworkspace",
        "backup/recoveryvault",
        "search/cognitivesearch",
    }
    assert synced.issubset(ALL_CANONICAL_TYPES)
    for canonical in synced:
        assert get_technical_fetch_spec(canonical) is not None


def test_each_spec_has_sync_paths_and_metrics_or_generic_sync():
    for spec in TECHNICAL_FETCH_SPECS.values():
        assert spec.sync_property_paths or spec.generic_arm_sync
        assert spec.arm_type
        assert spec.display_name


def test_public_ip_has_monitor_metrics():
    spec = get_technical_fetch_spec("network/publicip")
    metric_keys = {m.fact_key for m in spec.usage_metrics}
    assert "byte_count" in metric_keys
    assert "packet_count" in metric_keys


def test_list_technical_fetch_specs_serializable():
    specs = list_technical_fetch_specs()
    assert len(specs) >= 20
    vm = next(s for s in specs if s["canonical_type"] == "compute/vm")
    assert vm["arm_type"] == "Microsoft.Compute/virtualMachines"
    assert vm["arm_get_api_version"] == "2025-11-01"
    assert "hardwareProfile" in vm["sync_property_paths"]
    assert any(f["fact_key"] == "vm_size" for f in vm["technical_fields"])
    assert any(m["fact_key"] == "avg_cpu_pct" for m in vm["usage_metrics"])


def test_pick_sync_properties_lb():
    spec = get_technical_fetch_spec("network/loadbalancer")
    arm = {
        "properties": {
            "backendAddressPools": [{"name": "pool1"}],
            "frontendIPConfigurations": [{"name": "fe1"}],
            "provisioningState": "Succeeded",
            "unusedField": "skip",
        }
    }
    props = pick_sync_properties(arm, spec)
    assert "backendAddressPools" in props
    assert "unusedField" not in props


def test_extract_lb_backend_facts():
    row = {
        "id": LB_ID,
        "type": "network/loadbalancer",
        "location": "eastus",
        "resourceGroup": "net-rg",
        "state": "Succeeded",
        "sku": "Standard",
        "properties": {
            "backendAddressPools": [
                {"properties": {"backendIPConfigurations": []}},
            ],
        },
    }
    facts = extract_technical_facts(row)
    assert facts["backend_pool_count"] == 1
    assert facts["all_backends_empty"] is True
    assert facts["arm_resource_type"] == "microsoft.network/loadbalancers"


def test_extract_app_gateway_listener_count():
    row = {
        "id": "/subscriptions/x/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw1",
        "type": "network/appgateway",
        "properties": {
            "httpListeners": [{"name": "https-listener"}],
            "provisioningState": "Succeeded",
        },
    }
    facts = extract_technical_facts(row)
    assert facts["http_listener_count"] == 1


def test_extract_app_gateway_pool_and_probe_counts():
    row = {
        "id": "/subscriptions/x/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw1",
        "type": "network/appgateway",
        "properties": {
            "backendAddressPools": [{"name": "pool-a"}, {"name": "pool-b"}],
            "probes": [{"name": "probe-https"}],
            "provisioningState": "Succeeded",
        },
    }
    facts = extract_technical_facts(row)
    assert facts["backend_pool_count"] == 2
    assert facts["health_probe_count"] == 1


def test_aks_sync_paths_include_node_provisioning_profile():
    spec = get_technical_fetch_spec("containers/aks")
    assert "nodeProvisioningProfile" in spec.sync_property_paths

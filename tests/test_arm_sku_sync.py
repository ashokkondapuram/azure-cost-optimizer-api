"""Tests for ARM SKU extraction and catalog enrichment during sync."""

from app.arm_sku_sync import (
    VmSkuCatalogCache,
    build_app_service_plan_sku_index,
    build_sync_sku_fields,
    extract_arm_sku_payload,
    sku_display_label,
)
from app.optimization_metrics import build_optimization_metrics
from app.resources.types import sku_text


class _FakeClient:
    def list_vm_skus(self, subscription_id: str, location: str) -> list:
        return [{
            "resourceType": "virtualMachines",
            "name": "Standard_D4s_v3",
            "tier": "Standard",
            "size": "D4s_v3",
            "family": "standardDSv3Family",
            "capabilities": [
                {"name": "vCPUs", "value": "4"},
                {"name": "MemoryGB", "value": "16"},
            ],
        }]


def test_extract_vm_sku_payload():
    vm = {
        "sku": {},
        "properties": {"hardwareProfile": {"vmSize": "Standard_D4s_v3"}},
        "location": "eastus",
    }
    payload = extract_arm_sku_payload(vm, "compute/vm")
    assert payload["vm_size"] == "Standard_D4s_v3"
    assert payload["name"] == "Standard_D4s_v3"


def test_build_sync_sku_fields_enriches_vm_catalog():
    vm = {
        "sku": {},
        "properties": {"hardwareProfile": {"vmSize": "Standard_D4s_v3"}},
        "location": "eastus",
    }
    cache = VmSkuCatalogCache(_FakeClient(), "sub")
    label, sku_json = build_sync_sku_fields(vm, "compute/vm", catalog_cache=cache)
    assert label == "Standard_D4s_v3"
    assert sku_json["catalog"]["vcpus"] == 4
    assert sku_json["catalog"]["memory_gb"] == 16.0


def test_redis_sku_payload():
    redis = {
        "sku": {"name": "Premium", "family": "P", "capacity": 1},
        "properties": {},
        "location": "eastus",
    }
    payload = extract_arm_sku_payload(redis, "database/redis")
    assert payload["name"] == "Premium"
    assert payload["family"] == "P"
    assert payload["capacity"] == 1


def test_vnet_address_space_sku_payload():
    vnet = {
        "properties": {
            "addressSpace": {"addressPrefixes": ["10.0.0.0/16", "172.16.0.0/24"]},
            "subnets": [{"name": "default"}, {"name": "aks"}],
        },
        "location": "canadacentral",
    }
    payload = extract_arm_sku_payload(vnet, "network/vnet")
    assert payload["name"] == "10.0.0.0/16, 172.16.0.0/24"
    assert payload["subnet_count"] == 2
    label, sku_json = build_sync_sku_fields(vnet, "network/vnet")
    assert label == "10.0.0.0/16, 172.16.0.0/24"
    assert sku_json["address_prefixes"] == ["10.0.0.0/16", "172.16.0.0/24"]


def test_private_endpoint_connection_sku_payload():
    pe = {
        "properties": {
            "privateLinkServiceConnections": [
                {
                    "properties": {
                        "groupId": "blob",
                        "privateLinkServiceId": (
                            "/subscriptions/sub-1/resourceGroups/net-rg/providers/"
                            "Microsoft.Storage/storageAccounts/sa1"
                        ),
                        "privateLinkServiceConnectionState": {"status": "Approved"},
                    },
                },
            ],
        },
        "location": "canadacentral",
    }
    payload = extract_arm_sku_payload(pe, "network/privateendpoint")
    assert payload["name"] == "blob · Approved"
    assert payload["group_id"] == "blob"
    assert payload["connection_state"] == "Approved"
    label, sku_json = build_sync_sku_fields(pe, "network/privateendpoint")
    assert label == "blob · Approved"
    assert sku_json["target_resource_id"].endswith("/storageAccounts/sa1")


def test_private_link_service_summary_sku_payload():
    pls = {
        "properties": {
            "visibility": "Enabled",
            "privateEndpointConnections": [{"name": "conn1"}, {"name": "conn2"}],
            "provisioningState": "Succeeded",
        },
        "location": "canadacentral",
    }
    payload = extract_arm_sku_payload(pls, "network/privatelinkservice")
    assert payload["name"] == "2 connections · Enabled"
    assert payload["connection_count"] == 2
    assert payload["visibility"] == "Enabled"
    label, sku_json = build_sync_sku_fields(pls, "network/privatelinkservice")
    assert label == "2 connections · Enabled"


def test_app_service_plan_sku_payload():
    plan = {
        "sku": {"name": "P1v3", "tier": "PremiumV3", "size": "P1v3", "capacity": 1},
        "properties": {"numberOfSites": 2, "status": "Ready"},
        "location": "canadacentral",
    }
    payload = extract_arm_sku_payload(plan, "appservice/plan")
    assert payload["name"] == "P1v3 · PremiumV3 · 1 worker"
    assert payload["tier"] == "PremiumV3"
    label, sku_json = build_sync_sku_fields(plan, "appservice/plan")
    assert label == "P1v3 · PremiumV3 · 1 worker"
    assert sku_json["size"] == "P1v3"


def test_app_service_webapp_plan_sku_label():
    plan = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Web/serverFarms/plan1",
        "sku": {"name": "S1", "tier": "Standard"},
        "properties": {},
    }
    webapp = {
        "properties": {
            "serverFarmId": plan["id"],
            "kind": "app,linux",
            "state": "Running",
        },
        "_plan_sku": "S1",
    }
    payload = extract_arm_sku_payload(webapp, "appservice/webapp")
    assert payload["plan_name"] == "plan1"
    assert payload["plan_sku"] == "S1"
    label = sku_display_label(webapp, "appservice/webapp", payload)
    assert label == "Linux · S1 · plan1"
    index = build_app_service_plan_sku_index([plan])
    assert index[plan["id"].lower()] == "S1"


def test_private_dns_zone_summary_sku_payload():
    zone = {
        "properties": {
            "zoneType": "Private",
            "numberOfRecordSets": 2,
            "provisioningState": "Succeeded",
        },
        "location": "global",
    }
    payload = extract_arm_sku_payload(zone, "network/privatedns")
    assert payload["name"] == "2 record sets · Private"
    assert payload["record_set_count"] == 2
    assert payload["zone_type"] == "Private"
    label, sku_json = build_sync_sku_fields(zone, "network/privatedns")
    assert label == "2 record sets · Private"


def test_appgateway_sku_from_properties():
    agw = {
        "properties": {
            "sku": {"name": "WAF_v2", "tier": "WAF_v2"},
            "provisioningState": "Succeeded",
        },
        "location": "canadacentral",
    }
    payload = extract_arm_sku_payload(agw, "network/appgateway")
    assert payload["name"] == "WAF_v2"
    assert payload["tier"] == "WAF_v2"
    label, sku_json = build_sync_sku_fields(agw, "network/appgateway")
    assert label == "WAF_v2"
    assert sku_json["arm"]["name"] == "WAF_v2"


def test_aks_node_pools_in_payload():
    aks = {
        "sku": {"name": "Base", "tier": "Standard"},
        "location": "eastus",
        "properties": {
            "agentPoolProfiles": [
                {"name": "pool1", "vmSize": "Standard_D2s_v3", "count": 3, "mode": "System"},
            ],
        },
    }
    payload = extract_arm_sku_payload(aks, "containers/aks")
    assert payload["tier"] == "Standard"
    assert payload["node_pools"][0]["vm_size"] == "Standard_D2s_v3"


def test_disk_sku_display_label_uses_name_only():
    disk = {
        "sku": {"name": "Premium_LRS", "tier": "Premium"},
        "properties": {"diskSizeGB": 128},
        "location": "eastus",
    }
    payload = extract_arm_sku_payload(disk, "compute/disk")
    label = sku_display_label(disk, "compute/disk", payload)
    assert label == "Premium_LRS"


def test_sku_text_strips_legacy_tier_suffix():
    assert sku_text({"name": "Premium_LRS", "tier": "Premium"}) == "Premium_LRS"
    assert sku_text("Premium_LRS (Premium)") == "Premium_LRS"


def test_disk_metrics_use_arm_sku_name_only():
    metrics = build_optimization_metrics(
        {"sku": "Premium_LRS (Premium)", "disk_state": "Unattached", "size_gb": 64},
        finding={"resource_type": "compute/disk"},
        rule_id="DISK_UNATTACHED",
        resource_type="compute/disk",
    )
    perf = {m["id"]: m for m in metrics["performance"]}
    assert perf["sku"]["formatted"] == "Premium_LRS"

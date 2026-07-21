"""Tests for Private Link stack inventory (private endpoints, link services, DNS zones)."""

from __future__ import annotations

from app.analysis.orchestrator import CANONICAL_TO_ARM, TYPE_TO_BUCKET, empty_buckets
from app.optimizer.component_map import COMPONENT_RESOURCE_TYPES
from app.resource_type_map import internal_resource_type
from app.resources import extract_technical_facts, get_technical_fetch_spec
from app.resources.registry import generic_arm_sync_types
from app.sync_scope import API_PATH_TO_TYPE, normalize_sync_types


PE_ID = (
    "/subscriptions/sub-1/resourceGroups/net-rg/providers/"
    "Microsoft.Network/privateEndpoints/pe-storage"
)
PLS_ID = (
    "/subscriptions/sub-1/resourceGroups/net-rg/providers/"
    "Microsoft.Network/privateLinkServices/pls-app"
)
DNS_ID = (
    "/subscriptions/sub-1/resourceGroups/net-rg/providers/"
    "Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
)


def test_private_link_arm_types_map_to_canonical():
    assert internal_resource_type(PE_ID) == "network/privateendpoint"
    assert internal_resource_type(PLS_ID) == "network/privatelinkservice"
    assert internal_resource_type(DNS_ID) == "network/privatedns"


def test_private_link_specs_registered_for_generic_sync():
    synced = dict(generic_arm_sync_types())
    assert synced["Microsoft.Network/privateEndpoints"] == "network/privateendpoint"
    assert synced["Microsoft.Network/privateLinkServices"] == "network/privatelinkservice"
    assert synced["Microsoft.Network/privateDnsZones"] == "network/privatedns"


def test_networking_component_includes_private_link_types():
    networking_extended = set(COMPONENT_RESOURCE_TYPES["Networking Extended"])
    assert "network/vnet" in networking_extended
    assert "network/privateendpoint" in networking_extended
    assert "network/privatelinkservice" in networking_extended
    assert "network/privatedns" in networking_extended
    networking = set(COMPONENT_RESOURCE_TYPES["Networking"])
    assert "network/firewall" in networking
    assert "network/cdn" in networking


def test_vnet_spec_registered_for_generic_sync():
    synced = dict(generic_arm_sync_types())
    assert synced["Microsoft.Network/virtualNetworks"] == "network/vnet"


def test_orchestrator_buckets_for_private_link_types():
    assert TYPE_TO_BUCKET["network/privateendpoint"] == "private_endpoints"
    assert TYPE_TO_BUCKET["network/privatelinkservice"] == "private_link_services"
    assert TYPE_TO_BUCKET["network/privatedns"] == "private_dns_zones"
    assert CANONICAL_TO_ARM["network/privateendpoint"] == "Microsoft.Network/privateEndpoints"
    buckets = empty_buckets()
    assert "private_endpoints" in buckets
    assert "private_link_services" in buckets
    assert "private_dns_zones" in buckets


def test_sync_scope_api_paths_for_private_link():
    assert API_PATH_TO_TYPE["/resources/privateendpoints"] == "network/privateendpoint"
    assert API_PATH_TO_TYPE["/resources/privatelinkservices"] == "network/privatelinkservice"
    assert API_PATH_TO_TYPE["/resources/privatedns"] == "network/privatedns"
    types = normalize_sync_types(["network/privateendpoint", "network/privatelinkservice"])
    assert types == {"network/privateendpoint", "network/privatelinkservice"}


def test_extract_private_endpoint_facts():
    spec = get_technical_fetch_spec("network/privateendpoint")
    assert spec is not None
    row = {
        "id": PE_ID,
        "type": "network/privateendpoint",
        "properties": {
            "provisioningState": "Succeeded",
            "privateLinkServiceConnections": [
                {
                    "properties": {
                        "privateLinkServiceId": PLS_ID,
                        "privateLinkServiceConnectionState": {"status": "Approved"},
                    },
                },
            ],
            "privateDnsZoneGroups": [{"name": "default"}],
        },
    }
    facts = extract_technical_facts(row)
    assert facts["connection_state"] == "Approved"
    assert facts["target_resource_id"] == PLS_ID
    assert facts["dns_zone_group_count"] == 1


def test_extract_private_dns_zone_facts():
    row = {
        "id": DNS_ID,
        "type": "network/privatedns",
        "properties": {
            "zoneType": "Private",
            "numberOfRecordSets": 2,
            "provisioningState": "Succeeded",
        },
    }
    facts = extract_technical_facts(row)
    assert facts["record_set_count"] == 2
    assert facts["is_empty"] is True


def test_extract_private_link_service_connection_count():
    row = {
        "id": PLS_ID,
        "type": "network/privatelinkservice",
        "properties": {
            "visibility": "Enabled",
            "privateEndpointConnections": [{"name": "conn1"}, {"name": "conn2"}],
            "provisioningState": "Succeeded",
        },
    }
    facts = extract_technical_facts(row)
    assert facts["connection_count"] == 2

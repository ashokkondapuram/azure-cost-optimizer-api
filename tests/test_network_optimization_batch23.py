"""Tests for networking optimization batches 2 and 3."""

from __future__ import annotations

from app.app_gateway_catalog import load_app_gateway_specifications, parse_app_gateway_arm
from app.nsg_catalog import load_nsg_specifications
from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.resource_engines.network.appgateway.optimization_rules import evaluate_app_gateway_cu_saturation
from app.optimizer.resource_engines.network.nsg.optimization_rules import evaluate_nsg_flow_log_cost
from app.optimizer.resource_engines.network.privateendpoint.optimization_rules import evaluate_private_endpoint_underutilized
from app.optimizer.resource_engines.network.privatelinkservice.optimization_rules import evaluate_private_link_nat_pressure
from app.optimizer.resource_engines.network.privatedns.optimization_rules import evaluate_private_dns_unused_zone
from app.optimizer.resource_engines.network.vnet.optimization_rules import evaluate_vnet_unused_subnet
from app.private_dns_catalog import load_private_dns_specifications
from app.private_endpoint_catalog import load_private_endpoint_specifications, parse_private_endpoint_arm
from app.private_link_service_catalog import load_private_link_service_specifications
from app.vnet_catalog import load_vnet_specifications, parse_vnet_arm


def test_batch23_catalogs_load():
    assert load_app_gateway_specifications().get("sku_tiers")
    assert load_private_endpoint_specifications().get("pricing")
    assert load_private_link_service_specifications().get("pricing")
    assert load_vnet_specifications().get("integrated_services")
    assert load_nsg_specifications().get("pricing")
    assert load_private_dns_specifications().get("pricing")


def test_app_gateway_cu_saturation():
    rule = ADVANCED_RULES["APP_GATEWAY_CU_SATURATION"]
    gw = {
        "name": "agw1",
        "sku": {"tier": "WAF_v2", "capacity": 2},
        "_technical_facts": {"billed_capacity_units": 180.0, "data_source": "azure_monitor"},
    }
    ctx = parse_app_gateway_arm(gw)
    draft = evaluate_app_gateway_cu_saturation(gw, ctx, 350.0, rule)
    assert draft is not None
    assert draft.priority == "P1"


def test_private_endpoint_underutilized_with_savings():
    rule = ADVANCED_RULES["PRIVATE_ENDPOINT_UNDERUTILIZED"]
    pe = {
        "name": "pe1",
        "properties": {"privateLinkServiceConnections": [{"properties": {"privateLinkServiceConnectionState": {"status": "Approved"}}}]},
        "_technical_facts": {
            "pe_bytes_in": 1_000_000.0,
            "pe_bytes_out": 500_000.0,
            "connection_state": "approved",
            "target_resource_id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/sa1",
            "data_source": "azure_monitor",
        },
    }
    ctx = parse_private_endpoint_arm(pe)
    draft = evaluate_private_endpoint_underutilized(pe, ctx, 0.0, rule)
    assert draft is not None
    assert draft.savings > 0


def test_private_link_nat_pressure():
    rule = ADVANCED_RULES["PRIVATE_LINK_NAT_PORT_PRESSURE"]
    pls = {
        "name": "pls1",
        "_technical_facts": {"pls_nat_port_usage_pct": 85.0, "data_source": "azure_monitor"},
    }
    draft = evaluate_private_link_nat_pressure(pls, {"connection_count": 2}, 40.0, rule)
    assert draft is not None
    assert draft.priority == "P1"


def test_vnet_peering_savings_without_mtd_cost():
    from app.optimizer.resource_engines.network.vnet.optimization_rules import evaluate_vnet_peering_consolidation

    rule = ADVANCED_RULES["VNET_PEERING_CONSOLIDATION_EXTENDED"]
    vnet = {"name": "vnet1", "properties": {"virtualNetworkPeerings": [{"name": "peer1"}, {"name": "peer2"}]}}
    draft = evaluate_vnet_peering_consolidation(vnet, {"peering_count": 2}, 0.0, rule)
    assert draft is not None
    assert draft.savings > 0


def test_private_dns_unused_zone_savings():
    rule = ADVANCED_RULES["PRIVATE_DNS_UNUSED_ZONE"]
    zone = {
        "name": "privatelink.database.windows.net",
        "_technical_facts": {"query_volume": 0.0, "record_set_count": 4, "data_source": "azure_monitor"},
    }
    draft = evaluate_private_dns_unused_zone(zone, {"record_set_count": 4}, 2.0, rule)
    assert draft is not None
    assert draft.savings > 0


def test_vnet_unused_subnet():
    rule = ADVANCED_RULES["VNET_UNUSED_SUBNET_EXTENDED"]
    vnet = {
        "name": "vnet1",
        "properties": {
            "subnets": [
                {"name": "empty", "properties": {"addressPrefix": "10.0.1.0/24"}},
                {"name": "used", "properties": {"addressPrefix": "10.0.2.0/24", "ipConfigurations": [{"id": "x"}]}},
            ],
        },
    }
    ctx = parse_vnet_arm(vnet)
    draft = evaluate_vnet_unused_subnet(vnet, ctx, 0.0, rule)
    assert draft is not None
    assert ctx["empty_subnet_count"] == 1


def test_nsg_flow_log_cost_savings():
    rule = ADVANCED_RULES["NSG_FLOW_LOG_COST"]
    nsg = {
        "name": "nsg1",
        "_technical_facts": {"flow_log_bytes": 5_000_000_000.0, "data_source": "azure_monitor"},
    }
    draft = evaluate_nsg_flow_log_cost(nsg, {"subnet_count": 1, "nic_count": 0}, 12.0, rule)
    assert draft is not None
    assert draft.savings > 0


def test_batch23_rules_registered():
    for rule_id in (
        "APP_GATEWAY_CU_SATURATION",
        "APP_GATEWAY_CU_RIGHTSIZE_DOWN",
        "PRIVATE_ENDPOINT_UNDERUTILIZED",
        "PRIVATE_LINK_NAT_PORT_PRESSURE",
        "PRIVATE_LINK_NAT_RIGHTSIZE",
        "PRIVATE_DNS_UNUSED_ZONE",
        "VNET_PEERING_CONSOLIDATION_EXTENDED",
        "VNET_UNUSED_SUBNET_EXTENDED",
        "NSG_FLOW_LOG_COST",
    ):
        assert rule_id in ADVANCED_RULES

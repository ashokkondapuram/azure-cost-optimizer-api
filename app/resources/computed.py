"""Computed field extractors shared across resource technical fetch specs."""

from __future__ import annotations

from typing import Any, Callable

from app.resources.types import get_nested


def compute_backend_pool_count(_row: dict, props: dict) -> int | None:
    pools = props.get("backendAddressPools") or []
    return len(pools) if pools else None


def compute_all_backends_empty(_row: dict, props: dict) -> bool | None:
    pools = props.get("backendAddressPools") or []
    if not pools:
        return None
    return all(
        not get_nested(pool, "properties.backendIPConfigurations")
        and not get_nested(pool, "properties.loadBalancerBackendAddresses")
        for pool in pools
    )


def compute_http_listener_count(_row: dict, props: dict) -> int | None:
    from app.appgateway_utils import http_listener_count

    return http_listener_count(props)


def compute_health_probe_count(_row: dict, props: dict) -> int | None:
    probes = props.get("probes") or props.get("healthProbes") or []
    return len(probes) if probes else None


def compute_has_vm(_row: dict, props: dict) -> bool:
    return bool(props.get("virtualMachine"))


def compute_has_private_endpoint(_row: dict, props: dict) -> bool:
    return bool(props.get("privateEndpoint"))


def compute_subnet_count(_row: dict, props: dict) -> int | None:
    subnets = props.get("subnets") or []
    return len(subnets)


def compute_pool_count(_row: dict, props: dict) -> int | None:
    pools = props.get("agentPoolProfiles") or []
    return len(pools) if pools else None


def compute_node_count(_row: dict, props: dict) -> int | None:
    pools = props.get("agentPoolProfiles") or []
    if not pools:
        return None
    return sum(int(p.get("count") or 0) for p in pools)


def compute_node_auto_provisioning(_row: dict, props: dict) -> str:
    profile = props.get("nodeProvisioningProfile") or {}
    mode = str(profile.get("mode") or "").strip().lower()
    return "Enabled" if mode == "auto" else "Disabled"


def compute_app_count(_row: dict, props: dict) -> int | None:
    sites = props.get("numberOfSites")
    return int(sites) if sites is not None else None


def compute_serverless_enabled(_row: dict, props: dict) -> bool | None:
    caps = props.get("capabilities") or []
    for cap in caps:
        name = (cap.get("name") if isinstance(cap, dict) else cap) or ""
        if str(name).lower() == "enableserverless":
            return True
    return False if caps else None


def compute_rule_count(_row: dict, props: dict) -> int | None:
    rules = props.get("securityRules") or []
    return len(rules) if rules else None


def compute_snapshot_age_days(_row: dict, props: dict) -> int | None:
    from datetime import datetime, timezone

    from app.vm_uptime import parse_azure_datetime

    created = parse_azure_datetime(
        props.get("timeCreated") or props.get("TimeCreated") or (_row.get("properties") or {}).get("timeCreated"),
    )
    if not created:
        return None
    return max(0, (datetime.now(timezone.utc) - created).days)


def compute_power_state(_row: dict, props: dict) -> str | None:
    power = props.get("powerState") or _row.get("state") or ""
    if power:
        return str(power).replace("PowerState/", "")
    return None


def compute_replication_count(_row: dict, props: dict) -> int:
    reps = props.get("_replications") or props.get("replications") or []
    if isinstance(reps, list) and reps:
        return len(reps)
    count = props.get("replicationCount")
    if count is not None:
        try:
            return max(0, int(count))
        except (TypeError, ValueError):
            pass
    return 0


def compute_private_endpoint_count(_row: dict, props: dict) -> int:
    conns = props.get("privateEndpointConnections") or []
    return len(conns) if isinstance(conns, list) else 0


def compute_retention_policy_enabled(_row: dict, props: dict) -> bool:
    policies = props.get("policies") or {}
    retention = policies.get("retentionPolicy") or {}
    return str(retention.get("status") or "").lower() == "enabled"


def compute_retention_policy_days(_row: dict, props: dict) -> int | None:
    policies = props.get("policies") or {}
    retention = policies.get("retentionPolicy") or {}
    days = retention.get("days")
    return int(days) if days is not None else None


def compute_network_default_action(_row: dict, props: dict) -> str | None:
    network = props.get("networkAcls") or {}
    action = network.get("defaultAction")
    return str(action) if action not in (None, "") else None


def _first_connection(props: dict) -> dict:
    for key in ("privateLinkServiceConnections", "manualPrivateLinkServiceConnections"):
        conns = props.get(key) or []
        if isinstance(conns, list) and conns:
            first = conns[0]
            return first if isinstance(first, dict) else {}
    return {}


def compute_pe_connection_state(_row: dict, props: dict) -> str | None:
    conn = _first_connection(props)
    inner = conn.get("properties") if isinstance(conn.get("properties"), dict) else conn
    state = (
        inner.get("privateLinkServiceConnectionState", {}).get("status")
        if isinstance(inner.get("privateLinkServiceConnectionState"), dict)
        else inner.get("provisioningState")
    )
    return str(state) if state not in (None, "") else None


def compute_pe_target_resource_id(_row: dict, props: dict) -> str | None:
    conn = _first_connection(props)
    inner = conn.get("properties") if isinstance(conn.get("properties"), dict) else conn
    target = (
        inner.get("privateLinkServiceId")
        or inner.get("groupId")
        or inner.get("privateLinkServiceArmRegion")
    )
    return str(target) if target not in (None, "") else None


def compute_dns_zone_group_count(_row: dict, props: dict) -> int:
    groups = props.get("privateDnsZoneGroups") or []
    return len(groups) if isinstance(groups, list) else 0


def compute_pls_connection_count(_row: dict, props: dict) -> int:
    conns = props.get("privateEndpointConnections") or []
    return len(conns) if isinstance(conns, list) else 0


def compute_privatedns_record_set_count(_row: dict, props: dict) -> int | None:
    count = props.get("numberOfRecordSets")
    return int(count) if count is not None else None


def compute_privatedns_is_empty(_row: dict, props: dict) -> bool | None:
    count = props.get("numberOfRecordSets")
    if count is None:
        return None
    try:
        return int(count) <= 2
    except (TypeError, ValueError):
        return None


def compute_vnet_peering_count(_row: dict, props: dict) -> int:
    peerings = props.get("virtualNetworkPeerings") or []
    return len(peerings) if isinstance(peerings, list) else 0


def compute_cosmos_api_type(row: dict, props: dict) -> str | None:
    from app.cosmosdb_catalog import parse_cosmos_arm_account

    return parse_cosmos_arm_account(row).get("api_type")


def compute_cosmos_region_count(_row: dict, props: dict) -> int | None:
    locations = props.get("locations") or []
    if not locations:
        return None
    return len(locations)


COMPUTED: dict[str, Callable[[dict, dict], Any]] = {
    "backend_pool_count": compute_backend_pool_count,
    "all_backends_empty": compute_all_backends_empty,
    "http_listener_count": compute_http_listener_count,
    "health_probe_count": compute_health_probe_count,
    "has_vm": compute_has_vm,
    "has_private_endpoint": compute_has_private_endpoint,
    "subnet_count": compute_subnet_count,
    "pool_count": compute_pool_count,
    "node_count": compute_node_count,
    "node_auto_provisioning": compute_node_auto_provisioning,
    "app_count": compute_app_count,
    "serverless_enabled": compute_serverless_enabled,
    "power_state": compute_power_state,
    "rule_count": compute_rule_count,
    "snapshot_age_days": compute_snapshot_age_days,
    "replication_count": compute_replication_count,
    "private_endpoint_count": compute_private_endpoint_count,
    "retention_policy_enabled": compute_retention_policy_enabled,
    "retention_policy_days": compute_retention_policy_days,
    "network_default_action": compute_network_default_action,
    "pe_connection_state": compute_pe_connection_state,
    "pe_target_resource_id": compute_pe_target_resource_id,
    "dns_zone_group_count": compute_dns_zone_group_count,
    "pls_connection_count": compute_pls_connection_count,
    "privatedns_record_set_count": compute_privatedns_record_set_count,
    "privatedns_is_empty": compute_privatedns_is_empty,
    "vnet_peering_count": compute_vnet_peering_count,
    "cosmos_api_type": compute_cosmos_api_type,
    "cosmos_region_count": compute_cosmos_region_count,
}

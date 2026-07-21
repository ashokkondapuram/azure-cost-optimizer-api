"""Resource profile — owned by network-privatelinkservice IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, metric, utilization_metric as um

CANONICAL_TYPE = "network/privatelinkservice"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/privateLinkServices",
    display_name="Private link service",
    sync_property_paths=(
        "visibility",
        "autoApproval",
        "fqdns",
        "ipConfigurations",
        "privateEndpointConnections",
        "provisioningState",
    ),
    generic_arm_sync=True,
    enrich_if_missing=("privateEndpointConnections",),
    fields=(
        field("connection_count", "computed:pls_connection_count", "Private endpoint connections", "association",
              "PRIVATE_LINK_UNUSED_EXTENDED"),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "PRIVATE_LINK_COST"),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/privatelinkservices",
    canonical_type=CANONICAL_TYPE,
    display_name="Private link service",
    doc_ref="microsoft-network-privatelinkservices-metrics",
    metrics=(
        um("PLSNatPortsUsage", "pls_nat_ports_used", "NAT ports in use",
           rules=("PRIVATE_LINK_NAT_PORT_PRESSURE", "PRIVATE_LINK_NAT_RIGHTSIZE")),
        um("PLSNatPortsCount", "pls_nat_ports_allocated", "NAT ports allocated",
           rules=("PRIVATE_LINK_NAT_PORT_PRESSURE", "PRIVATE_LINK_NAT_RIGHTSIZE")),
    ),
)

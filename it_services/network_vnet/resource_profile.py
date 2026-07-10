"""Resource profile — owned by network-vnet IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, metric, utilization_metric as um

CANONICAL_TYPE = "network/vnet"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/virtualNetworks",
    display_name="Virtual network",
    sync_property_paths=(
        "addressSpace",
        "subnets",
        "virtualNetworkPeerings",
        "provisioningState",
    ),
    generic_arm_sync=True,
    fields=(
        field("subnet_count", "computed:subnet_count", "Subnet count", "capacity"),
        field("peering_count", "computed:vnet_peering_count", "Peering count", "association",
              "VNET_PEERING_REVIEW_EXTENDED"),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "BANDWIDTH_REVIEW"),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/virtualnetworks",
    canonical_type=CANONICAL_TYPE,
    display_name="Virtual network",
    doc_ref="microsoft-network-virtualnetworks-metrics",
    metrics=(
        um("BytesDroppedDDoS", "ddos_bytes_dropped", "DDoS bytes dropped", aggregation="Total",
           rules=("VNET_PEERING_CONSOLIDATION_EXTENDED",)),
    ),
)

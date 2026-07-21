"""Resource profile — owned by network-nat IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "network/nat"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/natGateways",
    display_name="NAT gateway",
    sync_property_paths=("subnets", "publicIpAddresses", "provisioningState"),
    fields=(
        field("subnet_count", "computed:subnet_count", "Subnet associations", "association",
              "NAT_GATEWAY_IDLE"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/natgateways",
    canonical_type=CANONICAL_TYPE,
    display_name="NAT gateway",
    doc_ref="microsoft-network-natgateways-metrics",
    metrics=(
        um("ByteCount", "byte_count", "NAT gateway traffic volume", aggregation="Total",
           rules=("NAT_GATEWAY_IDLE", "NAT_GATEWAY_IDLE_EXTENDED", "NAT_GATEWAY_SKU_V2_UPGRADE")),
        um("SNATConnectionCount", "snat_connection_count", "SNAT connection count", aggregation="Total",
           rules=("NAT_GATEWAY_IDLE_EXTENDED", "NAT_GATEWAY_SNAT_EXHAUSTION")),
        um("PacketDropCount", "packet_drop_count", "Dropped packets", aggregation="Total",
           rules=("NAT_GATEWAY_SNAT_EXHAUSTION",)),
        um("DatapathAvailability", "datapath_availability_pct", "Datapath availability", aggregation="Average",
           rules=("NAT_GATEWAY_SNAT_EXHAUSTION",)),
    ),
)

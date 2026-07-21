"""Resource profile — owned by network-publicip IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "network/publicip"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/publicIPAddresses",
    display_name="Public IP address",
    sync_property_paths=(
        "ipAddress", "ipConfiguration", "natGateway", "publicIPAllocationMethod",
        "provisioningState",
    ),
    fields=(
        field("ip_address", "props:ipAddress", "IP address", "configuration"),
        field("allocation", "row:state", "Association", "association",
              "IP_UNASSOCIATED", "IP_IDLE_EXTENDED"),
        field("public_ip_allocation_method", "props:publicIPAllocationMethod", "Allocation method",
              "configuration", "IP_UNASSOCIATED"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/publicipaddresses",
    canonical_type=CANONICAL_TYPE,
    display_name="Public IP address",
    doc_ref="microsoft-network-publicipaddresses-metrics",
    metrics=(
        um("ByteCount", "byte_count", "Bytes transmitted", aggregation="Total",
           rules=("IP_IDLE_EXTENDED", "PUBLIC_IP_IDLE_EXTENDED")),
        um("PacketCount", "packet_count", "Packets transmitted", aggregation="Total",
           rules=("IP_IDLE_EXTENDED", "PUBLIC_IP_IDLE_EXTENDED")),
        um("VipAvailability", "vip_availability_pct", "VIP availability", aggregation="Average",
           rules=("PUBLIC_IP_IDLE_EXTENDED",)),
    ),
)

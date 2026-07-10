"""Resource profile — owned by network-nic IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "network/nic"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/networkInterfaces",
    display_name="Network interface",
    sync_property_paths=("virtualMachine", "privateEndpoint", "ipConfigurations", "provisioningState"),
    fields=(
        field("has_vm", "computed:has_vm", "Attached to VM", "association", "NIC_UNATTACHED"),
        field("has_private_endpoint", "computed:has_private_endpoint", "Private endpoint", "association",
              "NIC_UNATTACHED"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/networkinterfaces",
    canonical_type=CANONICAL_TYPE,
    display_name="Network interface",
    doc_ref="microsoft-network-networkinterfaces-metrics",
    metrics=(
        um("BytesReceivedRate", "bytes_received_rate", "Inbound bytes rate", aggregation="Total",
           rules=("NIC_UNATTACHED",)),
        um("BytesSentRate", "bytes_sent_rate", "Outbound bytes rate", aggregation="Total",
           rules=("NIC_UNATTACHED",)),
    ),
)

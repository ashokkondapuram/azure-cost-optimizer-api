"""Resource profile — owned by network-expressroute IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field

CANONICAL_TYPE = "network/expressroute"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/expressRouteCircuits",
    display_name="ExpressRoute circuit",
    sync_property_paths=("provisioningState", "serviceProviderProperties", "peerings"),
    generic_arm_sync=True,
    fields=(
        field("provisioning_state", "props:provisioningState", "Provisioning state", "status", "NETWORK_EXPRESSROUTE_REVIEW"),
        field("sku", "row:sku", "SKU", "configuration", "NETWORK_EXPRESSROUTE_REVIEW"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/expressroutecircuits",
    canonical_type=CANONICAL_TYPE,
    display_name="ExpressRoute circuit",
    doc_ref="microsoft-network-expressroutecircuits-metrics",
    metrics=(),
)

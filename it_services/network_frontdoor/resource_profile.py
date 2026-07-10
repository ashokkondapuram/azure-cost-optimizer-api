"""Resource profile — owned by network-frontdoor IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field

CANONICAL_TYPE = "network/frontdoor"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/frontdoors",
    display_name="Azure Front Door",
    sync_property_paths=("provisioningState", "frontendEndpoints", "routingRules"),
    generic_arm_sync=True,
    fields=(
        field("provisioning_state", "props:provisioningState", "Provisioning state", "status", "NETWORK_FRONT_DOOR_REVIEW"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/frontdoors",
    canonical_type=CANONICAL_TYPE,
    display_name="Azure Front Door",
    doc_ref="microsoft-network-frontdoors-metrics",
    metrics=(),
)

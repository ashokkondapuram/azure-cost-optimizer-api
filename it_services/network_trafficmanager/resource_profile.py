"""Resource profile — owned by network-trafficmanager IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field

CANONICAL_TYPE = "network/trafficmanager"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/trafficManagerProfiles",
    display_name="Traffic Manager profile",
    sync_property_paths=("profileStatus", "trafficRoutingMethod", "endpoints"),
    generic_arm_sync=True,
    fields=(
        field("profile_status", "props:profileStatus", "Profile status", "status", "NETWORK_TRAFFIC_MANAGER_IDLE"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/trafficmanagerprofiles",
    canonical_type=CANONICAL_TYPE,
    display_name="Traffic Manager profile",
    doc_ref="microsoft-network-trafficmanagerprofiles-metrics",
    metrics=(),
)

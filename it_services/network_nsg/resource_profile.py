"""Resource profile — owned by network-nsg IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field

CANONICAL_TYPE = "network/nsg"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/networkSecurityGroups",
    display_name="Network security group",
    sync_property_paths=("securityRules", "subnets", "networkInterfaces", "provisioningState"),
    fields=(
        field("rule_count", "computed:rule_count", "Security rule count", "configuration"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/networksecuritygroups",
    canonical_type=CANONICAL_TYPE,
    display_name="Network security group",
    doc_ref="microsoft-network-networksecuritygroups-metrics",
    metrics=(),
)

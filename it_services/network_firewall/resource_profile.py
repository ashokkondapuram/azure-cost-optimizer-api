"""Resource profile — owned by network-firewall IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, metric

CANONICAL_TYPE = "network/firewall"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/azureFirewalls",
    display_name="Azure Firewall",
    sync_property_paths=("provisioningState", "sku", "firewallPolicy", "threatIntelMode"),
    generic_arm_sync=True,
    fields=(
        field("sku_tier", "row:sku", "SKU tier", "configuration", "FIREWALL_FIXED_COST_EXTENDED"),
        field("provisioning_state", "props:provisioningState", "Provisioning state", "status",
              "FIREWALL_FIXED_COST_EXTENDED"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/azurefirewalls",
    canonical_type=CANONICAL_TYPE,
    display_name="Azure Firewall",
    doc_ref="microsoft-network-azurefirewalls-metrics",
    metrics=(),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "FIREWALL_FIXED_COST_EXTENDED"),
)

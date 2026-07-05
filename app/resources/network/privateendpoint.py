from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, metric

CANONICAL_TYPE = "network/privateendpoint"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/privateEndpoints",
    display_name="Private endpoint",
    sync_property_paths=(
        "subnet",
        "privateLinkServiceConnections",
        "manualPrivateLinkServiceConnections",
        "customDnsConfigs",
        "privateDnsZoneGroups",
        "provisioningState",
    ),
    generic_arm_sync=True,
    enrich_if_missing=("privateLinkServiceConnections", "privateDnsZoneGroups"),
    fields=(
        field("connection_state", "computed:pe_connection_state", "Connection state", "association",
              "PRIVATE_ENDPOINT_FAILED_EXTENDED"),
        field("target_resource_id", "computed:pe_target_resource_id", "Target resource", "association",
              "PRIVATE_ENDPOINT_ORPHAN_EXTENDED"),
        field("dns_zone_group_count", "computed:dns_zone_group_count", "DNS zone groups", "configuration",
              "PRIVATE_ENDPOINT_ORPHAN_EXTENDED"),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "PRIVATE_ENDPOINT_COST"),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/privateendpoints",
    canonical_type=CANONICAL_TYPE,
    display_name="Private endpoint",
    doc_ref="microsoft-network-privateendpoints-metrics",
    metrics=(),
)

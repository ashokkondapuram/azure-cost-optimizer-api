from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, metric

CANONICAL_TYPE = "network/privatedns"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/privateDnsZones",
    display_name="Private DNS zone",
    sync_property_paths=(
        "zoneType",
        "numberOfRecordSets",
        "maxNumberOfRecordSets",
        "provisioningState",
    ),
    generic_arm_sync=True,
    fields=(
        field("record_set_count", "computed:privatedns_record_set_count", "Record set count", "capacity",
              "PRIVATE_DNS_EMPTY_EXTENDED"),
        field("is_empty", "computed:privatedns_is_empty", "Empty zone", "utilization",
              "PRIVATE_DNS_EMPTY_EXTENDED"),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "PRIVATE_LINK_COST"),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/privatednszones",
    canonical_type=CANONICAL_TYPE,
    display_name="Private DNS zone",
    doc_ref="microsoft-network-privatednszones-metrics",
    metrics=(),
)

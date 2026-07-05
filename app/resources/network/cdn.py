from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, metric

CANONICAL_TYPE = "network/cdn"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Cdn/profiles",
    display_name="CDN profile",
    sync_property_paths=("provisioningState", "originResponseTimeout", "resourceState"),
    generic_arm_sync=True,
    fields=(
        field("resource_state", "props:resourceState", "Resource state", "status", "CDN_EGRESS_EXTENDED"),
        field("sku", "row:sku", "SKU", "configuration", "CDN_EGRESS_EXTENDED"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.cdn/profiles",
    canonical_type=CANONICAL_TYPE,
    display_name="CDN profile",
    doc_ref="microsoft-cdn-profiles-metrics",
    metrics=(),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "CDN_EGRESS_EXTENDED"),
)

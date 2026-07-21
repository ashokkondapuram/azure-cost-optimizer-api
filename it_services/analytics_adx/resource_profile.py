"""Resource profile — owned by analytics-adx IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, metric, utilization_metric as um

CANONICAL_TYPE = "analytics/adx"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Kusto/clusters",
    display_name="Azure Data Explorer",
    sync_property_paths=("provisioningState", "state", "sku"),
    generic_arm_sync=True,
    fields=(),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.kusto/clusters",
    canonical_type=CANONICAL_TYPE,
    display_name="Azure Data Explorer",
    doc_ref="microsoft-kusto-clusters-metrics",
    metrics=(
        um("IngestionVolumeInMB", "ingestion_bytes", "Data ingestion volume", aggregation="Total",
           rules=("ADX_INGESTION",)),
        um("QueryDuration", "query_duration_ms", "Query duration",
           rules=("ADX_INGESTION",)),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "ADX_INGESTION"),
)

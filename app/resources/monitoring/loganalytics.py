from app.resources.types import (
    ResourceMonitorProfile,
    TechnicalFetchSpec,
    field,
    metric,
    utilization_metric as um,
)

CANONICAL_TYPE = "monitoring/loganalytics"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.OperationalInsights/workspaces",
    display_name="Log Analytics workspace",
    sync_property_paths=("provisioningState", "retentionInDays", "sku", "features"),
    generic_arm_sync=True,
    fields=(
        field("retention_days", "props:retentionInDays", "Retention (days)", "configuration",
              "COST_LOG_ANALYTICS_REVIEW"),
        field("sku", "row:sku", "SKU", "configuration", "COST_LOG_ANALYTICS_REVIEW"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.operationalinsights/workspaces",
    canonical_type=CANONICAL_TYPE,
    display_name="Log Analytics workspace",
    doc_ref="microsoft-operationalinsights-workspaces-metrics",
    metrics=(
        um("BillableIngestionGB", "ingestion_gb", "Billable data ingested", aggregation="Total",
           rules=("COST_LOG_ANALYTICS_REVIEW",)),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "COST_LOG_ANALYTICS_REVIEW"),
)

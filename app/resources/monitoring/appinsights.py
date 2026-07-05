from app.resources.types import (
    ResourceMonitorProfile,
    TechnicalFetchSpec,
    field,
    metric,
    utilization_metric as um,
)

CANONICAL_TYPE = "monitoring/appinsights"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Insights/components",
    display_name="Application Insights",
    sync_property_paths=("Application_Type", "provisioningState", "WorkspaceResourceId"),
    generic_arm_sync=True,
    fields=(
        field("app_type", "props:Application_Type", "Application type", "configuration",
              "COST_APP_INSIGHTS_REVIEW"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.insights/components",
    canonical_type=CANONICAL_TYPE,
    display_name="Application Insights",
    doc_ref="microsoft-insights-components-metrics",
    metrics=(
        um("requests/count", "request_count", "Request count", aggregation="Total",
           rules=("COST_APP_INSIGHTS_REVIEW",)),
        um("availabilityResults/availabilityPercentage", "availability_pct", "Availability percentage",
           aggregation="Average",
           rules=("COST_APP_INSIGHTS_REVIEW",)),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "COST_APP_INSIGHTS_REVIEW"),
)

"""Resource profile — owned by analytics-databricks IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, metric, utilization_metric as um

CANONICAL_TYPE = "analytics/databricks"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Databricks/workspaces",
    display_name="Azure Databricks",
    sync_property_paths=("provisioningState", "parameters"),
    generic_arm_sync=True,
    fields=(),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.databricks/workspaces",
    canonical_type=CANONICAL_TYPE,
    display_name="Azure Databricks",
    doc_ref="microsoft-databricks-workspaces-metrics",
    metrics=(
        um("DbuUsage", "dbu_usage", "DBU usage", aggregation="Total",
           rules=("DATABRICKS_CLUSTER",)),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "DATABRICKS_CLUSTER"),
)

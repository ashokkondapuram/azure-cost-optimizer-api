"""Resource profile — owned by analytics-databricks IT service."""

from app.resources.types import TechnicalFetchSpec, metric

CANONICAL_TYPE = "analytics/databricks"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Databricks/workspaces",
    display_name="Azure Databricks",
    sync_property_paths=("provisioningState", "parameters"),
    generic_arm_sync=True,
    fields=(),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "DATABRICKS_CLUSTER"),
)

MONITOR_PROFILE = None

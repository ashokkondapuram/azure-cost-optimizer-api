"""Resource profile — owned by analytics-mlworkspace IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, metric, utilization_metric as um

CANONICAL_TYPE = "analytics/mlworkspace"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.MachineLearningServices/workspaces",
    display_name="Azure ML workspace",
    sync_property_paths=("provisioningState", "discoveryUrl"),
    generic_arm_sync=True,
    fields=(),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.machinelearningservices/workspaces",
    canonical_type=CANONICAL_TYPE,
    display_name="Azure ML workspace",
    doc_ref="microsoft-machinelearningservices-workspaces-metrics",
    metrics=(
        um("Completed Runs", "completed_runs", "Completed training runs", aggregation="Total",
           rules=("ML_WORKSPACE_COMPUTE",)),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "ML_WORKSPACE_COMPUTE"),
)

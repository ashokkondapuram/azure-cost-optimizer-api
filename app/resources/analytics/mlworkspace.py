from app.resources.types import TechnicalFetchSpec, metric

CANONICAL_TYPE = "analytics/mlworkspace"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.MachineLearningServices/workspaces",
    display_name="Azure ML workspace",
    sync_property_paths=("provisioningState", "discoveryUrl"),
    generic_arm_sync=True,
    fields=(),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "ML_WORKSPACE_COMPUTE"),
)

MONITOR_PROFILE = None

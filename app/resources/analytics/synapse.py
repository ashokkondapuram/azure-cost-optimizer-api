from app.resources.types import TechnicalFetchSpec, metric

CANONICAL_TYPE = "analytics/synapse"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Synapse/workspaces",
    display_name="Azure Synapse",
    sync_property_paths=("provisioningState", "settings"),
    generic_arm_sync=True,
    fields=(),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "SYNAPSE_PAUSE"),
)

MONITOR_PROFILE = None

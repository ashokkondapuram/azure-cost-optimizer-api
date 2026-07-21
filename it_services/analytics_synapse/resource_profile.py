"""Resource profile — owned by analytics-synapse IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, metric, utilization_metric as um

CANONICAL_TYPE = "analytics/synapse"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Synapse/workspaces",
    display_name="Azure Synapse",
    sync_property_paths=("provisioningState", "settings"),
    generic_arm_sync=True,
    fields=(),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.synapse/workspaces",
    canonical_type=CANONICAL_TYPE,
    display_name="Azure Synapse",
    doc_ref="microsoft-synapse-workspaces-metrics",
    metrics=(
        um("SQLPoolDataProcessedBytes", "sql_data_processed_bytes", "SQL pool data processed", aggregation="Total",
           rules=("SYNAPSE_PAUSE",)),
        um("BuiltinSqlPoolDataProcessedBytes", "sql_query_count", "Built-in SQL pool queries", aggregation="Total",
           rules=("SYNAPSE_PAUSE",)),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "SYNAPSE_PAUSE"),
)

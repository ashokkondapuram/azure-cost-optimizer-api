"""Resource profile — owned by integration-datafactory IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, metric, utilization_metric as um

CANONICAL_TYPE = "integration/datafactory"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.DataFactory/factories",
    display_name="Data Factory",
    sync_property_paths=("provisioningState", "publicNetworkAccess"),
    generic_arm_sync=True,
    fields=(),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.datafactory/factories",
    canonical_type=CANONICAL_TYPE,
    display_name="Data Factory",
    doc_ref="microsoft-datafactory-factories-metrics",
    metrics=(
        um("PipelineSucceededRuns", "pipeline_succeeded", "Successful pipeline runs", aggregation="Total",
           rules=("DATA_FACTORY_PIPELINE",)),
        um("PipelineFailedRuns", "pipeline_failed", "Failed pipeline runs", aggregation="Total",
           rules=("DATA_FACTORY_PIPELINE",)),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "DATA_FACTORY_PIPELINE"),
)

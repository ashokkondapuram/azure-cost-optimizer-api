from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "integration/logicapp"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Logic/workflows",
    display_name="Logic App",
    sync_property_paths=("state", "provisioningState"),
    generic_arm_sync=True,
    fields=(
        field("workflow_state", "props:state", "Workflow state", "utilization", "COST_LOGIC_APP_REVIEW"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.logic/workflows",
    canonical_type=CANONICAL_TYPE,
    display_name="Logic App",
    doc_ref="microsoft-logic-workflows-metrics",
    metrics=(
        um("RunsStarted", "runs_started", "Workflow runs started", aggregation="Total",
           rules=("COST_LOGIC_APP_REVIEW",)),
        um("RunsCompleted", "runs_completed", "Workflow runs completed", aggregation="Total",
           rules=("COST_LOGIC_APP_REVIEW",)),
    ),
)

"""Resource profile — owned by appservice-plan IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "appservice/plan"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Web/serverFarms",
    display_name="App Service plan",
    sync_property_paths=("numberOfSites", "reserved", "status", "maximumNumberOfWorkers", "targetWorkerCount"),
    fields=(
        field("app_count", "computed:app_count", "Hosted app count", "utilization",
              "PLAN_EMPTY", "PLAN_UNDERUTILIZED"),
        field("reserved", "props:reserved", "Linux reserved", "configuration"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.web/serverfarms",
    canonical_type=CANONICAL_TYPE,
    display_name="App Service plan",
    doc_ref="microsoft-web-serverfarms-metrics",
    metrics=(
        um("CpuPercentage", "cpu_pct", "App Service plan CPU utilization",
           rules=("PLAN_UNDERUTILIZED", "APP_SERVICE_PLAN_EXTENDED", "WEBAPP_PLAN_LOAD_LOW_EXTENDED")),
        um("MemoryPercentage", "memory_pct", "App Service plan memory utilization",
           rules=("PLAN_UNDERUTILIZED", "APP_SERVICE_PLAN_EXTENDED", "ASP_CONSOLIDATION_CANDIDATE_EXTENDED")),
    ),
)

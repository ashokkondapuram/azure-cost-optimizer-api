"""Resource profile — owned by appservice-webapp IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "appservice/webapp"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Web/sites",
    display_name="App Service",
    sync_property_paths=(
        "kind", "state", "alwaysOn", "httpsOnly", "clientAffinityEnabled",
        "serverFarmId", "siteConfig",
    ),
    fields=(
        field("state", "props:state", "App state", "utilization", "APP_IDLE", "APP_ALWAYS_ON_OFF"),
        field("alwaysOn", "props:alwaysOn", "Always On", "configuration", "APP_ALWAYS_ON_OFF"),
        field("https_only", "props:httpsOnly", "HTTPS only", "governance"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.web/sites",
    canonical_type=CANONICAL_TYPE,
    display_name="App Service web app",
    doc_ref="microsoft-web-sites-metrics",
    metrics=(
        um("CpuTime", "cpu_time_sec", "CPU time consumed", aggregation="Total",
           rules=("APP_IDLE", "WEBAPP_STOPPED_EXTENDED")),
        um("AverageMemoryWorkingSet", "avg_memory_bytes", "Average memory working set",
           aggregation="Average",
           rules=("APP_IDLE", "WEBAPP_ALWAYS_ON_EXTENDED")),
        um("Requests", "request_count", "HTTP requests", aggregation="Total",
           rules=("APP_IDLE", "WEBAPP_STOPPED_EXTENDED")),
    ),
)

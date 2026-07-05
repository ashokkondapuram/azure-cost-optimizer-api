from app.resources.types import ResourceMonitorProfile, utilization_metric as um

CANONICAL_TYPE = "database/sql"

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.sql/servers/databases",
    canonical_type=CANONICAL_TYPE,
    display_name="SQL database",
    doc_ref="microsoft-sql-servers-databases-metrics",
    metrics=(
        um("cpu_percent", "cpu_pct", "Database CPU utilization",
           rules=("SQL_IDLE", "SQL_SERVERLESS_EXTENDED")),
        um("storage_percent", "storage_pct", "Database storage utilization",
           rules=("SQL_IDLE",)),
    ),
)

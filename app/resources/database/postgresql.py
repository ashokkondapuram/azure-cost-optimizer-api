from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "database/postgresql"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.DBforPostgreSQL/flexibleServers",
    display_name="PostgreSQL flexible server",
    sync_property_paths=("storage", "highAvailability", "state", "version", "backup"),
    fields=(
        field("storage_gb", "props:storage.storageSizeGB", "Storage size (GB)", "capacity",
              "POSTGRES_STORAGE_OVERSIZE"),
        field("ha_mode", "props:highAvailability.mode", "High availability", "configuration"),
        field("version", "props:version", "PostgreSQL version", "configuration"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.dbforpostgresql/flexibleservers",
    canonical_type=CANONICAL_TYPE,
    display_name="PostgreSQL flexible server",
    doc_ref="microsoft-dbforpostgresql-flexibleservers-metrics",
    metrics=(
        um("cpu_percent", "cpu_pct", "PostgreSQL CPU utilization",
           rules=("POSTGRESQL_BURSTABLE_EXTENDED",)),
        um("memory_percent", "memory_pct", "PostgreSQL memory utilization",
           rules=("POSTGRESQL_BURSTABLE_EXTENDED",)),
        um("storage_percent", "storage_pct", "PostgreSQL storage utilization",
           rules=("POSTGRES_STORAGE_EXTENDED",)),
    ),
)

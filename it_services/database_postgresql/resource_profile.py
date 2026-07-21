"""Resource profile — owned by database-postgresql IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "database/postgresql"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.DBforPostgreSQL/flexibleServers",
    display_name="PostgreSQL flexible server",
    sync_property_paths=("storage", "highAvailability", "state", "version", "backup"),
    fields=(
        field("storage_gb", "props:storage.storageSizeGB", "Storage size (GB)", "capacity",
              "POSTGRESQL_STORAGE_EXTENDED", "POSTGRESQL_STORAGE_EXPANSION"),
        field("ha_mode", "props:highAvailability.mode", "High availability", "configuration",
              "POSTGRESQL_HA_UNNECESSARY", "POSTGRESQL_HA_REQUIRED"),
        field("version", "props:version", "PostgreSQL version", "configuration",
              "POSTGRESQL_VERSION_OUTDATED"),
        field("backup_retention_days", "props:backup.retentionDays", "Backup retention (days)", "configuration",
              "POSTGRESQL_BACKUP_RETENTION_REVIEW"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.dbforpostgresql/flexibleservers",
    canonical_type=CANONICAL_TYPE,
    display_name="PostgreSQL flexible server",
    doc_ref="microsoft-dbforpostgresql-flexibleservers-metrics",
    metrics=(
        um("cpu_percent", "cpu_pct", "PostgreSQL CPU utilization",
           aggregation="Average",
           rules=(
               "POSTGRESQL_BURSTABLE_EXTENDED", "POSTGRESQL_LOW_COMPUTE_UTILIZATION",
               "POSTGRESQL_HIGH_COMPUTE_DEMAND",
           )),
        um("memory_percent", "memory_pct", "PostgreSQL memory utilization",
           aggregation="Average",
           rules=(
               "POSTGRESQL_BURSTABLE_EXTENDED", "POSTGRESQL_LOW_COMPUTE_UTILIZATION",
               "POSTGRESQL_MEMORY_PRESSURE",
           )),
        um("storage_percent", "storage_pct", "PostgreSQL storage utilization",
           aggregation="Average",
           rules=("POSTGRESQL_STORAGE_EXTENDED", "POSTGRESQL_STORAGE_EXPANSION")),
        um("disk_iops_consumed_percentage", "disk_iops_pct", "Disk IOPS consumed",
           aggregation="Maximum",
           rules=("POSTGRESQL_IOPS_PRESSURE",)),
        um("active_connections", "active_connections", "Active connections",
           aggregation="Maximum",
           rules=("POSTGRESQL_CONNECTION_POOL_RISK",)),
        um("max_connections", "max_connections", "Peak connections",
           aggregation="Maximum",
           rules=("POSTGRESQL_CONNECTION_POOL_RISK",)),
        um("physical_replication_delay_in_seconds", "replication_lag_sec", "Replication lag",
           aggregation="Maximum",
           rules=("POSTGRESQL_READ_REPLICA_ANALYSIS",)),
        um("backup_storage_used", "backup_storage_bytes", "Backup storage used",
           aggregation="Maximum",
           rules=("POSTGRESQL_BACKUP_RETENTION_REVIEW",)),
        um("connections_failed", "failed_connections", "Failed connections",
           aggregation="Total",
           rules=("POSTGRESQL_CONNECTION_POOL_RISK",)),
    ),
)

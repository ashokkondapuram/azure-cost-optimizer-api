"""Resource profile — owned by backup-recoveryvault IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, metric, utilization_metric as um

CANONICAL_TYPE = "backup/recoveryvault"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.RecoveryServices/vaults",
    display_name="Recovery Services vault",
    sync_property_paths=("provisioningState", "sku"),
    generic_arm_sync=True,
    fields=(),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.recoveryservices/vaults",
    canonical_type=CANONICAL_TYPE,
    display_name="Recovery Services vault",
    doc_ref="microsoft-recoveryservices-vaults-metrics",
    metrics=(
        um("BackupHealthEvent", "backup_health_events", "Backup health events", aggregation="Count",
           rules=("BACKUP_RETENTION",)),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "BACKUP_RETENTION"),
)

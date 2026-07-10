"""Resource profile — owned by compute-disk IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "compute/disk"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Compute/disks",
    display_name="Managed disk",
    sync_property_paths=(
        "diskSizeGB", "diskState", "diskIOPSReadWrite", "diskMBpsReadWrite",
        "managedBy", "managedByExtended", "shareInfo", "encryption", "provisioningState",
        "timeCreated", "lastOwnershipUpdateTime", "creationData", "tier", "burstingEnabled",
    ),
    fields=(
        field("disk_state", "props:diskState", "Disk state", "association",
              "DISK_UNATTACHED", "DISK_OVERSIZE", "DISK_UNUSED_EXTENDED", "DISK_UNDERPROVISIONED"),
        field("size_gb", "props:diskSizeGB", "Disk size (GB)", "capacity",
              "DISK_UNATTACHED", "DISK_OVERSIZE", "DISK_UNDERPROVISIONED"),
        field("provisioned_iops", "props:diskIOPSReadWrite", "Provisioned IOPS", "capacity",
              "DISK_OVERSIZE_EXTENDED", "DISK_UNDERPROVISIONED"),
        field("provisioned_mbps", "props:diskMBpsReadWrite", "Provisioned throughput (MB/s)", "capacity",
              "DISK_OVERSIZE_EXTENDED", "DISK_UNDERPROVISIONED"),
        field("sku", "row:sku", "SKU", "configuration",
              "DISK_UNATTACHED", "DISK_OVERSIZE", "DISK_OVERSIZE_EXTENDED", "DISK_UNDERPROVISIONED"),
        field("managed_by", "props:managedBy", "Attached to", "association", "DISK_UNATTACHED"),
        field("last_managed_by", "props:lastManagedBy", "Last attached to", "association",
              "DISK_UNUSED_EXTENDED"),
        field("time_created", "props:timeCreated", "Created", "configuration",
              "DISK_UNUSED_EXTENDED"),
        field("last_ownership_update", "props:lastOwnershipUpdateTime", "Last ownership update time",
              "utilization", "DISK_UNUSED_EXTENDED"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.compute/disks",
    canonical_type=CANONICAL_TYPE,
    display_name="Managed disk",
    doc_ref="microsoft-compute-disks-metrics",
    # Azure Monitor supported metrics (learn.microsoft.com/.../microsoft-compute-disks-metrics)
    metrics=(
        um("Composite Disk Read Bytes/sec", "disk_read_bps", "Disk read throughput",
           aggregation="Average",
           rules=("DISK_OVERSIZE", "DISK_UNUSED_EXTENDED", "DISK_OVERSIZE_EXTENDED")),
        um("Composite Disk Write Bytes/sec", "disk_write_bps", "Disk write throughput",
           aggregation="Average",
           rules=("DISK_OVERSIZE", "DISK_UNUSED_EXTENDED", "DISK_OVERSIZE_EXTENDED")),
        um("Composite Disk Read Operations/sec", "disk_read_iops", "Disk read IOPS",
           aggregation="Average",
           rules=("DISK_OVERSIZE_EXTENDED", "DISK_UNDERPROVISIONED")),
        um("Composite Disk Write Operations/sec", "disk_write_iops", "Disk write IOPS",
           aggregation="Average",
           rules=("DISK_OVERSIZE_EXTENDED", "DISK_UNDERPROVISIONED")),
        um("DiskPaidBurstIOPS", "disk_paid_burst_iops", "On-demand burst operations",
           aggregation="Average",
           rules=()),
    ),
)

"""Resource profile — owned by compute-disk IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field

from it_services.compute_disk.assessment_bridge import (
    build_disk_monitor_profile,
    disk_sync_property_paths,
)

CANONICAL_TYPE = "compute/disk"

# Analysis-facing field defs (fact extraction); sync paths and metrics come from assessment.
_DISK_FIELDS = (
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
)

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Compute/disks",
    display_name="Managed disk",
    sync_property_paths=disk_sync_property_paths(),
    fields=_DISK_FIELDS,
)

MONITOR_PROFILE: ResourceMonitorProfile = build_disk_monitor_profile()

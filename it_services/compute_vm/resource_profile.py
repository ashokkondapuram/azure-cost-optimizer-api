"""Resource profile — owned by compute-vm IT service."""

from app.resources.types import (
    ResourceMonitorProfile,
    TechnicalFetchSpec,
    field,
    utilization_metric as um,
)

CANONICAL_TYPE = "compute/vm"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Compute/virtualMachines",
    display_name="Virtual machine",
    sync_property_paths=(
        "hardwareProfile", "storageProfile", "osProfile",
        "provisioningState", "powerState", "instanceView", "timeCreated",
    ),
    fields=(
        field("vm_size", "props:hardwareProfile.vmSize", "VM size", "configuration",
              "VM_IDLE", "VM_OVERSIZE", "VM_NO_RESERVED", "VM_RIGHTSIZE_FAMILY"),
        field("power_state", "computed:power_state", "Power state", "utilization",
              "VM_IDLE", "VM_STOPPED_DEALLOCATED", "VM_STOPPED_BILLING_EXTENDED", "VM_NO_RESERVED"),
        field("provisioning_state", "props:provisioningState", "Provisioning state", "configuration"),
        field("time_created", "props:timeCreated", "Time created", "configuration",
              "VM_COMMITMENT_CANDIDATE"),
        field("environment", "tag:Environment", "Environment tag", "governance",
              "SPOT_OPPORTUNITY", "VM_MISSING_GOVERNANCE_TAGS"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.compute/virtualmachines",
    canonical_type=CANONICAL_TYPE,
    display_name="Virtual machine",
    doc_ref="microsoft-compute-virtualmachines-metrics",
    metrics=(
        um("Percentage CPU", "avg_cpu_pct", "Average CPU utilization",
           aggregation="Average",
           rules=("VM_IDLE", "VM_OVERSIZE", "VM_UNDERUTILIZED_EXTENDED", "VM_RIGHTSIZE_FAMILY", "VM_SKU_SIZING_EXTENDED")),
        um("Available Memory Bytes", "avg_available_memory_bytes", "Available memory",
           rules=("VM_OVERSIZE", "VM_SKU_SIZING_EXTENDED", "VM_RIGHTSIZE_FAMILY", "VM_MEMORY_PRESSURE_EXTENDED"),
           aggregation="Average"),
        um("Network Out Total", "network_out_bytes", "Network egress bytes",
           aggregation="Total",
           rules=("VM_EGRESS_HIGH_EXTENDED", "VM_NETWORK_BOTTLENECK")),
        um("OS Disk Queue Depth", "disk_queue_depth", "OS disk queue depth",
           aggregation="Average",
           rules=("VM_DISK_BOTTLENECK",)),
    ),
)

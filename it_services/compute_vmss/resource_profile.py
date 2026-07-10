"""Resource profile — owned by compute-vmss IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "compute/vmss"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Compute/virtualMachineScaleSets",
    display_name="Virtual machine scale set",
    sync_property_paths=(
        "virtualMachineProfile", "sku", "provisioningState",
        "orchestrationMode", "upgradePolicy", "singlePlacementGroup",
        "platformFaultDomainCount",
    ),
    fields=(
        field("vm_size", "props:virtualMachineProfile.hardwareProfile.vmSize", "VM size", "configuration",
              "VM_IDLE", "VM_OVERSIZE", "VM_RIGHTSIZE_FAMILY"),
        field("instance_count", "sku:capacity", "Instance count", "capacity",
              "VM_IDLE", "AKS_UNDERUTILIZED"),
        field("orchestration_mode", "props:orchestrationMode", "Orchestration mode", "configuration"),
        field("provisioning_state", "props:provisioningState", "Provisioning state", "configuration"),
        field("time_created", "props:oldest_instance_time_created", "Oldest instance created", "configuration",
              "VM_COMMITMENT_CANDIDATE"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.compute/virtualmachinescalesets",
    canonical_type=CANONICAL_TYPE,
    display_name="Virtual machine scale set",
    doc_ref="microsoft-compute-virtualmachinescalesets-metrics",
    metrics=(
        um("Percentage CPU", "avg_cpu_pct", "Average CPU across scale set instances",
           aggregation="Average",
           rules=("VM_IDLE", "VM_OVERSIZE", "VM_RIGHTSIZE_FAMILY", "VM_SKU_SIZING_EXTENDED", "VMSS_AUTOSCALE_TUNING_EXTENDED")),
        um("Available Memory Bytes", "avg_available_memory_bytes", "Available memory across instances",
           rules=("VM_OVERSIZE", "VM_SKU_SIZING_EXTENDED", "VM_RIGHTSIZE_FAMILY"),
           aggregation="Average"),
        um("Network Out Total", "network_out_bytes", "Network egress bytes",
           aggregation="Total",
           rules=("VMSS_AUTOSCALE_TUNING_EXTENDED",)),
    ),
)

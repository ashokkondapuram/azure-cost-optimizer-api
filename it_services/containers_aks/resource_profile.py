"""Resource profile — owned by containers-aks IT service."""

from app.resources.types import (
    ResourceMonitorProfile,
    TechnicalFetchSpec,
    field,
    metric,
    utilization_metric as um,
)

CANONICAL_TYPE = "containers/aks"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.ContainerService/managedClusters",
    display_name="AKS cluster",
    sync_property_paths=(
        "kubernetesVersion", "agentPoolProfiles", "powerState",
        "networkProfile", "provisioningState", "enableRBAC",
        "nodeProvisioningProfile", "nodeResourceGroup",
    ),
    enrich_if_missing=("nodeProvisioningProfile", "nodeResourceGroup"),
    fields=(
        field("kubernetes_version", "props:kubernetesVersion", "Kubernetes version", "configuration",
              "AKS_OLD_VERSION"),
        field("node_auto_provisioning", "computed:node_auto_provisioning", "Node auto provisioning",
              "configuration",
              "AKS_NO_AUTOSCALER_EXTENDED", "AKS_POOL_CONSOLIDATION", "AKS_IDLE_POOL_EXTENDED"),
        field("pool_count", "computed:pool_count", "Node pool count", "capacity", "AKS_EMPTY_POOL"),
        field("node_count", "computed:node_count", "Total node count", "capacity",
              "AKS_EMPTY_POOL", "AKS_UNDERUTILIZED"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.containerservice/managedclusters",
    canonical_type=CANONICAL_TYPE,
    display_name="AKS cluster",
    doc_ref="microsoft-containerservice-managedclusters-metrics",
    metrics=(
        um("node_cpu_usage_percentage", "cluster_cpu_pct", "Cluster node CPU utilization",
           rules=("AKS_UNDERUTILIZED", "AKS_IDLE_POOL_EXTENDED")),
        um("node_memory_working_set_percentage", "cluster_mem_pct", "Cluster node memory utilization",
           rules=("AKS_UNDERUTILIZED", "AKS_IDLE_POOL_EXTENDED", "AKS_NODE_MEMORY_PRESSURE_EXTENDED")),
        um("kube_pod_status_ready", "pod_count", "Ready pod count",
           aggregation="Maximum",
           primary_stat="maximum",
           rules=("AKS_POD_DENSITY_EXTENDED",)),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("k8s_agent", "node_cpu_usage", "node_cpu_pct",
           "Per-node CPU from K8s utilization agent", "P7D", "AKS_UNDERUTILIZED"),
    metric("k8s_agent", "node_memory_usage", "node_mem_pct",
           "Per-node memory from K8s utilization agent", "P7D", "AKS_UNDERUTILIZED"),
)

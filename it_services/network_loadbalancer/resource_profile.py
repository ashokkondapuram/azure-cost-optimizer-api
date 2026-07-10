"""Resource profile — owned by network-loadbalancer IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "network/loadbalancer"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/loadBalancers",
    display_name="Load balancer",
    sync_property_paths=(
        "backendAddressPools", "frontendIPConfigurations", "loadBalancingRules",
        "probes", "provisioningState",
    ),
    fields=(
        field("backend_pool_count", "computed:backend_pool_count", "Backend pool count", "association",
              "LB_NO_BACKEND", "LB_IDLE_EXTENDED"),
        field("all_backends_empty", "computed:all_backends_empty", "All backends empty", "utilization",
              "LB_NO_BACKEND"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/loadbalancers",
    canonical_type=CANONICAL_TYPE,
    display_name="Load balancer",
    doc_ref="microsoft-network-loadbalancers-metrics",
    metrics=(
        um("DipAvailability", "backend_availability_pct", "Backend pool availability",
           aggregation="Average",
           rules=("LB_NO_BACKEND", "LB_IDLE_EXTENDED", "LOAD_BALANCER_IDLE_EXTENDED")),
        um("ByteCount", "byte_count", "Load balancer traffic volume", aggregation="Total",
           rules=("LB_IDLE_EXTENDED", "LOAD_BALANCER_IDLE_EXTENDED", "LOAD_BALANCER_THROUGHPUT_RIGHTSIZE")),
        um("ByteCount", "byte_count_peak", "Peak load balancer traffic", aggregation="Maximum",
           rules=("LOAD_BALANCER_THROUGHPUT_RIGHTSIZE",)),
        um("UsedSNATPorts", "used_snat_ports", "Used SNAT ports", aggregation="Maximum",
           rules=("LOAD_BALANCER_SNAT_PRESSURE",)),
        um("AllocatedSNATPorts", "allocated_snat_ports", "Allocated SNAT ports", aggregation="Maximum",
           rules=("LOAD_BALANCER_SNAT_PRESSURE",)),
        um("SNATConnectionCount", "snat_connection_count", "SNAT connections", aggregation="Total",
           rules=("LOAD_BALANCER_SNAT_PRESSURE",)),
    ),
)

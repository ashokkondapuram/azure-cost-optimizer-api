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
           rules=("LB_NO_BACKEND", "LB_IDLE_EXTENDED")),
        um("ByteCount", "byte_count", "Load balancer traffic volume", aggregation="Total",
           rules=("LB_IDLE_EXTENDED",)),
    ),
)

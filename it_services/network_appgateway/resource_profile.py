"""Resource profile — owned by network-appgateway IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "network/appgateway"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Network/applicationGateways",
    display_name="Application gateway",
    sync_property_paths=(
        "httpListeners", "requestRoutingRules", "backendAddressPools",
        "backendHttpSettingsCollection", "frontendIPConfigurations",
        "frontendPorts", "probes", "sku", "provisioningState",
    ),
    fields=(
        field("http_listener_count", "computed:http_listener_count", "HTTP listener count", "utilization",
              "APPGW_UNUSED", "APP_GATEWAY_IDLE_EXTENDED"),
        field("sku_tier", "row:sku", "SKU tier", "configuration", "APPGW_UNUSED"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.network/applicationgateways",
    canonical_type=CANONICAL_TYPE,
    display_name="Application gateway",
    doc_ref="microsoft-network-applicationgateways-metrics",
    metrics=(
        um("HealthyHostCount", "healthy_host_count", "Healthy backend hosts",
           aggregation="Average",
           rules=("APPGW_UNUSED", "APP_GATEWAY_IDLE_EXTENDED")),
        um("Throughput", "throughput_bytes", "Application gateway throughput",
           rules=("APP_GATEWAY_IDLE_EXTENDED",)),
        um("TotalRequests", "request_count", "Total requests served", aggregation="Total",
           rules=("APP_GATEWAY_IDLE_EXTENDED",)),
        um("EstimatedBilledCapacityUnits", "billed_capacity_units", "Billed capacity units",
           aggregation="Average",
           rules=("APP_GATEWAY_CU_SATURATION", "APP_GATEWAY_CU_RIGHTSIZE_DOWN")),
        um("CurrentConnections", "current_connections", "Active connections",
           rules=("APP_GATEWAY_CU_SATURATION",)),
    ),
)

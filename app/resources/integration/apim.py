from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "integration/apim"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.ApiManagement/service",
    display_name="API Management",
    sync_property_paths=("provisioningState", "publisherEmail", "virtualNetworkType"),
    generic_arm_sync=True,
    fields=(
        field("vnet_type", "props:virtualNetworkType", "VNet integration", "configuration",
              "COST_APIM_REVIEW"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.apimanagement/service",
    canonical_type=CANONICAL_TYPE,
    display_name="API Management",
    doc_ref="microsoft-apimanagement-service-metrics",
    metrics=(
        um("Requests", "request_count", "API requests", aggregation="Total",
           rules=("COST_APIM_REVIEW",)),
        um("Capacity", "capacity_pct", "Gateway capacity utilization",
           rules=("COST_APIM_REVIEW",)),
    ),
)

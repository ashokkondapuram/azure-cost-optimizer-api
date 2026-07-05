from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "containers/acr"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.ContainerRegistry/registries",
    display_name="Container registry",
    sync_property_paths=(
        "provisioningState", "adminUserEnabled", "policies", "zoneRedundancy",
        "publicNetworkAccess", "networkRuleSet", "privateEndpointConnections",
        "replicationCount", "_replications",
    ),
    fields=(
        field("sku", "row:sku", "SKU", "configuration",
              "ACR_PREMIUM_EXTENDED", "ACR_STANDARD_EXTENDED", "ACR_GEO_REPLICATION_EXTENDED",
              "ACR_STORAGE_HIGH_EXTENDED", "ACR_RETENTION_DISABLED_EXTENDED"),
        field("provisioning_state", "props:provisioningState", "Provisioning state", "configuration",
              "ACR_PREMIUM_EXTENDED", "ACR_STANDARD_EXTENDED"),
        field("admin_user_enabled", "props:adminUserEnabled", "Admin user enabled", "governance",
              "ACR_PREMIUM_EXTENDED"),
        field("zone_redundancy", "props:zoneRedundancy", "Zone redundancy", "configuration",
              "ACR_PREMIUM_EXTENDED", "ACR_GEO_REPLICATION_EXTENDED"),
        field("replication_count", "computed:replication_count", "Geo-replication count", "configuration",
              "ACR_GEO_REPLICATION_EXTENDED", "ACR_PREMIUM_EXTENDED"),
        field("retention_policy_enabled", "computed:retention_policy_enabled", "Retention policy enabled", "configuration",
              "ACR_RETENTION_DISABLED_EXTENDED"),
        field("retention_policy_days", "computed:retention_policy_days", "Retention policy days", "configuration",
              "ACR_RETENTION_DISABLED_EXTENDED"),
        field("private_endpoint_count", "computed:private_endpoint_count", "Private endpoint count", "association",
              "ACR_PREMIUM_EXTENDED"),
        field("public_network_access", "props:publicNetworkAccess", "Public network access", "configuration",
              "ACR_PREMIUM_EXTENDED"),
        field("network_default_action", "props:networkRuleSet.defaultAction", "Network default action", "configuration",
              "ACR_PREMIUM_EXTENDED"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.containerregistry/registries",
    canonical_type=CANONICAL_TYPE,
    display_name="Container registry",
    doc_ref="microsoft-containerregistry-registries-metrics",
    metrics=(
        um("TotalPullCount", "pull_count", "Total image pulls", aggregation="Total",
           rules=("ACR_PREMIUM_EXTENDED", "ACR_STANDARD_EXTENDED", "ACR_STORAGE_HIGH_EXTENDED")),
        um("TotalPushCount", "push_count", "Total image pushes", aggregation="Total",
           rules=("ACR_STORAGE_HIGH_EXTENDED",)),
        um("StorageUsed", "storage_used_bytes", "Registry storage used",
           aggregation="Average",
           rules=("ACR_PREMIUM_EXTENDED", "ACR_STANDARD_EXTENDED", "ACR_STORAGE_HIGH_EXTENDED",
                  "ACR_RETENTION_DISABLED_EXTENDED")),
    ),
)

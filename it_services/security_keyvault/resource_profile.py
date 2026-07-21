"""Resource profile — owned by security-keyvault IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "security/keyvault"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.KeyVault/vaults",
    display_name="Key vault",
    sync_property_paths=(
        "enableSoftDelete", "enableRbacAuthorization", "enablePurgeProtection",
        "sku", "provisioningState", "networkAcls", "publicNetworkAccess", "tenantId",
    ),
    fields=(
        field("sku", "row:sku", "SKU", "configuration",
              "KEYVAULT_PREMIUM_EXTENDED", "KEYVAULT_IDLE_EXTENDED", "KEYVAULT_HIGH_OPS_EXTENDED"),
        field("soft_delete_enabled", "props:enableSoftDelete", "Soft delete", "governance",
              "KEYVAULT_SOFT_DELETE_OFF", "KEYVAULT_PROTECTION_EXTENDED"),
        field("purge_protection_enabled", "props:enablePurgeProtection", "Purge protection", "governance",
              "KEYVAULT_SOFT_DELETE_OFF", "KEYVAULT_PROTECTION_EXTENDED"),
        field("rbac_enabled", "props:enableRbacAuthorization", "RBAC authorization", "governance",
              "KEYVAULT_PROTECTION_EXTENDED"),
        field("public_network_access", "props:publicNetworkAccess", "Public network access", "configuration",
              "KEYVAULT_PROTECTION_EXTENDED", "KEYVAULT_PREMIUM_EXTENDED"),
        field("network_default_action", "computed:network_default_action", "Network default action", "configuration",
              "KEYVAULT_PROTECTION_EXTENDED"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.keyvault/vaults",
    canonical_type=CANONICAL_TYPE,
    display_name="Key vault",
    doc_ref="microsoft-keyvault-vaults-metrics",
    metrics=(
        um("ServiceApiHit", "api_hits", "Key Vault API hits", aggregation="Count",
           rules=("KEYVAULT_IDLE_EXTENDED", "KEYVAULT_PREMIUM_EXTENDED", "KEYVAULT_HIGH_OPS_EXTENDED")),
        um("ServiceApiResult", "api_results", "Key Vault API results", aggregation="Count",
           rules=("KEYVAULT_HIGH_OPS_EXTENDED",)),
        um("Availability", "availability_pct", "Key Vault availability",
           aggregation="Average",
           rules=("KEYVAULT_IDLE_EXTENDED", "KEYVAULT_HIGH_OPS_EXTENDED")),
    ),
)

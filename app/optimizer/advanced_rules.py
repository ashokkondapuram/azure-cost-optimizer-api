"""Advanced rule catalog for the optimization engine.

These rules extend the base engine with stronger reliability, business controls,
and workload-specific optimization logic. Rules remain declarative so thresholds
can be overridden from DB profiles or request payloads.
"""
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class Category(str, Enum):
    COMPUTE = "COMPUTE"
    KUBERNETES = "KUBERNETES"
    STORAGE = "STORAGE"
    NETWORK = "NETWORK"
    DATABASE = "DATABASE"
    SECURITY = "SECURITY"
    COST = "COST"
    GOVERNANCE = "GOVERNANCE"
    RELIABILITY = "RELIABILITY"


@dataclass
class AdvancedRule:
    id: str
    name: str
    description: str
    category: Category
    severity: Severity
    enabled: bool = True
    evaluation_window_days: int = 7
    min_monthly_savings_usd: float = 5.0
    cpu_idle_pct: float = 5.0
    cpu_oversize_pct: float = 20.0
    memory_idle_pct: float = 15.0
    node_cpu_idle_pct: float = 10.0
    node_memory_idle_pct: float = 15.0
    max_unattached_disk_days: int = 14
    snapshot_retention_days: int = 90
    snapshot_min_size_gb: int = 0
    disk_io_idle_bps: float = 1024.0
    disk_idle_min_size_gb: int = 128
    disk_iops_block_downgrade_pct: float = 20.0
    disk_iops_high_util_pct: float = 80.0
    acr_pull_count_low: float = 500.0
    acr_storage_high_gb: float = 50.0
    acr_push_count_low: float = 100.0
    kv_api_hits_idle: float = 10.0
    kv_api_hits_high: float = 50_000.0
    public_ip_idle_days: int = 7
    min_rightsize_savings_pct: float = 0.20
    min_reserved_coverage_hours: int = 500
    nonprod_shutdown_hours_per_day: int = 14
    require_tags: list[str] = field(default_factory=lambda: ["environment", "owner", "costCenter"])
    prod_tag_values: list[str] = field(default_factory=lambda: ["prod", "production"])
    nonprod_tag_values: list[str] = field(default_factory=lambda: ["dev", "test", "qa", "staging", "sandbox"])
    spot_allowed_envs: list[str] = field(default_factory=lambda: ["dev", "test", "qa", "batch", "ci"])
    aks_min_system_nodes: int = 2
    aks_max_idle_node_ratio: float = 0.30
    storage_cool_after_days: int = 30
    storage_archive_after_days: int = 90
    sql_serverless_candidate_cpu_pct: float = 10.0
    cosmos_autoscale_candidate_utilization_pct: float = 25.0
    vm_uptime_hours_candidate: int = 500
    redis_premium_min_capacity: int = 1
    asp_min_apps_for_premium: int = 2
    node_count_min: int = 1
    db_dtu_idle_pct: float = 5.0
    budget_warn_pct: float = 80.0
    budget_crit_pct: float = 95.0
    reserved_savings_threshold: float = 0.30
    savings_plan_min_monthly_usd: float = 500.0
    cluster_dev_hours: str = "08:00-18:00"
    private_dns_max_default_record_sets: int = 2


ADVANCED_RULES: dict[str, AdvancedRule] = {
    "VM_UNDERUTILIZED_EXTENDED": AdvancedRule(
        id="VM_UNDERUTILIZED_EXTENDED",
        name="Extended VM Underutilization",
        description="VM sustained low CPU and memory over evaluation window with sufficient cost to justify action.",
        category=Category.COMPUTE,
        severity=Severity.HIGH,
    ),
    "VM_RIGHTSIZE_FAMILY": AdvancedRule(
        id="VM_RIGHTSIZE_FAMILY",
        name="VM Family Right-Sizing",
        description="Suggest smaller VM family or burstable family when workload shape is consistently low.",
        category=Category.COMPUTE,
        severity=Severity.MEDIUM,
    ),
    "VM_COMMITMENT_CANDIDATE": AdvancedRule(
        id="VM_COMMITMENT_CANDIDATE",
        name="Reserved Instance or Savings Plan Candidate",
        description="Stable-running VMs are candidates for Reservations or Savings Plans.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "VM_MISSING_GOVERNANCE_TAGS": AdvancedRule(
        id="VM_MISSING_GOVERNANCE_TAGS",
        name="Missing Governance Tags",
        description="Resource is missing required ownership, environment, or cost allocation tags.",
        category=Category.GOVERNANCE,
        severity=Severity.HIGH,
    ),
    "VM_STOPPED_BILLING_EXTENDED": AdvancedRule(
        id="VM_STOPPED_BILLING_EXTENDED",
        name="VM Stopped But Still Billing",
        description="VM is stopped (not deallocated) and may still incur compute charges.",
        category=Category.COMPUTE,
        severity=Severity.HIGH,
    ),
    "VM_SKU_SIZING_EXTENDED": AdvancedRule(
        id="VM_SKU_SIZING_EXTENDED",
        name="VM SKU rightsizing",
        description="CPU and memory utilization suggest a smaller or larger VM SKU within or across families.",
        category=Category.COMPUTE,
        severity=Severity.MEDIUM,
        cpu_idle_pct=25.0,
        memory_idle_pct=30.0,
        cpu_oversize_pct=75.0,
    ),
    "AKS_IDLE_POOL_EXTENDED": AdvancedRule(
        id="AKS_IDLE_POOL_EXTENDED",
        name="Extended AKS Idle Pool Detection",
        description="Node pool has too many idle nodes relative to total pool size.",
        category=Category.KUBERNETES,
        severity=Severity.HIGH,
    ),
    "AKS_NONPROD_SCHEDULING": AdvancedRule(
        id="AKS_NONPROD_SCHEDULING",
        name="AKS Non-Prod Scheduling",
        description="Non-production clusters should use shutdown schedules or scale-to-zero patterns where possible.",
        category=Category.KUBERNETES,
        severity=Severity.MEDIUM,
    ),
    "AKS_SYSTEM_POOL_RELIABILITY": AdvancedRule(
        id="AKS_SYSTEM_POOL_RELIABILITY",
        name="AKS System Pool Reliability Baseline",
        description="Production system pools should maintain minimum healthy node count for reliability.",
        category=Category.RELIABILITY,
        severity=Severity.CRITICAL,
    ),
    "DISK_UNUSED_EXTENDED": AdvancedRule(
        id="DISK_UNUSED_EXTENDED",
        name="Extended Unused Disk Detection",
        description="Disk is unattached long enough to be considered waste, or attached with idle I/O on large disks.",
        category=Category.COMPUTE,
        severity=Severity.HIGH,
        max_unattached_disk_days=14,
        disk_io_idle_bps=1024.0,
        disk_idle_min_size_gb=128,
        disk_iops_block_downgrade_pct=20.0,
    ),
    "SNAPSHOT_RETENTION_EXTENDED": AdvancedRule(
        id="SNAPSHOT_RETENTION_EXTENDED",
        name="Extended Snapshot Retention",
        description="Snapshots older than the retention threshold should be removed after recovery validation.",
        category=Category.COMPUTE,
        severity=Severity.LOW,
        snapshot_retention_days=90,
        snapshot_min_size_gb=0,
        min_monthly_savings_usd=1.0,
    ),
    "PUBLIC_IP_IDLE_EXTENDED": AdvancedRule(
        id="PUBLIC_IP_IDLE_EXTENDED",
        name="Extended Public IP Idle Detection",
        description="Unassociated static public IPs create direct monthly waste.",
        category=Category.NETWORK,
        severity=Severity.HIGH,
    ),
    "LOAD_BALANCER_IDLE_EXTENDED": AdvancedRule(
        id="LOAD_BALANCER_IDLE_EXTENDED",
        name="Extended Idle Load Balancer Detection",
        description="Load balancers without backend instances create avoidable network spend.",
        category=Category.NETWORK,
        severity=Severity.HIGH,
    ),
    "APP_GATEWAY_IDLE_EXTENDED": AdvancedRule(
        id="APP_GATEWAY_IDLE_EXTENDED",
        name="Extended Idle Application Gateway Detection",
        description="Application gateways without listeners should be deleted or reconfigured.",
        category=Category.NETWORK,
        severity=Severity.HIGH,
    ),
    "SQL_SERVERLESS_EXTENDED": AdvancedRule(
        id="SQL_SERVERLESS_EXTENDED",
        name="SQL Serverless Candidate",
        description="Low-utilization SQL databases should move to serverless when supported.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
    ),
    "COSMOS_AUTOSCALE_EXTENDED": AdvancedRule(
        id="COSMOS_AUTOSCALE_EXTENDED",
        name="Cosmos Autoscale Candidate",
        description="Low steady utilization suggests autoscale or serverless is cheaper than provisioned throughput.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
    ),
    "STORAGE_LIFECYCLE_EXTENDED": AdvancedRule(
        id="STORAGE_LIFECYCLE_EXTENDED",
        name="Storage Lifecycle Candidate",
        description="Storage accounts without lifecycle management should be reviewed for tiering and archival.",
        category=Category.STORAGE,
        severity=Severity.MEDIUM,
    ),
    "KEYVAULT_PROTECTION_EXTENDED": AdvancedRule(
        id="KEYVAULT_PROTECTION_EXTENDED",
        name="Key Vault Protection Baseline",
        description="Key Vault should have soft delete and purge protection enabled for recoverability.",
        category=Category.SECURITY,
        severity=Severity.HIGH,
    ),
    "KEYVAULT_IDLE_EXTENDED": AdvancedRule(
        id="KEYVAULT_IDLE_EXTENDED",
        name="Idle Key Vault",
        description="Vaults with negligible API activity may be unused and safe to consolidate or delete.",
        category=Category.SECURITY,
        severity=Severity.LOW,
        kv_api_hits_idle=10.0,
        min_monthly_savings_usd=1.0,
    ),
    "KEYVAULT_PREMIUM_EXTENDED": AdvancedRule(
        id="KEYVAULT_PREMIUM_EXTENDED",
        name="Key Vault Premium SKU Review",
        description="Premium SKU may be unnecessary when vaults store secrets only and have no HSM-backed keys.",
        category=Category.SECURITY,
        severity=Severity.MEDIUM,
        kv_api_hits_idle=10.0,
        min_monthly_savings_usd=5.0,
    ),
    "KEYVAULT_HIGH_OPS_EXTENDED": AdvancedRule(
        id="KEYVAULT_HIGH_OPS_EXTENDED",
        name="Key Vault High API Volume",
        description="High API hit volume increases per-operation charges — cache secrets and reduce polling.",
        category=Category.COST,
        severity=Severity.MEDIUM,
        kv_api_hits_high=50_000.0,
        min_monthly_savings_usd=5.0,
    ),
    "BUDGET_GUARDRAIL_EXTENDED": AdvancedRule(
        id="BUDGET_GUARDRAIL_EXTENDED",
        name="Budget Guardrail Breach Risk",
        description="Budget current or forecast spend is approaching the configured limit.",
        category=Category.COST,
        severity=Severity.CRITICAL,
    ),
    "APP_SERVICE_PLAN_EXTENDED": AdvancedRule(
        id="APP_SERVICE_PLAN_EXTENDED",
        name="Extended App Service Plan Waste",
        description="Empty or over-provisioned App Service Plans create recurring platform cost.",
        category=Category.COMPUTE,
        severity=Severity.HIGH,
    ),
    "NIC_ORPHANED_EXTENDED": AdvancedRule(
        id="NIC_ORPHANED_EXTENDED",
        name="Orphaned Network Interface",
        description="NICs detached from VMs still incur minor management overhead and clutter inventory.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
    ),
    "NAT_GATEWAY_IDLE_EXTENDED": AdvancedRule(
        id="NAT_GATEWAY_IDLE_EXTENDED",
        name="Extended Idle NAT Gateway",
        description="NAT Gateway without subnet associations is pure idle spend.",
        category=Category.NETWORK,
        severity=Severity.HIGH,
    ),
    "REDIS_HEALTH_EXTENDED": AdvancedRule(
        id="REDIS_HEALTH_EXTENDED",
        name="Redis Health and Recovery",
        description="Failed Redis caches should be remediated immediately.",
        category=Category.DATABASE,
        severity=Severity.CRITICAL,
    ),
    "REDIS_RIGHTSIZE_EXTENDED": AdvancedRule(
        id="REDIS_RIGHTSIZE_EXTENDED",
        name="Redis Right-Sizing Candidate",
        description="Premium or high-capacity Redis SKUs should be validated against actual memory pressure.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
    ),
    "NSG_ORPHANED_EXTENDED": AdvancedRule(
        id="NSG_ORPHANED_EXTENDED",
        name="Orphaned Network Security Group",
        description="NSG is not associated with any subnet or network interface and should be removed.",
        category=Category.NETWORK,
        severity=Severity.LOW,
    ),
    "NSG_PERMISSIVE_EXTENDED": AdvancedRule(
        id="NSG_PERMISSIVE_EXTENDED",
        name="Overly Permissive NSG Rules",
        description="NSG allows broad inbound access from the internet on sensitive ports.",
        category=Category.SECURITY,
        severity=Severity.HIGH,
    ),
    "POSTGRESQL_STOPPED_EXTENDED": AdvancedRule(
        id="POSTGRESQL_STOPPED_EXTENDED",
        name="Stopped PostgreSQL Server",
        description="PostgreSQL flexible server is stopped but may still incur storage and backup charges.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
    ),
    "POSTGRESQL_BURSTABLE_EXTENDED": AdvancedRule(
        id="POSTGRESQL_BURSTABLE_EXTENDED",
        name="PostgreSQL Burstable Candidate",
        description="Non-production PostgreSQL workloads on General Purpose tiers should use Burstable SKUs.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
    ),
    "POSTGRESQL_STORAGE_EXTENDED": AdvancedRule(
        id="POSTGRESQL_STORAGE_EXTENDED",
        name="PostgreSQL Storage Right-Sizing",
        description="PostgreSQL storage is provisioned well above typical usage and should be reviewed.",
        category=Category.DATABASE,
        severity=Severity.LOW,
    ),
    "ACR_PREMIUM_EXTENDED": AdvancedRule(
        id="ACR_PREMIUM_EXTENDED",
        name="ACR Premium SKU Review",
        description="Premium container registry SKU may be unnecessary for dev/test or low-throughput workloads.",
        category=Category.COMPUTE,
        severity=Severity.MEDIUM,
        acr_pull_count_low=500.0,
        acr_storage_high_gb=50.0,
        acr_push_count_low=100.0,
        min_monthly_savings_usd=5.0,
    ),
    "ACR_STANDARD_EXTENDED": AdvancedRule(
        id="ACR_STANDARD_EXTENDED",
        name="ACR Standard SKU Review",
        description="Standard SKU registries with low pull volume and storage may downgrade to Basic.",
        category=Category.COMPUTE,
        severity=Severity.LOW,
        acr_pull_count_low=500.0,
        acr_storage_high_gb=50.0,
        min_monthly_savings_usd=5.0,
    ),
    "ACR_GEO_REPLICATION_EXTENDED": AdvancedRule(
        id="ACR_GEO_REPLICATION_EXTENDED",
        name="ACR Geo-Replication Cost",
        description="Geo-replicated registries multiply storage and transfer cost — validate business need.",
        category=Category.STORAGE,
        severity=Severity.MEDIUM,
        min_monthly_savings_usd=5.0,
    ),
    "ACR_STORAGE_HIGH_EXTENDED": AdvancedRule(
        id="ACR_STORAGE_HIGH_EXTENDED",
        name="ACR High Storage Usage",
        description="Registries with high storage and low activity should review image cleanup policies.",
        category=Category.STORAGE,
        severity=Severity.LOW,
        acr_storage_high_gb=50.0,
        acr_pull_count_low=500.0,
        acr_push_count_low=100.0,
        min_monthly_savings_usd=5.0,
    ),
    "ACR_RETENTION_DISABLED_EXTENDED": AdvancedRule(
        id="ACR_RETENTION_DISABLED_EXTENDED",
        name="ACR Retention Policy Disabled",
        description="Premium registries with high storage should enable untagged manifest retention.",
        category=Category.GOVERNANCE,
        severity=Severity.LOW,
        acr_storage_high_gb=50.0,
        min_monthly_savings_usd=0.0,
    ),
    "WEBAPP_STOPPED_EXTENDED": AdvancedRule(
        id="WEBAPP_STOPPED_EXTENDED",
        name="Stopped Web App on Paid Plan",
        description="Stopped web apps still consume App Service Plan capacity — consolidate or delete.",
        category=Category.COMPUTE,
        severity=Severity.MEDIUM,
    ),
    "WEBAPP_ALWAYS_ON_EXTENDED": AdvancedRule(
        id="WEBAPP_ALWAYS_ON_EXTENDED",
        name="Production Web App Without Always On",
        description="Production web apps should enable Always On to avoid cold-start waste and failed health checks.",
        category=Category.RELIABILITY,
        severity=Severity.MEDIUM,
    ),
    "STORAGE_REDUNDANCY_EXTENDED": AdvancedRule(
        id="STORAGE_REDUNDANCY_EXTENDED",
        name="Storage Geo-Redundancy Review",
        description="GRS/GZRS storage accounts cost more than LRS — validate redundancy requirements per workload.",
        category=Category.STORAGE,
        severity=Severity.MEDIUM,
    ),
    "AKS_OLD_VERSION_EXTENDED": AdvancedRule(
        id="AKS_OLD_VERSION_EXTENDED",
        name="AKS Unsupported Kubernetes Version",
        description="Cluster runs a Kubernetes version outside the supported set and should be upgraded.",
        category=Category.KUBERNETES,
        severity=Severity.MEDIUM,
    ),
    "AKS_NO_AUTOSCALER_EXTENDED": AdvancedRule(
        id="AKS_NO_AUTOSCALER_EXTENDED",
        name="AKS Node Pool Without Autoscaler",
        description="Node pool has fixed node count without cluster autoscaler enabled.",
        category=Category.KUBERNETES,
        severity=Severity.HIGH,
    ),
    "AKS_NO_SPOT_EXTENDED": AdvancedRule(
        id="AKS_NO_SPOT_EXTENDED",
        name="AKS User Pool Not Using Spot",
        description="User node pool uses on-demand VMs where Spot nodes could reduce cost.",
        category=Category.KUBERNETES,
        severity=Severity.MEDIUM,
    ),
    "AKS_SINGLE_NODE_POOL_EXTENDED": AdvancedRule(
        id="AKS_SINGLE_NODE_POOL_EXTENDED",
        name="AKS Single Node Pool",
        description="Cluster has only one node pool — workloads share system and user nodes.",
        category=Category.KUBERNETES,
        severity=Severity.LOW,
    ),
    "DISK_OVERSIZE_EXTENDED": AdvancedRule(
        id="DISK_OVERSIZE_EXTENDED",
        name="Oversized Premium Disk",
        description="Premium SSD disk shows near-zero I/O and may be downgraded to Standard SSD.",
        category=Category.COMPUTE,
        severity=Severity.LOW,
        disk_io_idle_bps=1024.0,
        disk_iops_block_downgrade_pct=20.0,
    ),
    "DISK_UNDERPROVISIONED": AdvancedRule(
        id="DISK_UNDERPROVISIONED",
        name="Under-Provisioned Managed Disk",
        description="Premium or Ultra disk IOPS or throughput is near the provisioned cap — increase size or tier before cost cuts.",
        category=Category.RELIABILITY,
        severity=Severity.MEDIUM,
        disk_iops_high_util_pct=80.0,
    ),
    "SQL_IDLE_EXTENDED": AdvancedRule(
        id="SQL_IDLE_EXTENDED",
        name="Idle SQL Database",
        description="SQL database shows sustained low CPU utilization on provisioned tier.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        sql_serverless_candidate_cpu_pct=5.0,
    ),
    "COSMOS_PROVISIONED_EXTENDED": AdvancedRule(
        id="COSMOS_PROVISIONED_EXTENDED",
        name="Cosmos DB Not Serverless",
        description="Cosmos account uses provisioned throughput without serverless capability enabled.",
        category=Category.DATABASE,
        severity=Severity.LOW,
    ),
    "STORAGE_HOT_UNUSED_EXTENDED": AdvancedRule(
        id="STORAGE_HOT_UNUSED_EXTENDED",
        name="Storage Hot Tier Review",
        description="Storage account on Hot tier should be validated for active access patterns.",
        category=Category.STORAGE,
        severity=Severity.LOW,
    ),
    "STORAGE_LRS_CRITICAL_EXTENDED": AdvancedRule(
        id="STORAGE_LRS_CRITICAL_EXTENDED",
        name="Storage LRS Resilience Tradeoff",
        description="Locally redundant storage may not meet geo-resilience requirements for critical data.",
        category=Category.STORAGE,
        severity=Severity.INFO,
    ),
    "BUDGET_WARNING_EXTENDED": AdvancedRule(
        id="BUDGET_WARNING_EXTENDED",
        name="Budget Warning Threshold",
        description="Budget current or forecast spend is approaching the configured warning limit.",
        category=Category.COST,
        severity=Severity.MEDIUM,
        budget_warn_pct=80.0,
    ),
    "BUDGET_CRITICAL_EXTENDED": AdvancedRule(
        id="BUDGET_CRITICAL_EXTENDED",
        name="Budget Critical Threshold",
        description="Budget current or forecast spend is at or above the critical limit.",
        category=Category.COST,
        severity=Severity.CRITICAL,
        budget_crit_pct=95.0,
    ),
    "VMSS_NO_AUTOSCALE_EXTENDED": AdvancedRule(
        id="VMSS_NO_AUTOSCALE_EXTENDED",
        name="VMSS Without Autoscale",
        description="Scale set has fixed instance count or autoscale profile with min equals max.",
        category=Category.COMPUTE,
        severity=Severity.MEDIUM,
    ),
    "VMSS_NONPROD_SCHEDULING_EXTENDED": AdvancedRule(
        id="VMSS_NONPROD_SCHEDULING_EXTENDED",
        name="VMSS Non-Prod Scheduling",
        description="Non-production scale set should use shutdown schedules or scale-to-zero.",
        category=Category.COMPUTE,
        severity=Severity.MEDIUM,
    ),
    "RESERVED_OPPORTUNITY_EXTENDED": AdvancedRule(
        id="RESERVED_OPPORTUNITY_EXTENDED",
        name="Reserved Instance Opportunity",
        description="Subscription has sustained on-demand VM spend suitable for Reserved Instances.",
        category=Category.COST,
        severity=Severity.MEDIUM,
        reserved_savings_threshold=0.30,
        min_monthly_savings_usd=100.0,
    ),
    "SAVINGS_PLAN_OPPORTUNITY_EXTENDED": AdvancedRule(
        id="SAVINGS_PLAN_OPPORTUNITY_EXTENDED",
        name="Savings Plan Opportunity",
        description="Subscription compute spend is eligible for Azure Savings Plans.",
        category=Category.COST,
        severity=Severity.MEDIUM,
        savings_plan_min_monthly_usd=500.0,
    ),
    # Phase 3 — Monitoring
    "LOG_ANALYTICS_RETENTION_EXTENDED": AdvancedRule(
        id="LOG_ANALYTICS_RETENTION_EXTENDED",
        name="Log Analytics Retention Review",
        description="Workspace retention or ingestion volume suggests cost optimization opportunity.",
        category=Category.COST,
        severity=Severity.HIGH,
    ),
    "APP_INSIGHTS_SAMPLING_EXTENDED": AdvancedRule(
        id="APP_INSIGHTS_SAMPLING_EXTENDED",
        name="Application Insights Sampling Review",
        description="Application Insights component lacks adaptive sampling with significant ingestion cost.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    # Phase 3 — Integration
    "APIM_SKU_EXTENDED": AdvancedRule(
        id="APIM_SKU_EXTENDED",
        name="API Management SKU Review",
        description="API Management tier or capacity units may be over-provisioned for workload.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "DATA_FACTORY_IR_EXTENDED": AdvancedRule(
        id="DATA_FACTORY_IR_EXTENDED",
        name="Data Factory Integration Runtime Review",
        description="Self-hosted or over-provisioned integration runtimes increase pipeline cost.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "LOGIC_APP_PLAN_EXTENDED": AdvancedRule(
        id="LOGIC_APP_PLAN_EXTENDED",
        name="Logic App Plan Review",
        description="Logic App uses Standard plan for low-volume intermittent workloads.",
        category=Category.COST,
        severity=Severity.LOW,
    ),
    # Phase 3 — Messaging
    "EVENT_HUBS_TIER_EXTENDED": AdvancedRule(
        id="EVENT_HUBS_TIER_EXTENDED",
        name="Event Hubs Tier Review",
        description="Event Hubs namespace tier or throughput units exceed actual usage.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "SERVICE_BUS_TIER_EXTENDED": AdvancedRule(
        id="SERVICE_BUS_TIER_EXTENDED",
        name="Service Bus Tier Review",
        description="Service Bus namespace uses Premium tier where Standard may suffice.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    # Phase 3 — Analytics
    "DATABRICKS_CLUSTER_EXTENDED": AdvancedRule(
        id="DATABRICKS_CLUSTER_EXTENDED",
        name="Databricks Cluster Review",
        description="Databricks workspace lacks auto-termination or uses all-purpose clusters inefficiently.",
        category=Category.COST,
        severity=Severity.HIGH,
    ),
    "SYNAPSE_PAUSE_EXTENDED": AdvancedRule(
        id="SYNAPSE_PAUSE_EXTENDED",
        name="Synapse Pause and Scale Review",
        description="Synapse dedicated SQL pool runs continuously without pause schedule.",
        category=Category.COST,
        severity=Severity.HIGH,
    ),
    "ADX_INGESTION_EXTENDED": AdvancedRule(
        id="ADX_INGESTION_EXTENDED",
        name="Azure Data Explorer Ingestion Review",
        description="ADX cluster ingestion or retention policies may be over-provisioned.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "ML_WORKSPACE_COMPUTE_EXTENDED": AdvancedRule(
        id="ML_WORKSPACE_COMPUTE_EXTENDED",
        name="ML Workspace Compute Review",
        description="ML workspace has idle compute clusters or over-provisioned endpoints.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    # Phase 3 — Backup & Search
    "BACKUP_RETENTION_EXTENDED": AdvancedRule(
        id="BACKUP_RETENTION_EXTENDED",
        name="Backup Vault Retention Review",
        description="Recovery Services vault retention or protected item count suggests storage growth.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "COGNITIVE_SEARCH_SKU_EXTENDED": AdvancedRule(
        id="COGNITIVE_SEARCH_SKU_EXTENDED",
        name="AI Search SKU Review",
        description="Search service replicas or partitions exceed query volume requirements.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "FIREWALL_FIXED_COST_EXTENDED": AdvancedRule(
        id="FIREWALL_FIXED_COST_EXTENDED",
        name="Azure Firewall Fixed Cost Review",
        description="Dedicated firewall SKU incurs significant fixed monthly cost.",
        category=Category.COST,
        severity=Severity.MEDIUM,
        min_monthly_savings_usd=200.0,
    ),
    "CDN_EGRESS_EXTENDED": AdvancedRule(
        id="CDN_EGRESS_EXTENDED",
        name="CDN / Front Door Egress Review",
        description="CDN or Front Door profile has significant egress-related spend.",
        category=Category.COST,
        severity=Severity.MEDIUM,
        min_monthly_savings_usd=80.0,
    ),
    "AKS_UNDERUTILIZED": AdvancedRule(
        id="AKS_UNDERUTILIZED",
        name="AKS Cluster Underutilized",
        description="Cluster node CPU and memory are consistently low — scale down node pools or enable cluster autoscaler.",
        category=Category.KUBERNETES,
        severity=Severity.HIGH,
        node_cpu_idle_pct=15.0,
        node_memory_idle_pct=20.0,
    ),
    "COSMOS_SERVERLESS": AdvancedRule(
        id="COSMOS_SERVERLESS",
        name="Cosmos DB Serverless Candidate",
        description="Low steady RU consumption supports serverless or autoscale instead of fixed provisioned throughput.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        cosmos_autoscale_candidate_utilization_pct=25.0,
    ),
    "REDIS_TIER_REVIEW": AdvancedRule(
        id="REDIS_TIER_REVIEW",
        name="Redis Tier and Shard Review",
        description="Premium or high shard count may exceed workload needs — validate SKU and eviction policy.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        redis_premium_min_capacity=1,
    ),
    "APP_ALWAYS_ON_OFF": AdvancedRule(
        id="APP_ALWAYS_ON_OFF",
        name="Production Web App Without Always On",
        description="Production web apps should enable Always On to avoid cold starts and failed health probes.",
        category=Category.RELIABILITY,
        severity=Severity.MEDIUM,
    ),
    "PRIVATE_ENDPOINT_FAILED_EXTENDED": AdvancedRule(
        id="PRIVATE_ENDPOINT_FAILED_EXTENDED",
        name="Private Endpoint Connection Failed",
        description="Private endpoint connection is rejected or failed — fix or delete to stop hourly charges.",
        category=Category.NETWORK,
        severity=Severity.HIGH,
    ),
    "PRIVATE_ENDPOINT_ORPHAN_EXTENDED": AdvancedRule(
        id="PRIVATE_ENDPOINT_ORPHAN_EXTENDED",
        name="Orphaned Private Endpoint",
        description="Private endpoint has no approved connection or target resource — review for deletion.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
        min_monthly_savings_usd=5.0,
    ),
    "PRIVATE_LINK_UNUSED_EXTENDED": AdvancedRule(
        id="PRIVATE_LINK_UNUSED_EXTENDED",
        name="Unused Private Link Service",
        description="Private link service has no private endpoint connections.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
        min_monthly_savings_usd=5.0,
    ),
    "PRIVATE_DNS_EMPTY_EXTENDED": AdvancedRule(
        id="PRIVATE_DNS_EMPTY_EXTENDED",
        name="Empty Private DNS Zone",
        description="Private DNS zone has no record sets beyond SOA/NS — delete if unused.",
        category=Category.NETWORK,
        severity=Severity.LOW,
        private_dns_max_default_record_sets=2,
    ),
    "VNET_PEERING_REVIEW_EXTENDED": AdvancedRule(
        id="VNET_PEERING_REVIEW_EXTENDED",
        name="Virtual Network Peering Review",
        description="VNet peering and cross-region data transfer can drive recurring network spend.",
        category=Category.NETWORK,
        severity=Severity.LOW,
        min_monthly_savings_usd=10.0,
    ),
    "VM_DISK_BOTTLENECK": AdvancedRule(
        id="VM_DISK_BOTTLENECK",
        name="VM Blocked by Disk I/O",
        description="VM shows low CPU but attached disk IOPS are saturated — do not downsize the VM first.",
        category=Category.COMPUTE,
        severity=Severity.HIGH,
    ),
    "VM_NETWORK_BOTTLENECK": AdvancedRule(
        id="VM_NETWORK_BOTTLENECK",
        name="VM Blocked by Network Throughput",
        description="VM network interface shows saturation — validate throughput before rightsizing compute.",
        category=Category.NETWORK,
        severity=Severity.HIGH,
    ),
    "VM_SCHEDULE_CANDIDATE_EXTENDED": AdvancedRule(
        id="VM_SCHEDULE_CANDIDATE_EXTENDED",
        name="VM Schedule Optimization Candidate",
        description="VM is frequently stopped or deallocated — automate shutdown or delete if unused.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "VM_ZOMBIE_CANDIDATE_EXTENDED": AdvancedRule(
        id="VM_ZOMBIE_CANDIDATE_EXTENDED",
        name="Zombie VM Candidate",
        description="VM runs continuously with near-zero CPU — strong delete or decommission candidate.",
        category=Category.COST,
        severity=Severity.HIGH,
    ),
    "AKS_POOL_CONSOLIDATION": AdvancedRule(
        id="AKS_POOL_CONSOLIDATION",
        name="AKS Node Pool Consolidation",
        description="Node pool can run on fewer nodes based on aggregate CPU and memory headroom.",
        category=Category.KUBERNETES,
        severity=Severity.MEDIUM,
    ),
    "COST_SPIKE_DETECTED": AdvancedRule(
        id="COST_SPIKE_DETECTED",
        name="Cost Spike Detected",
        description="Service daily spend increased significantly versus the prior-week baseline.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
}

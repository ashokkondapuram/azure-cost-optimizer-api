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
    cosmos_ru_low_pct: float = 20.0
    cosmos_ru_high_pct: float = 80.0
    cosmos_throttle_ru_pct: float = 95.0
    cosmos_serverless_ru_threshold: float = 50000.0
    cosmos_index_to_data_ratio: float = 1.5
    cosmos_large_item_bytes: float = 2097152.0
    cosmos_hot_partition_skew_ratio: float = 2.5
    cosmos_replication_lag_ms: float = 100.0
    vm_uptime_hours_candidate: int = 500
    redis_premium_min_capacity: int = 1
    redis_memory_pressure_pct: float = 85.0
    redis_low_utilization_pct: float = 30.0
    redis_server_load_low_pct: float = 20.0
    redis_hit_ratio_poor_pct: float = 50.0
    redis_cluster_ops_threshold: float = 50_000.0
    redis_idle_ops_threshold: float = 0.0
    postgresql_cpu_high_pct: float = 80.0
    postgresql_cpu_low_pct: float = 25.0
    postgresql_memory_pressure_pct: float = 85.0
    postgresql_memory_low_pct: float = 40.0
    postgresql_storage_high_pct: float = 80.0
    postgresql_storage_low_pct: float = 40.0
    postgresql_iops_pressure_pct: float = 80.0
    postgresql_connection_risk_absolute: float = 3500.0
    postgresql_replication_lag_seconds: float = 5.0
    postgresql_backup_retention_prod_days: float = 14.0
    postgresql_backup_retention_dev_days: float = 7.0
    asp_min_apps_for_premium: int = 2
    node_count_min: int = 1
    db_dtu_idle_pct: float = 5.0
    budget_warn_pct: float = 80.0
    budget_crit_pct: float = 95.0
    reserved_savings_threshold: float = 0.30
    savings_plan_min_monthly_usd: float = 500.0
    cluster_dev_hours: str = "08:00-18:00"
    private_dns_max_default_record_sets: int = 2
    public_ip_idle_byte_threshold: float = 100.0
    public_ip_idle_packet_threshold: float = 100.0
    nat_snat_exhaustion_pct: float = 80.0
    nat_snat_low_connection_threshold: float = 10.0
    nat_throughput_v2_upgrade_gbps: float = 40.0
    nat_idle_byte_threshold: float = 1_000_000.0
    lb_snat_pressure_pct: float = 70.0
    lb_throughput_low_pct_of_peak: float = 10.0
    lb_idle_byte_threshold: float = 1_000_000.0
    memory_pressure_pct: float = 90.0
    network_egress_bytes_monthly: float = 10_995_116_277_760.0
    vmss_scale_out_cpu_pct: float = 70.0
    vmss_scale_in_cpu_pct: float = 30.0
    disk_capacity_used_pct_max: float = 30.0
    disk_queue_depth_contention: float = 10.0
    snapshot_archive_days: float = 180.0
    snapshot_delete_days: float = 365.0
    node_memory_pressure_pct: float = 85.0
    pod_density_low_threshold: float = 3.0
    node_cpu_downsize_pct: float = 20.0
    acr_image_retention_days: float = 90.0
    plan_load_low_pct: float = 20.0
    asp_consolidation_app_max: float = 5.0
    storage_egress_bytes_monthly: float = 107_374_182_400.0
    storage_transaction_low: float = 5000.0
    app_gateway_cu_saturation_pct: float = 80.0
    app_gateway_cu_downsize_pct: float = 30.0
    pe_underutilized_bytes_monthly: float = 107_374_182_400.0
    pls_nat_port_pressure_pct: float = 80.0
    pls_nat_port_low_pct: float = 30.0
    nsg_flow_log_min_gb: float = 1.0


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
        public_ip_idle_byte_threshold=100.0,
        public_ip_idle_packet_threshold=100.0,
        min_monthly_savings_usd=2.0,
    ),
    "PUBLIC_IP_BASIC_SKU_MIGRATION": AdvancedRule(
        id="PUBLIC_IP_BASIC_SKU_MIGRATION",
        name="Public IP Basic SKU Migration",
        description="Basic SKU public IPs must migrate to Standard before the Azure retirement deadline.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
        min_monthly_savings_usd=0.0,
    ),
    "LOAD_BALANCER_IDLE_EXTENDED": AdvancedRule(
        id="LOAD_BALANCER_IDLE_EXTENDED",
        name="Extended Idle Load Balancer Detection",
        description="Load balancers without backend instances create avoidable network spend.",
        category=Category.NETWORK,
        severity=Severity.HIGH,
        lb_idle_byte_threshold=1_000_000.0,
    ),
    "LOAD_BALANCER_SNAT_PRESSURE": AdvancedRule(
        id="LOAD_BALANCER_SNAT_PRESSURE",
        name="Load Balancer SNAT Port Pressure",
        description="High SNAT port utilization risks outbound connection failures.",
        category=Category.NETWORK,
        severity=Severity.HIGH,
        lb_snat_pressure_pct=70.0,
        min_monthly_savings_usd=0.0,
    ),
    "LOAD_BALANCER_THROUGHPUT_RIGHTSIZE": AdvancedRule(
        id="LOAD_BALANCER_THROUGHPUT_RIGHTSIZE",
        name="Load Balancer Throughput Right-Size",
        description="Sustained throughput far below peak suggests over-provisioned data processing.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
        lb_throughput_low_pct_of_peak=10.0,
    ),
    "LOAD_BALANCER_BACKEND_CONSOLIDATION": AdvancedRule(
        id="LOAD_BALANCER_BACKEND_CONSOLIDATION",
        name="Load Balancer Backend Consolidation",
        description="Backends configured but very low traffic — consolidate or remove.",
        category=Category.NETWORK,
        severity=Severity.LOW,
        lb_idle_byte_threshold=1_000_000.0,
    ),
    "LOAD_BALANCER_BASIC_SKU_MIGRATION": AdvancedRule(
        id="LOAD_BALANCER_BASIC_SKU_MIGRATION",
        name="Load Balancer Basic SKU Migration",
        description="Basic SKU load balancers must migrate to Standard before retirement.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
        min_monthly_savings_usd=0.0,
    ),
    "APP_GATEWAY_IDLE_EXTENDED": AdvancedRule(
        id="APP_GATEWAY_IDLE_EXTENDED",
        name="Extended Idle Application Gateway Detection",
        description="Application gateways without listeners should be deleted or reconfigured.",
        category=Category.NETWORK,
        severity=Severity.HIGH,
        min_monthly_savings_usd=25.0,
    ),
    "APP_GATEWAY_CU_SATURATION": AdvancedRule(
        id="APP_GATEWAY_CU_SATURATION",
        name="Application Gateway CU Saturation",
        description="Billed capacity units exceed safe utilization — performance risk.",
        category=Category.NETWORK,
        severity=Severity.HIGH,
        app_gateway_cu_saturation_pct=80.0,
        min_monthly_savings_usd=0.0,
    ),
    "APP_GATEWAY_CU_RIGHTSIZE_DOWN": AdvancedRule(
        id="APP_GATEWAY_CU_RIGHTSIZE_DOWN",
        name="Application Gateway CU Right-Size Down",
        description="Sustained low billed CU supports capacity reduction.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
        app_gateway_cu_downsize_pct=30.0,
        min_monthly_savings_usd=25.0,
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
        cosmos_autoscale_candidate_utilization_pct=25.0,
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
        nat_idle_byte_threshold=1_000_000.0,
        nat_snat_low_connection_threshold=10.0,
    ),
    "NAT_GATEWAY_SNAT_EXHAUSTION": AdvancedRule(
        id="NAT_GATEWAY_SNAT_EXHAUSTION",
        name="NAT Gateway SNAT Exhaustion Risk",
        description="SNAT connection utilization exceeds safe threshold — add IPs or consolidate.",
        category=Category.NETWORK,
        severity=Severity.CRITICAL,
        nat_snat_exhaustion_pct=80.0,
        min_monthly_savings_usd=0.0,
    ),
    "NAT_GATEWAY_SKU_V2_UPGRADE": AdvancedRule(
        id="NAT_GATEWAY_SKU_V2_UPGRADE",
        name="NAT Gateway StandardV2 Candidate",
        description="Sustained throughput may require StandardV2 for 100 Gbps and zone redundancy.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
        nat_throughput_v2_upgrade_gbps=40.0,
        min_monthly_savings_usd=0.0,
    ),
    "NAT_GATEWAY_SUBNET_CONSOLIDATION": AdvancedRule(
        id="NAT_GATEWAY_SUBNET_CONSOLIDATION",
        name="NAT Gateway Subnet Consolidation",
        description="Multiple public IPs with low traffic — consolidate subnets or reduce IP count.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
        nat_idle_byte_threshold=1_000_000.0,
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
    "REDIS_IDLE_DETECTION": AdvancedRule(
        id="REDIS_IDLE_DETECTION",
        name="Idle Redis Cache",
        description="Redis caches with zero operations per second over the evaluation window are decommission candidates.",
        category=Category.DATABASE,
        severity=Severity.HIGH,
        redis_idle_ops_threshold=0.0,
    ),
    "REDIS_MEMORY_PRESSURE": AdvancedRule(
        id="REDIS_MEMORY_PRESSURE",
        name="Redis Memory Pressure",
        description="High memory utilization or evictions indicate upgrade or policy tuning is needed.",
        category=Category.DATABASE,
        severity=Severity.HIGH,
        redis_memory_pressure_pct=85.0,
    ),
    "REDIS_LOW_UTILIZATION": AdvancedRule(
        id="REDIS_LOW_UTILIZATION",
        name="Redis Low Utilization",
        description="Sustained low memory and server load support tier or capacity downgrade.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        redis_low_utilization_pct=30.0,
        redis_server_load_low_pct=20.0,
    ),
    "REDIS_HIT_RATIO_POOR": AdvancedRule(
        id="REDIS_HIT_RATIO_POOR",
        name="Redis Cache Hit Ratio",
        description="Low cache hit ratio may indicate sizing or eviction policy issues.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        redis_hit_ratio_poor_pct=50.0,
    ),
    "REDIS_CLUSTER_UNNECESSARY": AdvancedRule(
        id="REDIS_CLUSTER_UNNECESSARY",
        name="Redis Cluster Review",
        description="Single-shard Premium caches with low throughput may not need clustering.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        redis_cluster_ops_threshold=50_000.0,
    ),
    "REDIS_PERSISTENCE_REVIEW": AdvancedRule(
        id="REDIS_PERSISTENCE_REVIEW",
        name="Redis Persistence Review",
        description="Premium/Enterprise persistence (RDB/AOF) adds storage cost — validate durability requirements.",
        category=Category.DATABASE,
        severity=Severity.LOW,
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
    "POSTGRESQL_LOW_COMPUTE_UTILIZATION": AdvancedRule(
        id="POSTGRESQL_LOW_COMPUTE_UTILIZATION",
        name="PostgreSQL Low Compute Utilization",
        description="Sustained low CPU and memory support a smaller vCore SKU.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        postgresql_cpu_low_pct=25.0,
        postgresql_memory_low_pct=40.0,
        evaluation_window_days=30,
    ),
    "POSTGRESQL_HIGH_COMPUTE_DEMAND": AdvancedRule(
        id="POSTGRESQL_HIGH_COMPUTE_DEMAND",
        name="PostgreSQL High CPU Utilization",
        description="Sustained high CPU utilization indicates a compute upgrade is needed.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        postgresql_cpu_high_pct=80.0,
    ),
    "POSTGRESQL_MEMORY_PRESSURE": AdvancedRule(
        id="POSTGRESQL_MEMORY_PRESSURE",
        name="PostgreSQL Memory Pressure",
        description="High memory utilization risks degraded query performance.",
        category=Category.DATABASE,
        severity=Severity.HIGH,
        postgresql_memory_pressure_pct=85.0,
    ),
    "POSTGRESQL_STORAGE_EXPANSION": AdvancedRule(
        id="POSTGRESQL_STORAGE_EXPANSION",
        name="PostgreSQL Storage Expansion Needed",
        description="Storage utilization is high and capacity should be expanded or data archived.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        postgresql_storage_high_pct=80.0,
    ),
    "POSTGRESQL_IOPS_PRESSURE": AdvancedRule(
        id="POSTGRESQL_IOPS_PRESSURE",
        name="PostgreSQL IOPS Pressure",
        description="Disk IOPS consumption is near provisioned limits.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        postgresql_iops_pressure_pct=80.0,
    ),
    "POSTGRESQL_CONNECTION_POOL_RISK": AdvancedRule(
        id="POSTGRESQL_CONNECTION_POOL_RISK",
        name="PostgreSQL Connection Pool Risk",
        description="High concurrent connections may exhaust limits without pooling.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        postgresql_connection_risk_absolute=3500.0,
    ),
    "POSTGRESQL_HA_UNNECESSARY": AdvancedRule(
        id="POSTGRESQL_HA_UNNECESSARY",
        name="PostgreSQL HA Unnecessary",
        description="High availability on non-production PostgreSQL servers adds cost without benefit.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
    ),
    "POSTGRESQL_HA_REQUIRED": AdvancedRule(
        id="POSTGRESQL_HA_REQUIRED",
        name="PostgreSQL HA Required",
        description="Production PostgreSQL servers should enable high availability for failover.",
        category=Category.DATABASE,
        severity=Severity.HIGH,
    ),
    "POSTGRESQL_READ_REPLICA_ANALYSIS": AdvancedRule(
        id="POSTGRESQL_READ_REPLICA_ANALYSIS",
        name="PostgreSQL Read Replica Review",
        description="Read replicas incur full instance cost and should be justified by workload.",
        category=Category.DATABASE,
        severity=Severity.LOW,
        postgresql_replication_lag_seconds=5.0,
    ),
    "POSTGRESQL_VERSION_OUTDATED": AdvancedRule(
        id="POSTGRESQL_VERSION_OUTDATED",
        name="PostgreSQL Version Outdated",
        description="PostgreSQL major version is behind supported releases.",
        category=Category.DATABASE,
        severity=Severity.LOW,
    ),
    "POSTGRESQL_BACKUP_RETENTION_REVIEW": AdvancedRule(
        id="POSTGRESQL_BACKUP_RETENTION_REVIEW",
        name="PostgreSQL Backup Retention Review",
        description="Backup retention exceeds typical dev/prod targets and may increase storage cost.",
        category=Category.DATABASE,
        severity=Severity.LOW,
        postgresql_backup_retention_prod_days=14.0,
        postgresql_backup_retention_dev_days=7.0,
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
    "DISK_CAPACITY_RIGHTSIZE_EXTENDED": AdvancedRule(
        id="DISK_CAPACITY_RIGHTSIZE_EXTENDED",
        name="Managed Disk Capacity Right-Sizing",
        description="Provisioned disk size significantly exceeds measured utilization.",
        category=Category.COMPUTE,
        severity=Severity.LOW,
        disk_capacity_used_pct_max=30.0,
        min_monthly_savings_usd=3.0,
    ),
    "DISK_QUEUE_DEPTH_EXTENDED": AdvancedRule(
        id="DISK_QUEUE_DEPTH_EXTENDED",
        name="Managed Disk Queue Depth Contention",
        description="Disk queue depth indicates I/O contention — review before tier downgrade.",
        category=Category.RELIABILITY,
        severity=Severity.HIGH,
        disk_queue_depth_contention=10.0,
    ),
    "SNAPSHOT_ARCHIVE_EXTENDED": AdvancedRule(
        id="SNAPSHOT_ARCHIVE_EXTENDED",
        name="Snapshot Archive Candidate",
        description="Long-retained disk snapshot should be archived or deleted after policy review.",
        category=Category.COMPUTE,
        severity=Severity.MEDIUM,
        snapshot_archive_days=180.0,
        snapshot_delete_days=365.0,
        snapshot_min_size_gb=10.0,
        min_monthly_savings_usd=2.0,
    ),
    "AKS_NODE_MEMORY_PRESSURE_EXTENDED": AdvancedRule(
        id="AKS_NODE_MEMORY_PRESSURE_EXTENDED",
        name="AKS Node Memory Pressure",
        description="AKS cluster nodes show sustained memory pressure.",
        category=Category.KUBERNETES,
        severity=Severity.HIGH,
        node_memory_pressure_pct=85.0,
    ),
    "AKS_POD_DENSITY_EXTENDED": AdvancedRule(
        id="AKS_POD_DENSITY_EXTENDED",
        name="AKS Pod Density Review",
        description="Low pod density on underutilized nodes suggests consolidation opportunity.",
        category=Category.KUBERNETES,
        severity=Severity.MEDIUM,
        pod_density_low_threshold=3.0,
        node_cpu_downsize_pct=20.0,
        min_monthly_savings_usd=15.0,
    ),
    "ACR_IMAGE_RETENTION_EXTENDED": AdvancedRule(
        id="ACR_IMAGE_RETENTION_EXTENDED",
        name="ACR Image Retention Review",
        description="Container registry storage exceeds threshold — enable retention or purge policies.",
        category=Category.COMPUTE,
        severity=Severity.LOW,
        acr_image_retention_days=90.0,
        acr_storage_high_gb=50.0,
        min_monthly_savings_usd=5.0,
    ),
    "WEBAPP_PLAN_LOAD_LOW_EXTENDED": AdvancedRule(
        id="WEBAPP_PLAN_LOAD_LOW_EXTENDED",
        name="App Service Plan Low Load",
        description="App Service Plan CPU utilization is below downsize threshold.",
        category=Category.COMPUTE,
        severity=Severity.MEDIUM,
        plan_load_low_pct=20.0,
        min_monthly_savings_usd=5.0,
    ),
    "ASP_CONSOLIDATION_CANDIDATE_EXTENDED": AdvancedRule(
        id="ASP_CONSOLIDATION_CANDIDATE_EXTENDED",
        name="App Service Plan Consolidation",
        description="App Service Plan hosts few apps — consolidation may reduce platform overhead.",
        category=Category.COMPUTE,
        severity=Severity.MEDIUM,
        asp_consolidation_app_max=5.0,
        min_monthly_savings_usd=10.0,
    ),
    "STORAGE_EGRESS_HIGH_EXTENDED": AdvancedRule(
        id="STORAGE_EGRESS_HIGH_EXTENDED",
        name="Storage Account High Egress",
        description="Storage account egress exceeds bandwidth cost review threshold.",
        category=Category.STORAGE,
        severity=Severity.MEDIUM,
        storage_egress_bytes_monthly=107_374_182_400.0,
        min_monthly_savings_usd=5.0,
    ),
    "STORAGE_COOL_TIER_CANDIDATE_EXTENDED": AdvancedRule(
        id="STORAGE_COOL_TIER_CANDIDATE_EXTENDED",
        name="Storage Cool Tier Candidate",
        description="Hot tier storage account with low transaction volume is a Cool tier migration candidate.",
        category=Category.STORAGE,
        severity=Severity.LOW,
        storage_cool_after_days=30.0,
        storage_transaction_low=5000.0,
        min_monthly_savings_usd=5.0,
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
    "VM_MEMORY_PRESSURE_EXTENDED": AdvancedRule(
        id="VM_MEMORY_PRESSURE_EXTENDED",
        name="VM Memory Pressure",
        description="VM shows sustained memory pressure — block downsize until memory is addressed.",
        category=Category.COMPUTE,
        severity=Severity.HIGH,
        memory_pressure_pct=90.0,
        min_monthly_savings_usd=0.0,
    ),
    "VM_EGRESS_HIGH_EXTENDED": AdvancedRule(
        id="VM_EGRESS_HIGH_EXTENDED",
        name="VM High Network Egress",
        description="VM network egress exceeds cost review threshold.",
        category=Category.COMPUTE,
        severity=Severity.MEDIUM,
        network_egress_bytes_monthly=10_995_116_277_760.0,
        min_monthly_savings_usd=5.0,
    ),
    "VMSS_AUTOSCALE_TUNING_EXTENDED": AdvancedRule(
        id="VMSS_AUTOSCALE_TUNING_EXTENDED",
        name="VMSS Autoscale Tuning",
        description="Scale set autoscale thresholds may be misaligned with observed CPU utilization.",
        category=Category.COMPUTE,
        severity=Severity.MEDIUM,
        vmss_scale_out_cpu_pct=70.0,
        vmss_scale_in_cpu_pct=30.0,
        min_monthly_savings_usd=10.0,
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
    "LOG_ANALYTICS_INGESTION_EXTENDED": AdvancedRule(
        id="LOG_ANALYTICS_INGESTION_EXTENDED",
        name="Log Analytics High Ingestion Review",
        description="Log Analytics workspace ingestion exceeds configured threshold.",
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
    "APP_INSIGHTS_LOW_TRAFFIC_EXTENDED": AdvancedRule(
        id="APP_INSIGHTS_LOW_TRAFFIC_EXTENDED",
        name="Application Insights Low Traffic Review",
        description="Application Insights component has low request volume for its cost.",
        category=Category.COST,
        severity=Severity.LOW,
    ),
    # Phase 3 — Integration
    "APIM_SKU_EXTENDED": AdvancedRule(
        id="APIM_SKU_EXTENDED",
        name="API Management SKU Review",
        description="API Management tier or capacity units may be over-provisioned for workload.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "APIM_LOW_TRAFFIC_EXTENDED": AdvancedRule(
        id="APIM_LOW_TRAFFIC_EXTENDED",
        name="API Management Low Traffic Review",
        description="API Management gateway capacity utilization is below workload needs.",
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
    "DATA_FACTORY_IDLE_PIPELINES_EXTENDED": AdvancedRule(
        id="DATA_FACTORY_IDLE_PIPELINES_EXTENDED",
        name="Data Factory Idle Pipelines Review",
        description="Data Factory has low pipeline execution volume for its cost.",
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
    "LOGIC_APP_LOW_RUNS_EXTENDED": AdvancedRule(
        id="LOGIC_APP_LOW_RUNS_EXTENDED",
        name="Logic App Low Runs Review",
        description="Logic App workflow run volume is below plan cost.",
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
    "EVENT_HUBS_LOW_THROUGHPUT_EXTENDED": AdvancedRule(
        id="EVENT_HUBS_LOW_THROUGHPUT_EXTENDED",
        name="Event Hubs Low Throughput Review",
        description="Event Hubs namespace has minimal message volume for its tier.",
        category=Category.COST,
        severity=Severity.LOW,
    ),
    "SERVICE_BUS_TIER_EXTENDED": AdvancedRule(
        id="SERVICE_BUS_TIER_EXTENDED",
        name="Service Bus Tier Review",
        description="Service Bus namespace uses Premium tier where Standard may suffice.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "SERVICE_BUS_IDLE_NAMESPACE_EXTENDED": AdvancedRule(
        id="SERVICE_BUS_IDLE_NAMESPACE_EXTENDED",
        name="Service Bus Idle Namespace Review",
        description="Service Bus namespace has low active message volume.",
        category=Category.COST,
        severity=Severity.LOW,
    ),
    # Phase 3 — Analytics
    "DATABRICKS_CLUSTER_EXTENDED": AdvancedRule(
        id="DATABRICKS_CLUSTER_EXTENDED",
        name="Databricks Cluster Review",
        description="Databricks workspace lacks auto-termination or uses all-purpose clusters inefficiently.",
        category=Category.COST,
        severity=Severity.HIGH,
    ),
    "DATABRICKS_DEV_WORKSPACE_EXTENDED": AdvancedRule(
        id="DATABRICKS_DEV_WORKSPACE_EXTENDED",
        name="Databricks Dev Workspace Review",
        description="Non-production Databricks workspace has elevated compute spend.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "SYNAPSE_PAUSE_EXTENDED": AdvancedRule(
        id="SYNAPSE_PAUSE_EXTENDED",
        name="Synapse Pause and Scale Review",
        description="Synapse dedicated SQL pool runs continuously without pause schedule.",
        category=Category.COST,
        severity=Severity.HIGH,
    ),
    "SYNAPSE_SQL_IDLE_EXTENDED": AdvancedRule(
        id="SYNAPSE_SQL_IDLE_EXTENDED",
        name="Synapse SQL Pool Idle Review",
        description="Synapse dedicated SQL pool shows low query activity for its cost.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "ADX_INGESTION_EXTENDED": AdvancedRule(
        id="ADX_INGESTION_EXTENDED",
        name="Azure Data Explorer Ingestion Review",
        description="ADX cluster ingestion or retention policies may be over-provisioned.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "ADX_LOW_INGESTION_EXTENDED": AdvancedRule(
        id="ADX_LOW_INGESTION_EXTENDED",
        name="ADX Low Ingestion Review",
        description="ADX cluster ingestion volume is below provisioned capacity.",
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
    "ML_WORKSPACE_IDLE_EXTENDED": AdvancedRule(
        id="ML_WORKSPACE_IDLE_EXTENDED",
        name="ML Workspace Dev Idle Review",
        description="Non-production ML workspace has idle compute spend.",
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
    "BACKUP_VAULT_GROWTH_EXTENDED": AdvancedRule(
        id="BACKUP_VAULT_GROWTH_EXTENDED",
        name="Backup Vault Growth Review",
        description="Recovery Services vault backup storage cost exceeds growth threshold.",
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
    "COGNITIVE_SEARCH_REPLICA_EXTENDED": AdvancedRule(
        id="COGNITIVE_SEARCH_REPLICA_EXTENDED",
        name="AI Search Replica Review",
        description="Search service replica count exceeds query volume requirements.",
        category=Category.COST,
        severity=Severity.MEDIUM,
    ),
    "NETWORK_FRONT_DOOR_IDLE_EXTENDED": AdvancedRule(
        id="NETWORK_FRONT_DOOR_IDLE_EXTENDED",
        name="Front Door Low Traffic Review",
        description="Front Door profile has low request volume for its cost.",
        category=Category.NETWORK,
        severity=Severity.LOW,
    ),
    "NETWORK_FRONT_DOOR_COST_EXTENDED": AdvancedRule(
        id="NETWORK_FRONT_DOOR_COST_EXTENDED",
        name="Front Door Cost Review",
        description="Front Door profile has recurring cost above optimization threshold.",
        category=Category.NETWORK,
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
        cosmos_serverless_ru_threshold=50000.0,
    ),
    "COSMOS_RU_RIGHT_SIZING_UNDER": AdvancedRule(
        id="COSMOS_RU_RIGHT_SIZING_UNDER",
        name="Cosmos DB Under-Provisioned RU Utilization",
        description="Sustained low normalized RU consumption supports downscaling provisioned throughput.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        cosmos_ru_low_pct=20.0,
        evaluation_window_days=30,
    ),
    "COSMOS_RU_RIGHT_SIZING_OVER": AdvancedRule(
        id="COSMOS_RU_RIGHT_SIZING_OVER",
        name="Cosmos DB High RU Utilization",
        description="Sustained high normalized RU consumption requires more provisioned throughput.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        cosmos_ru_high_pct=80.0,
    ),
    "COSMOS_THROTTLING_DETECTED": AdvancedRule(
        id="COSMOS_THROTTLING_DETECTED",
        name="Cosmos DB Throttling Risk",
        description="Normalized RU consumption near 100% indicates imminent 429 throttling.",
        category=Category.DATABASE,
        severity=Severity.HIGH,
        cosmos_throttle_ru_pct=95.0,
    ),
    "COSMOS_HOT_CONTAINER_DETECTED": AdvancedRule(
        id="COSMOS_HOT_CONTAINER_DETECTED",
        name="Cosmos DB Hot Partition",
        description="Uneven RU consumption suggests partition key skew or hot containers.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        cosmos_hot_partition_skew_ratio=2.5,
    ),
    "COSMOS_API_COST_VARIANCE": AdvancedRule(
        id="COSMOS_API_COST_VARIANCE",
        name="Cosmos DB API Cost Premium",
        description="Non-SQL Cosmos APIs may carry higher RU cost than the SQL API.",
        category=Category.DATABASE,
        severity=Severity.LOW,
    ),
    "COSMOS_CONSISTENCY_OVERPROVISIONED": AdvancedRule(
        id="COSMOS_CONSISTENCY_OVERPROVISIONED",
        name="Cosmos DB Consistency Review",
        description="Strong or bounded staleness consistency increases RU cost for reads and writes.",
        category=Category.DATABASE,
        severity=Severity.LOW,
    ),
    "COSMOS_LARGE_ITEMS_DETECTED": AdvancedRule(
        id="COSMOS_LARGE_ITEMS_DETECTED",
        name="Cosmos DB Large Items",
        description="Average item size exceeds 2 MB and increases RU and storage cost.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
        cosmos_large_item_bytes=2097152.0,
    ),
    "COSMOS_INDEXING_OVERPROVISIONED": AdvancedRule(
        id="COSMOS_INDEXING_OVERPROVISIONED",
        name="Cosmos DB Index Over-Provisioning",
        description="Index size is large relative to data — custom indexing may reduce cost.",
        category=Category.DATABASE,
        severity=Severity.LOW,
        cosmos_index_to_data_ratio=1.5,
    ),
    "COSMOS_MULTI_WRITE_UNNECESSARY": AdvancedRule(
        id="COSMOS_MULTI_WRITE_UNNECESSARY",
        name="Cosmos DB Multi-Write Review",
        description="Multi-region writes multiply throughput cost when global writes are not required.",
        category=Category.DATABASE,
        severity=Severity.MEDIUM,
    ),
    "COSMOS_FAILOVER_UNNECESSARY": AdvancedRule(
        id="COSMOS_FAILOVER_UNNECESSARY",
        name="Cosmos DB Failover Review",
        description="Automatic failover on non-production accounts may be unnecessary.",
        category=Category.DATABASE,
        severity=Severity.LOW,
    ),
    "COSMOS_FREE_TIER_SUBOPTIMAL": AdvancedRule(
        id="COSMOS_FREE_TIER_SUBOPTIMAL",
        name="Cosmos DB Free Tier Review",
        description="Free tier is enabled but usage exceeds included RU/s capacity.",
        category=Category.DATABASE,
        severity=Severity.LOW,
    ),
    "COSMOS_RESERVED_CAPACITY_ELIGIBLE": AdvancedRule(
        id="COSMOS_RESERVED_CAPACITY_ELIGIBLE",
        name="Cosmos DB Reserved Capacity Candidate",
        description="Stable provisioned RU consumption is eligible for reserved capacity savings.",
        category=Category.COST,
        severity=Severity.MEDIUM,
        cosmos_ru_low_pct=20.0,
        cosmos_ru_high_pct=80.0,
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
    "PRIVATE_ENDPOINT_UNDERUTILIZED": AdvancedRule(
        id="PRIVATE_ENDPOINT_UNDERUTILIZED",
        name="Private Endpoint Underutilized",
        description="Private endpoint shows very low byte volume — candidate for deletion or consolidation.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
        pe_underutilized_bytes_monthly=107_374_182_400.0,
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
    "PRIVATE_LINK_NAT_PORT_PRESSURE": AdvancedRule(
        id="PRIVATE_LINK_NAT_PORT_PRESSURE",
        name="Private Link NAT Port Pressure",
        description="Private link service NAT port utilization exceeds safe threshold.",
        category=Category.NETWORK,
        severity=Severity.HIGH,
        pls_nat_port_pressure_pct=80.0,
        min_monthly_savings_usd=0.0,
    ),
    "PRIVATE_LINK_NAT_RIGHTSIZE": AdvancedRule(
        id="PRIVATE_LINK_NAT_RIGHTSIZE",
        name="Private Link NAT Right-Size",
        description="Low NAT port utilization suggests private link consolidation opportunity.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
        pls_nat_port_low_pct=30.0,
        min_monthly_savings_usd=5.0,
    ),
    "PRIVATE_DNS_EMPTY_EXTENDED": AdvancedRule(
        id="PRIVATE_DNS_EMPTY_EXTENDED",
        name="Empty Private DNS Zone",
        description="Private DNS zone has no record sets beyond SOA/NS — delete if unused.",
        category=Category.NETWORK,
        severity=Severity.LOW,
        private_dns_max_default_record_sets=2,
        min_monthly_savings_usd=1.0,
    ),
    "PRIVATE_DNS_UNUSED_ZONE": AdvancedRule(
        id="PRIVATE_DNS_UNUSED_ZONE",
        name="Unused Private DNS Zone",
        description="Private DNS zone shows zero query volume over the evaluation window.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
        min_monthly_savings_usd=1.0,
    ),
    "VNET_PEERING_CONSOLIDATION_EXTENDED": AdvancedRule(
        id="VNET_PEERING_CONSOLIDATION_EXTENDED",
        name="VNet Peering Consolidation",
        description="Virtual network peerings may drive recurring data transfer cost.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
        min_monthly_savings_usd=10.0,
    ),
    "VNET_UNUSED_SUBNET_EXTENDED": AdvancedRule(
        id="VNET_UNUSED_SUBNET_EXTENDED",
        name="VNet Unused Subnet",
        description="Virtual network contains subnets with no attached resources.",
        category=Category.NETWORK,
        severity=Severity.LOW,
        min_monthly_savings_usd=0.0,
    ),
    "NSG_FLOW_LOG_COST": AdvancedRule(
        id="NSG_FLOW_LOG_COST",
        name="NSG Flow Log Cost",
        description="NSG flow log ingestion and storage may exceed value for low-traffic NSGs.",
        category=Category.NETWORK,
        severity=Severity.MEDIUM,
        nsg_flow_log_min_gb=1.0,
        min_monthly_savings_usd=5.0,
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
    "DISK_NEW_GRACE_PERIOD": AdvancedRule(
        id="DISK_NEW_GRACE_PERIOD",
        name="New Disk Grace Period",
        description="Skip optimization recommendations for disks created within the grace window.",
        category=Category.COMPUTE,
        severity=Severity.INFO,
        min_monthly_savings_usd=0.0,
    ),
    "DISK_ULTRA_DOWNGRADE_PREMIUM": AdvancedRule(
        id="DISK_ULTRA_DOWNGRADE_PREMIUM",
        name="UltraSSD to Premium Downgrade",
        description="UltraSSD disk IOPS and throughput utilization are low — Premium SSD is more cost-effective.",
        category=Category.COMPUTE,
        severity=Severity.MEDIUM,
        disk_iops_high_util_pct=50.0,
        min_monthly_savings_usd=50.0,
    ),
    "DISK_ULTRA_DOWNGRADE_SSD": AdvancedRule(
        id="DISK_ULTRA_DOWNGRADE_SSD",
        name="UltraSSD to Standard SSD Downgrade",
        description="UltraSSD utilization is very low — Standard SSD may be sufficient.",
        category=Category.COMPUTE,
        severity=Severity.MEDIUM,
        disk_iops_high_util_pct=30.0,
        min_monthly_savings_usd=100.0,
    ),
    "DISK_PREMIUM_DOWNGRADE_HDD": AdvancedRule(
        id="DISK_PREMIUM_DOWNGRADE_HDD",
        name="Premium to Standard HDD Downgrade",
        description="Premium disk shows very low utilization — Standard HDD may be sufficient.",
        category=Category.COMPUTE,
        severity=Severity.LOW,
        disk_iops_high_util_pct=15.0,
        min_monthly_savings_usd=10.0,
    ),
    "DISK_SSD_DOWNGRADE_HDD": AdvancedRule(
        id="DISK_SSD_DOWNGRADE_HDD",
        name="Standard SSD to HDD Downgrade",
        description="Standard SSD shows very low I/O — Standard HDD may be sufficient.",
        category=Category.COMPUTE,
        severity=Severity.LOW,
        disk_iops_high_util_pct=20.0,
        min_monthly_savings_usd=2.0,
    ),
}

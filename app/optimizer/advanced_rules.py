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
        description="Disk is unattached long enough to be considered waste.",
        category=Category.COMPUTE,
        severity=Severity.HIGH,
    ),
    "SNAPSHOT_RETENTION_EXTENDED": AdvancedRule(
        id="SNAPSHOT_RETENTION_EXTENDED",
        name="Extended Snapshot Retention",
        description="Old snapshots should be removed or moved to a governed retention set.",
        category=Category.COMPUTE,
        severity=Severity.LOW,
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
    "BUDGET_GUARDRAIL_EXTENDED": AdvancedRule(
        id="BUDGET_GUARDRAIL_EXTENDED",
        name="Budget Guardrail Breach Risk",
        description="Budget current or forecast spend is approaching the configured limit.",
        category=Category.COST,
        severity=Severity.CRITICAL,
    ),
}

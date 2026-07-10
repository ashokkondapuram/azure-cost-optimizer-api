"""Optimization rule definitions.

Every rule is a pure dataclass. The engine loads them from:
  1. Built-in defaults (this file)
  2. DB overrides (EngineConfig table)
  3. API payload overrides at runtime

Severity levels:  CRITICAL | HIGH | MEDIUM | LOW | INFO
Categories:       COMPUTE | KUBERNETES | STORAGE | NETWORK | DATABASE | SECURITY | COST
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"
    INFO     = "INFO"


class Category(str, Enum):
    COMPUTE    = "COMPUTE"
    KUBERNETES = "KUBERNETES"
    STORAGE    = "STORAGE"
    NETWORK    = "NETWORK"
    DATABASE   = "DATABASE"
    SECURITY   = "SECURITY"
    COST       = "COST"


@dataclass
class Rule:
    id:               str
    name:             str
    description:      str
    category:         Category
    severity:         Severity
    enabled:          bool = True
    # Thresholds — all overridable via DB/API
    cpu_idle_pct:     float = 5.0    # VM avg CPU % below this = idle
    cpu_oversize_pct: float = 20.0   # VM avg CPU % below this = oversized
    mem_idle_pct:     float = 10.0   # VM avg mem % below this = idle
    disk_unattached:  bool  = True
    ip_unassociated:  bool  = True
    node_cpu_idle:    float = 10.0   # AKS node CPU % below this = idle
    node_mem_idle:    float = 15.0   # AKS node mem % below this = idle
    node_count_min:   int   = 1      # min nodes before scale-down suggestion
    cluster_dev_hours: str  = "08:00-18:00"  # start-stop window for non-prod
    storage_days_unused: int = 30    # storage account last-modified threshold
    db_dtu_idle_pct:  float = 5.0    # SQL DB avg DTU below this = idle
    budget_warn_pct:  float = 80.0   # % of budget before warning
    budget_crit_pct:  float = 95.0   # % of budget before critical
    reserved_savings_threshold: float = 0.30  # 30% savings to recommend Reserved
    spot_eligible_workloads: list = field(default_factory=lambda: ["batch", "dev", "test", "ci"])
    rightsizing_memory_buffer: float = 1.20  # 20% headroom when recommending SKU
    snapshot_retention_days: int = 90
    snapshot_min_size_gb: int = 0
    min_monthly_savings_usd: float = 1.0
    waste_score_multiplier: float = 1.0
    evaluation_window_days: int = 7


# ─── Built-in rule catalogue ─────────────────────────────────────────────────
DEFAULT_RULES: dict[str, Rule] = {

    # ── COMPUTE ──────────────────────────────────────────────────────────
    "VM_IDLE": Rule(
        id="VM_IDLE", category=Category.COMPUTE, severity=Severity.HIGH,
        name="Idle Virtual Machine",
        description="VM CPU < {cpu_idle_pct}% average over 7 days. Deallocate or delete.",
    ),
    "VM_OVERSIZE": Rule(
        id="VM_OVERSIZE", category=Category.COMPUTE, severity=Severity.MEDIUM,
        name="Oversized Virtual Machine",
        description="VM CPU < {cpu_oversize_pct}% and memory < {mem_idle_pct}%. Downsize SKU.",
    ),
    "VM_NO_RESERVED": Rule(
        id="VM_NO_RESERVED", category=Category.COMPUTE, severity=Severity.MEDIUM,
        name="VM Without Reserved Instance",
        description="Running VM with no reservation. 1-yr RI saves ~40%, 3-yr ~60%.",
    ),
    "VM_STOPPED_DEALLOCATED": Rule(
        id="VM_STOPPED_DEALLOCATED", category=Category.COMPUTE, severity=Severity.HIGH,
        name="Stopped (Not Deallocated) VM",
        description="VM is stopped but still incurring compute charges. Deallocate it.",
    ),
    "DISK_UNATTACHED": Rule(
        id="DISK_UNATTACHED", category=Category.COMPUTE, severity=Severity.HIGH,
        name="Unattached Managed Disk",
        description="Managed disk not attached to any VM. Delete or snapshot-then-delete.",
    ),
    "DISK_OVERSIZE": Rule(
        id="DISK_OVERSIZE", category=Category.COMPUTE, severity=Severity.LOW,
        name="Oversized Disk (Premium → Standard)",
        description="Premium SSD disk on a stopped/idle VM. Downgrade to Standard SSD.",
    ),
    "SNAPSHOT_OLD": Rule(
        id="SNAPSHOT_OLD", category=Category.COMPUTE, severity=Severity.LOW,
        name="Old Disk Snapshot (>90 days)",
        description="Snapshots older than 90 days accumulate cost. Review and delete.",
    ),

    # ── KUBERNETES ───────────────────────────────────────────────────────
    "AKS_NODE_IDLE": Rule(
        id="AKS_NODE_IDLE", category=Category.KUBERNETES, severity=Severity.HIGH,
        name="Idle AKS Node",
        description="Node CPU < {node_cpu_idle}% and mem < {node_mem_idle}%. Enable cluster autoscaler.",
    ),
    "AKS_OVERPROVISIONED": Rule(
        id="AKS_OVERPROVISIONED", category=Category.KUBERNETES, severity=Severity.HIGH,
        name="Over-Provisioned Node Pool",
        description="Node count consistently above actual scheduling needs. Reduce max nodes.",
    ),
    "AKS_DEV_RUNNING_NIGHTS": Rule(
        id="AKS_DEV_RUNNING_NIGHTS", category=Category.KUBERNETES, severity=Severity.MEDIUM,
        name="Dev/Staging Cluster Running Outside Business Hours",
        description="Non-prod cluster running 24/7. Enable start-stop schedule ({cluster_dev_hours}).",
    ),
    "AKS_NO_SPOT": Rule(
        id="AKS_NO_SPOT", category=Category.KUBERNETES, severity=Severity.MEDIUM,
        name="Node Pool Not Using Spot VMs",
        description="System node pool is fine on on-demand. User/batch pools can use Spot (up to 90% savings).",
    ),
    "AKS_OLD_VERSION": Rule(
        id="AKS_OLD_VERSION", category=Category.KUBERNETES, severity=Severity.MEDIUM,
        name="AKS Cluster on Old Kubernetes Version",
        description="Cluster is not on a supported N or N-1 version. Upgrade for security + cost efficiency.",
    ),
    "AKS_NO_AUTOSCALER": Rule(
        id="AKS_NO_AUTOSCALER", category=Category.KUBERNETES, severity=Severity.HIGH,
        name="Cluster Autoscaler Disabled",
        description="No autoscaler = permanently over-provisioned nodes. Enable cluster autoscaler.",
    ),
    "AKS_SINGLE_NODE_POOL": Rule(
        id="AKS_SINGLE_NODE_POOL", category=Category.KUBERNETES, severity=Severity.LOW,
        name="Single Node Pool Architecture",
        description="All workloads on one pool. Split system vs user pools for cost + resilience.",
    ),
    "AKS_EMPTY_POOL": Rule(
        id="AKS_EMPTY_POOL", category=Category.KUBERNETES, severity=Severity.HIGH,
        name="Empty AKS Node Pool",
        description="Node pool has zero nodes or no schedulable capacity. Remove or resize the pool.",
    ),

    # ── STORAGE ──────────────────────────────────────────────────────────
    "STORAGE_HOT_UNUSED": Rule(
        id="STORAGE_HOT_UNUSED", category=Category.STORAGE, severity=Severity.MEDIUM,
        name="Hot Storage Account — Low Activity",
        description="Storage account on Hot tier with no transactions > {storage_days_unused} days. Move to Cool/Archive.",
    ),
    "STORAGE_NO_LIFECYCLE": Rule(
        id="STORAGE_NO_LIFECYCLE", category=Category.STORAGE, severity=Severity.MEDIUM,
        name="No Blob Lifecycle Policy",
        description="Storage account missing lifecycle management. Add tiering rules to auto-move cold data.",
    ),
    "STORAGE_LRS_CRITICAL": Rule(
        id="STORAGE_LRS_CRITICAL", category=Category.STORAGE, severity=Severity.INFO,
        name="LRS Replication on Critical Data",
        description="Storage using Locally Redundant Storage. Consider GRS/ZRS for resilience (cost tradeoff).",
    ),

    # ── NETWORKING ───────────────────────────────────────────────────────
    "IP_UNASSOCIATED": Rule(
        id="IP_UNASSOCIATED", category=Category.NETWORK, severity=Severity.HIGH,
        name="Unassociated Public IP Address",
        description="Static Public IP not associated with any resource. Incurring idle charges. Delete it.",
    ),
    "NIC_UNATTACHED": Rule(
        id="NIC_UNATTACHED", category=Category.NETWORK, severity=Severity.MEDIUM,
        name="Unattached Network Interface",
        description="NIC not attached to a VM or other resource. Delete after confirming no dependency.",
    ),
    "NAT_GATEWAY_IDLE": Rule(
        id="NAT_GATEWAY_IDLE", category=Category.NETWORK, severity=Severity.HIGH,
        name="Idle NAT Gateway",
        description="NAT Gateway with no associated subnets. Costs ~$32+/mo idle. Delete or attach subnets.",
    ),
    "LB_NO_BACKEND": Rule(
        id="LB_NO_BACKEND", category=Category.NETWORK, severity=Severity.HIGH,
        name="Load Balancer With Empty Backend Pool",
        description="Load Balancer has no backend instances. Idle Standard LB costs ~$18/mo. Delete it.",
    ),
    "APPGW_UNUSED": Rule(
        id="APPGW_UNUSED", category=Category.NETWORK, severity=Severity.HIGH,
        name="Application Gateway With No Listeners",
        description="Application Gateway has no active listeners. Costs ~$125+/mo idle. Delete or consolidate.",
    ),

    # ── APP SERVICES ─────────────────────────────────────────────────────
    "ASP_EMPTY": Rule(
        id="ASP_EMPTY", category=Category.COMPUTE, severity=Severity.HIGH,
        name="Empty App Service Plan",
        description="App Service Plan with no hosted apps. Delete or consolidate workloads.",
    ),
    "ASP_OVERPROVISIONED": Rule(
        id="ASP_OVERPROVISIONED", category=Category.COMPUTE, severity=Severity.MEDIUM,
        name="Over-Provisioned App Service Plan",
        description="Premium/isolated plan hosting few apps. Downgrade SKU or consolidate apps.",
    ),
    "PLAN_EMPTY": Rule(
        id="PLAN_EMPTY", category=Category.COMPUTE, severity=Severity.HIGH,
        name="Empty App Service Plan",
        description="App Service Plan hosts no web apps. Delete or consolidate workloads.",
    ),
    "PLAN_UNDERUTILIZED": Rule(
        id="PLAN_UNDERUTILIZED", category=Category.COMPUTE, severity=Severity.MEDIUM,
        name="Underutilized App Service Plan",
        description="Plan CPU and memory utilization are consistently low. Downgrade SKU.",
    ),
    "APP_IDLE": Rule(
        id="APP_IDLE", category=Category.COMPUTE, severity=Severity.MEDIUM,
        name="Idle Web App",
        description="Web app has low request volume or is stopped on a paid plan.",
    ),

    # ── REDIS / CACHE ────────────────────────────────────────────────────
    "REDIS_FAILED": Rule(
        id="REDIS_FAILED", category=Category.DATABASE, severity=Severity.CRITICAL,
        name="Failed Redis Cache",
        description="Azure Cache for Redis in Failed provisioning state. Delete and recreate or open support ticket.",
    ),
    "REDIS_OVERSIZED": Rule(
        id="REDIS_OVERSIZED", category=Category.DATABASE, severity=Severity.MEDIUM,
        name="Oversized Redis Cache",
        description="Premium Redis tier may exceed workload needs. Review SKU and shard count.",
    ),

    # ── DATABASE ─────────────────────────────────────────────────────────
    "SQL_IDLE": Rule(
        id="SQL_IDLE", category=Category.DATABASE, severity=Severity.HIGH,
        name="Idle SQL Database",
        description="SQL DB DTU/vCore utilization < {db_dtu_idle_pct}% for 7 days. Pause (serverless) or delete.",
    ),
    "SQL_NO_SERVERLESS": Rule(
        id="SQL_NO_SERVERLESS", category=Category.DATABASE, severity=Severity.MEDIUM,
        name="SQL DB Not Using Serverless Tier",
        description="Dev/test SQL databases on provisioned compute. Switch to Serverless for auto-pause savings.",
    ),
    "COSMOS_PROVISIONED": Rule(
        id="COSMOS_PROVISIONED", category=Category.DATABASE, severity=Severity.MEDIUM,
        name="Cosmos DB on Provisioned Throughput",
        description="Low-traffic Cosmos DB using provisioned RU/s. Switch to autoscale or serverless.",
    ),

    # ── COST / BILLING ───────────────────────────────────────────────────
    "BUDGET_WARNING": Rule(
        id="BUDGET_WARNING", category=Category.COST, severity=Severity.HIGH,
        name="Approaching Budget Limit",
        description="Subscription spend at {budget_warn_pct}%+ of configured budget.",
    ),
    "BUDGET_CRITICAL": Rule(
        id="BUDGET_CRITICAL", category=Category.COST, severity=Severity.CRITICAL,
        name="Budget Limit Nearly Exceeded",
        description="Subscription spend at {budget_crit_pct}%+ of configured budget. Immediate action required.",
    ),
    "RESERVED_OPPORTUNITY": Rule(
        id="RESERVED_OPPORTUNITY", category=Category.COST, severity=Severity.MEDIUM,
        name="Reserved Instance Opportunity",
        description="Consistent VM usage detected. 1-yr RI saves ~40%, 3-yr ~60% vs pay-as-you-go.",
    ),
    "SAVINGS_PLAN_OPPORTUNITY": Rule(
        id="SAVINGS_PLAN_OPPORTUNITY", category=Category.COST, severity=Severity.MEDIUM,
        name="Azure Savings Plan Opportunity",
        description="Stable compute spend. Azure Savings Plan offers up to 65% discount across any VM family.",
    ),
    "SPOT_OPPORTUNITY": Rule(
        id="SPOT_OPPORTUNITY", category=Category.COST, severity=Severity.MEDIUM,
        name="Spot VM Opportunity",
        description="Batch/dev/test workloads on on-demand VMs. Spot pricing saves up to 90%.",
    ),

    # ── SECURITY ─────────────────────────────────────────────────────────
    "KEYVAULT_SOFT_DELETE_OFF": Rule(
        id="KEYVAULT_SOFT_DELETE_OFF", category=Category.SECURITY, severity=Severity.HIGH,
        name="Key Vault Soft Delete Disabled",
        description="Key Vault without soft delete or purge protection. Accidental deletion is irrecoverable.",
    ),

    # ── DATABASE (advanced) ───────────────────────────────────────────────
    "SQL_ELASTIC_POOL_CANDIDATE": Rule(
        id="SQL_ELASTIC_POOL_CANDIDATE", category=Category.DATABASE, severity=Severity.MEDIUM,
        name="SQL Elastic Pool Candidate",
        description="Multiple databases on one server may consolidate into an elastic pool.",
        min_monthly_savings_usd=5.0,
    ),
    "SQL_HYBRID_BENEFIT_CANDIDATE": Rule(
        id="SQL_HYBRID_BENEFIT_CANDIDATE", category=Category.DATABASE, severity=Severity.LOW,
        name="SQL Hybrid Benefit Candidate",
        description="Provisioned SQL may qualify for Azure Hybrid Benefit licensing.",
        min_monthly_savings_usd=5.0,
    ),

    # ── NETWORK (advanced) ────────────────────────────────────────────────
    "NETWORK_DDOS_PLAN_REVIEW": Rule(
        id="NETWORK_DDOS_PLAN_REVIEW", category=Category.NETWORK, severity=Severity.LOW,
        name="DDoS protection review",
        description="Public IP with DDoS Standard — confirm necessity.",
        min_monthly_savings_usd=5.0,
    ),
    "NETWORK_TRAFFIC_MANAGER_IDLE": Rule(
        id="NETWORK_TRAFFIC_MANAGER_IDLE", category=Category.NETWORK, severity=Severity.LOW,
        name="Traffic Manager review",
        description="Active Traffic Manager profile — validate usage.",
        min_monthly_savings_usd=1.0,
    ),
    "NETWORK_FRONT_DOOR_REVIEW": Rule(
        id="NETWORK_FRONT_DOOR_REVIEW", category=Category.NETWORK, severity=Severity.MEDIUM,
        name="Front Door review",
        description="Azure Front Door profile — review routing and WAF tier.",
        min_monthly_savings_usd=10.0,
    ),
    "NETWORK_EXPRESSROUTE_REVIEW": Rule(
        id="NETWORK_EXPRESSROUTE_REVIEW", category=Category.NETWORK, severity=Severity.MEDIUM,
        name="ExpressRoute review",
        description="ExpressRoute circuit — review bandwidth tier and peering utilization.",
        min_monthly_savings_usd=50.0,
    ),

    # ── DATABASE (query performance) ──────────────────────────────────────
    "SQL_QUERY_PERF_REVIEW": Rule(
        id="SQL_QUERY_PERF_REVIEW", category=Category.DATABASE, severity=Severity.MEDIUM,
        name="SQL query performance review",
        description="Provisioned SQL database — tune queries, indexes, or tier.",
        min_monthly_savings_usd=10.0,
    ),

    # ── GOVERNANCE ────────────────────────────────────────────────────────
    "GOVERNANCE_TAG_ENFORCEMENT": Rule(
        id="GOVERNANCE_TAG_ENFORCEMENT", category=Category.SECURITY, severity=Severity.INFO,
        name="Required tags missing",
        description="Resource is missing mandatory governance tags.",
        min_monthly_savings_usd=0.0,
    ),

    # ── SERVERLESS ────────────────────────────────────────────────────────
    "FUNCTIONS_PLAN_OPTIMIZATION": Rule(
        id="FUNCTIONS_PLAN_OPTIMIZATION", category=Category.COMPUTE, severity=Severity.MEDIUM,
        name="Functions plan optimization",
        description="Function app on dedicated plan — consider Consumption/Flex.",
        min_monthly_savings_usd=1.0,
    ),
}

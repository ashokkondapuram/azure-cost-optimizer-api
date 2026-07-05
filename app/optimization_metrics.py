"""Cost and performance optimization metrics for every resource finding."""

from __future__ import annotations

from datetime import timezone
from typing import Any, Callable

from app.disk_staleness import _parse_azure_datetime, disk_lineage_from_facts
from app.resources.types import sku_text

# ─── Metric definitions ───────────────────────────────────────────────────────

MetricStatusFn = Callable[[Any], str | None]


def _status_cpu(value: Any) -> str | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v < 5:
        return "underutilized"
    if v < 20:
        return "low"
    if v > 85:
        return "high"
    return "healthy"


def _status_idle_ratio(value: Any) -> str | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v >= 0.5:
        return "underutilized"
    if v >= 0.25:
        return "low"
    return "healthy"


def _status_count_idle(value: Any) -> str | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return "underutilized" if v > 0 else "healthy"


def _status_budget_used(value: Any) -> str | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v >= 100:
        return "critical"
    if v >= 80:
        return "high"
    if v >= 60:
        return "low"
    return "healthy"


def _status_age_days(value: Any) -> str | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return "stale" if v > 90 else "healthy"


def _status_truthy_idle(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "underutilized" if not value else "healthy"
    text = str(value).strip().lower()
    if text in {"false", "no", "0", "none", "unattached", "idle", "stopped"}:
        return "underutilized"
    if text in {"true", "yes", "1", "running", "attached", "associated", "enabled"}:
        return "healthy"
    return None


def _status_savings_pct(value: Any) -> str | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v >= 70:
        return "high"
    if v >= 35:
        return "medium"
    return "low"


def _status_informational(value: Any) -> str | None:
    if value is None or value == "":
        return "unavailable"
    return "informational"


def _status_mtd_cost(value: Any, facts: dict[str, Any] | None = None) -> str | None:
    if value is None:
        return None
    threshold = (facts or {}).get("min_monthly_cost")
    if threshold is None:
        return "informational"
    try:
        return "above_threshold" if float(value) >= float(threshold) else "healthy"
    except (TypeError, ValueError):
        return "informational"


METRIC_DEFS: dict[str, dict[str, Any]] = {
    # Cost
    "monthly_cost_usd": {"category": "cost", "id": "mtd_cost", "label": "Month-to-date cost", "unit": "CAD", "format": "money"},
    "monthly_cost": {"category": "cost", "id": "mtd_cost", "label": "Month-to-date cost", "unit": "CAD", "format": "money"},
    "min_monthly_cost": {"category": "cost", "id": "min_monthly_cost", "label": "Minimum monthly cost", "unit": "CAD", "format": "money"},
    "current_spend_usd": {"category": "cost", "id": "current_spend", "label": "Current spend", "unit": "USD", "format": "money"},
    "forecast_spend_usd": {"category": "cost", "id": "forecast_spend", "label": "Forecast spend", "unit": "USD", "format": "money"},
    "amount": {"category": "cost", "id": "budget_limit", "label": "Budget limit", "unit": "USD", "format": "money"},
    # Performance / utilization
    "avg_cpu_pct": {"category": "performance", "id": "avg_cpu", "label": "Average CPU utilization", "unit": "%", "format": "percent", "status_fn": _status_cpu},
    "avg_memory_pct": {"category": "performance", "id": "avg_memory", "label": "Average memory utilization", "unit": "%", "format": "percent", "status_fn": _status_cpu},
    "memory_usage_pct": {"category": "performance", "id": "memory_usage", "label": "Memory utilization", "unit": "%", "format": "percent", "status_fn": _status_cpu},
    "used_pct": {"category": "performance", "id": "budget_utilization", "label": "Budget utilization", "unit": "%", "format": "percent", "status_fn": _status_budget_used},
    "idle_nodes": {"category": "performance", "id": "idle_nodes", "label": "Idle nodes", "unit": "nodes", "format": "number", "status_fn": _status_count_idle},
    "idle_node_ratio": {"category": "performance", "id": "idle_node_ratio", "label": "Idle node ratio", "unit": "ratio", "format": "percent", "status_fn": _status_idle_ratio},
    "node_count": {"category": "performance", "id": "node_count", "label": "Node count", "unit": "nodes", "format": "number"},
    "pool_count": {"category": "performance", "id": "pool_count", "label": "Node pools", "unit": "pools", "format": "number"},
    "uptime_hours": {"category": "performance", "id": "uptime_hours", "label": "Uptime hours", "unit": "hours", "format": "number"},
    "age_days": {"category": "performance", "id": "age_days", "label": "Resource age", "unit": "days", "format": "number", "status_fn": _status_age_days},
    "last_owner_name": {"category": "performance", "id": "last_owner", "label": "Last owner name", "unit": "resource", "format": "text"},
    "time_created": {"category": "performance", "id": "time_created", "label": "Created", "unit": "date", "format": "datetime"},
    "last_ownership_update": {
        "category": "performance",
        "id": "last_ownership_update",
        "label": "Last ownership update time",
        "unit": "date",
        "format": "datetime",
    },
    "size_gb": {"category": "performance", "id": "size_gb", "label": "Size", "unit": "GB", "format": "number"},
    "storage_gb": {"category": "performance", "id": "storage_gb", "label": "Storage provisioned", "unit": "GB", "format": "number"},
    "http_listener_count": {"category": "performance", "id": "http_listeners", "label": "HTTP listeners", "unit": "listeners", "format": "number", "status_fn": _status_truthy_idle},
    "backend_pool_count": {"category": "performance", "id": "backend_pools", "label": "Backend pools", "unit": "pools", "format": "number"},
    "subnet_count": {"category": "performance", "id": "subnets", "label": "Associated subnets", "unit": "subnets", "format": "number", "status_fn": _status_truthy_idle},
    "app_count": {"category": "performance", "id": "app_count", "label": "Hosted apps", "unit": "apps", "format": "number"},
    "nic_count": {"category": "performance", "id": "nic_count", "label": "Network interfaces", "unit": "NICs", "format": "number"},
    "replication_count": {"category": "performance", "id": "replication", "label": "Replication count", "unit": "replicas", "format": "number"},
    "power_state": {"category": "performance", "id": "power_state", "label": "Power state", "unit": "state", "format": "text"},
    "provisioning_state": {"category": "performance", "id": "provisioning_state", "label": "Provisioning state", "unit": "state", "format": "text"},
    "disk_state": {"category": "performance", "id": "disk_state", "label": "Disk state", "unit": "state", "format": "text"},
    "state": {"category": "performance", "id": "resource_state", "label": "Resource state", "unit": "state", "format": "text"},
    "allocation": {"category": "performance", "id": "ip_allocation", "label": "IP allocation", "unit": "state", "format": "text"},
    "vm_size": {"category": "performance", "id": "vm_size", "label": "VM SKU", "unit": "SKU", "format": "text"},
    "suggested_sku": {"category": "performance", "id": "suggested_sku", "label": "Suggested SKU", "unit": "SKU", "format": "text"},
    "sizing_action": {"category": "performance", "id": "sizing_action", "label": "Sizing action", "unit": "action", "format": "text"},
    "sku": {"category": "performance", "id": "sku", "label": "SKU", "unit": "SKU", "format": "text"},
    "tier": {"category": "performance", "id": "tier", "label": "Service tier", "unit": "tier", "format": "text"},
    "access_tier": {"category": "performance", "id": "access_tier", "label": "Access tier", "unit": "tier", "format": "text"},
    "kubernetes_version": {"category": "performance", "id": "k8s_version", "label": "Kubernetes version", "unit": "version", "format": "text"},
    "alwaysOn": {"category": "performance", "id": "always_on", "label": "Always On", "unit": "flag", "format": "bool"},
    "has_vm": {"category": "performance", "id": "has_vm", "label": "Attached to VM", "unit": "flag", "format": "bool", "status_fn": _status_truthy_idle},
    "has_private_endpoint": {"category": "performance", "id": "private_endpoint", "label": "Private endpoint", "unit": "flag", "format": "bool"},
    "has_lifecycle_policy": {"category": "performance", "id": "lifecycle_policy", "label": "Lifecycle policy", "unit": "flag", "format": "bool", "status_fn": _status_truthy_idle},
    "autoscaler_enabled": {"category": "performance", "id": "autoscaler", "label": "Cluster autoscaler", "unit": "flag", "format": "bool", "status_fn": _status_truthy_idle},
    "all_backends_empty": {"category": "performance", "id": "backends_empty", "label": "All backends empty", "unit": "flag", "format": "bool", "status_fn": lambda v: "underutilized" if v else "healthy"},
    "pricing_model": {"category": "performance", "id": "pricing_model", "label": "Pricing model", "unit": "model", "format": "text"},
    "environment": {"category": "performance", "id": "environment", "label": "Environment tag", "unit": "tag", "format": "text"},
    "azure_service_name": {"category": "cost", "id": "azure_service", "label": "Azure service (billing)", "unit": "service", "format": "text", "status_fn": _status_informational},
    "resource_group": {"category": "performance", "id": "resource_group", "label": "Resource group", "unit": "group", "format": "text"},
    "arm_resource_type": {"category": "performance", "id": "arm_resource_type", "label": "ARM resource type", "unit": "type", "format": "text"},
    "confidence_score": {"category": "performance", "id": "confidence_score", "label": "Recommendation confidence", "unit": "/100", "format": "number"},
    "waste_score": {"category": "performance", "id": "waste_score", "label": "Waste score", "unit": "/100", "format": "number"},
    # Azure Monitor utilization facts (rule-scoped display)
    "byte_count": {"category": "performance", "id": "byte_count", "label": "Bytes transmitted", "unit": "bytes", "format": "number", "status_fn": lambda v: "low" if v is not None and float(v) < 1_000_000 else None},
    "packet_count": {"category": "performance", "id": "packet_count", "label": "Packets transmitted", "unit": "packets", "format": "number"},
    "throughput_bytes": {"category": "performance", "id": "throughput", "label": "Throughput", "unit": "bytes", "format": "number", "status_fn": lambda v: "low" if v is not None and float(v) < 500 else None},
    "request_count": {"category": "performance", "id": "requests", "label": "Request count", "unit": "requests", "format": "number", "status_fn": lambda v: "low" if v is not None and float(v) < 1000 else None},
    "healthy_host_count": {"category": "performance", "id": "healthy_hosts", "label": "Healthy backend hosts", "unit": "hosts", "format": "number"},
    "cpu_pct": {"category": "performance", "id": "avg_cpu", "label": "Average CPU utilization", "unit": "%", "format": "percent", "status_fn": _status_cpu},
    "cluster_cpu_pct": {"category": "performance", "id": "cluster_cpu", "label": "Cluster CPU utilization", "unit": "%", "format": "percent", "status_fn": _status_cpu},
    "cluster_mem_pct": {"category": "performance", "id": "cluster_memory", "label": "Cluster memory utilization", "unit": "%", "format": "percent", "status_fn": _status_cpu},
    "storage_pct": {"category": "performance", "id": "storage_utilization", "label": "Storage utilization", "unit": "%", "format": "percent", "status_fn": _status_cpu},
    "transaction_count": {"category": "performance", "id": "transactions", "label": "Transaction count", "unit": "transactions", "format": "number", "status_fn": lambda v: "low" if v is not None and float(v) < 5000 else None},
    "used_capacity_bytes": {"category": "performance", "id": "used_capacity", "label": "Used capacity", "unit": "bytes", "format": "number"},
    "api_hits": {"category": "performance", "id": "api_hits", "label": "API hits", "unit": "hits", "format": "number", "status_fn": lambda v: "low" if v is not None and float(v) < 10 else None},
    "snat_connection_count": {"category": "performance", "id": "snat_connections", "label": "SNAT connections", "unit": "connections", "format": "number"},
    "pull_count": {"category": "performance", "id": "pull_count", "label": "Image pull count", "unit": "pulls", "format": "number", "status_fn": lambda v: "low" if v is not None and float(v) < 500 else None},
    "disk_read_bps": {"category": "performance", "id": "disk_read", "label": "Disk read throughput", "unit": "B/s", "format": "number"},
    "disk_write_bps": {"category": "performance", "id": "disk_write", "label": "Disk write throughput", "unit": "B/s", "format": "number"},
    "disk_read_iops": {"category": "performance", "id": "disk_read_iops", "label": "Disk read IOPS", "unit": "ops/s", "format": "number"},
    "disk_write_iops": {"category": "performance", "id": "disk_write_iops", "label": "Disk write IOPS", "unit": "ops/s", "format": "number"},
    "disk_iops_utilization_pct": {
        "category": "performance",
        "id": "disk_iops_utilization",
        "label": "Disk IOPS utilization",
        "unit": "%",
        "format": "percent",
        "status_fn": lambda v: "high" if v is not None and float(v) >= 80 else ("low" if v is not None and float(v) < 20 else None),
    },
    "provisioned_iops": {"category": "performance", "id": "provisioned_iops", "label": "Provisioned IOPS", "unit": "IOPS", "format": "number"},
    "provisioned_mbps": {"category": "performance", "id": "provisioned_mbps", "label": "Provisioned throughput", "unit": "MB/s", "format": "number"},
    "source_disk_id": {"category": "performance", "id": "source_disk_id", "label": "Source disk", "unit": "resource", "format": "arm_resource"},
    "total_ru": {"category": "performance", "id": "total_ru", "label": "Total RU consumed", "unit": "RU", "format": "number", "status_fn": lambda v: "low" if v is not None and float(v) < 50000 else None},
    "memory_pct": {"category": "performance", "id": "memory_usage", "label": "Memory utilization", "unit": "%", "format": "percent", "status_fn": _status_cpu},
    "ops_per_sec": {"category": "performance", "id": "ops_per_sec", "label": "Operations per second", "unit": "ops/s", "format": "number"},
}

# Fact keys owned by optimization_metrics.performance (not checks or resource_details).
PERFORMANCE_FACT_KEYS: frozenset[str] = frozenset(
    key for key, defn in METRIC_DEFS.items() if defn.get("category") == "performance"
)

# Engine scores shown on the recommendation card — not duplicated in evidence tables.
ENGINE_SCORE_METRIC_IDS: frozenset[str] = frozenset({"confidence_score", "waste_score"})

# Identity fields — drawer/list already show these; not utilization metrics.
INVENTORY_CONTEXT_FACT_KEYS: frozenset[str] = frozenset({
    "resource_group",
    "arm_resource_type",
    "location",
    "resource_type",
    "canonical_resource_type",
})

# Generic `state` is dropped when a type-specific state fact is present.
_STATE_SUPERSEDED_BY: dict[str, str] = {
    "compute/disk": "disk_state",
    "compute/snapshot": "time_created",
}

# Optional disk lineage — omit gap-fill placeholders when unknown.
_DISK_SKIP_UNAVAILABLE_IDS: frozenset[str] = frozenset({
    "last_owner",
    "last_ownership_update",
})

# Shown once in the cost summary block (not repeated in checks or technical details).
PRIMARY_COST_METRIC_IDS: frozenset[str] = frozenset({"mtd_cost", "estimated_savings", "azure_service"})

# Rule-scoped metric display — only these metrics appear per rule (no N/A filler rows).
RULE_METRIC_PROFILES: dict[str, tuple[str, ...]] = {
    "VM_IDLE": ("avg_cpu", "power_state", "vm_size"),
    "VM_OVERSIZE": ("avg_cpu", "avg_memory", "vm_size"),
    "VM_UNDERUTILIZED_EXTENDED": ("avg_cpu", "avg_memory", "vm_size"),
    "VM_SKU_SIZING_EXTENDED": ("avg_cpu", "avg_memory", "vm_size", "suggested_sku", "sizing_action"),
    "VM_STOPPED_BILLING_EXTENDED": ("power_state", "vm_size"),
    "VM_RIGHTSIZE_FAMILY": ("vm_size", "avg_cpu", "suggested_sku", "sizing_action"),
    "VM_COMMITMENT_CANDIDATE": ("uptime_hours", "vm_size"),
    "DISK_UNATTACHED": ("disk_state", "size_gb", "age_days", "sku", "last_owner", "last_ownership_update"),
    "DISK_UNUSED_EXTENDED": ("disk_state", "size_gb", "disk_read", "disk_write", "age_days", "last_owner", "last_ownership_update", "time_created"),
    "DISK_OVERSIZE": ("disk_state", "size_gb", "sku"),
    "DISK_OVERSIZE_EXTENDED": ("disk_state", "size_gb", "sku", "disk_read", "disk_write", "disk_read_iops", "disk_write_iops", "disk_iops_utilization", "provisioned_iops"),
    "DISK_UNDERPROVISIONED": ("disk_state", "size_gb", "sku", "disk_read_iops", "disk_write_iops", "disk_iops_utilization", "provisioned_iops", "provisioned_mbps"),
    "SNAPSHOT_OLD": ("age_days", "size_gb", "time_created", "sku", "disk_state"),
    "SNAPSHOT_RETENTION_EXTENDED": (
        "age_days", "size_gb", "time_created", "sku", "disk_state",
        "source_disk_id", "incremental", "provisioning_state",
    ),
    "APP_GATEWAY_IDLE_EXTENDED": ("http_listeners", "throughput", "requests", "healthy_hosts"),
    "APPGW_UNUSED": ("http_listeners", "throughput", "requests"),
    "LOAD_BALANCER_IDLE_EXTENDED": ("backend_pools", "backends_empty", "byte_count"),
    "PUBLIC_IP_IDLE_EXTENDED": ("ip_allocation", "byte_count", "packet_count"),
    "IP_UNASSOCIATED": ("ip_allocation",),
    "NAT_GATEWAY_IDLE_EXTENDED": ("subnets", "byte_count", "snat_connections"),
    "NIC_ORPHANED_EXTENDED": ("has_vm",),
    "NIC_UNATTACHED": ("has_vm",),
    "SQL_SERVERLESS_EXTENDED": ("avg_cpu", "tier", "sku"),
    "COSMOS_AUTOSCALE_EXTENDED": ("requests", "total_ru"),
    "STORAGE_LIFECYCLE_EXTENDED": ("transactions", "used_capacity", "access_tier"),
    "STORAGE_REDUNDANCY_EXTENDED": ("sku", "access_tier"),
    "POSTGRESQL_BURSTABLE_EXTENDED": ("avg_cpu", "tier", "sku"),
    "POSTGRESQL_STORAGE_EXTENDED": ("storage_gb", "storage_utilization"),
    "POSTGRESQL_STOPPED_EXTENDED": ("resource_state", "storage_gb"),
    "AKS_IDLE_POOL_EXTENDED": ("cluster_cpu", "cluster_memory", "idle_nodes", "node_count"),
    "AKS_NONPROD_SCHEDULING": ("node_count", "pool_count"),
    "ACR_PREMIUM_EXTENDED": ("pull_count", "push_count", "storage_used_bytes", "sku", "replication_count", "premium_blockers"),
    "ACR_STANDARD_EXTENDED": ("pull_count", "storage_used_bytes", "sku"),
    "ACR_GEO_REPLICATION_EXTENDED": ("replication_count", "sku", "replication_regions"),
    "ACR_STORAGE_HIGH_EXTENDED": ("storage_used_bytes", "pull_count", "push_count", "sku"),
    "ACR_RETENTION_DISABLED_EXTENDED": (
        "storage_used_bytes", "sku", "retention_policy_enabled", "retention_policy_days",
    ),
    "REDIS_HEALTH_EXTENDED": ("resource_state", "memory_usage", "ops_per_sec"),
    "KEYVAULT_PROTECTION_EXTENDED": ("enableSoftDelete", "enablePurgeProtection", "sku"),
    "KEYVAULT_IDLE_EXTENDED": ("api_hits", "sku", "availability_pct"),
    "KEYVAULT_PREMIUM_EXTENDED": ("api_hits", "sku"),
    "KEYVAULT_HIGH_OPS_EXTENDED": ("api_hits", "api_results", "availability_pct"),
    "APP_SERVICE_PLAN_EXTENDED": ("tier", "app_count"),
    "BUDGET_GUARDRAIL_EXTENDED": ("budget_utilization", "current_spend", "forecast_spend"),
    "COST_EXPORT_ONLY_RESOURCE": ("arm_resource_type", "resource_state"),
}

RULE_METRIC_VARIANTS: dict[str, dict[str, tuple[str, ...]]] = {
    "APP_GATEWAY_IDLE_EXTENDED": {
        "idle_no_listeners": ("http_listeners",),
        "low_throughput": ("http_listeners", "throughput", "requests", "healthy_hosts"),
    },
    "PUBLIC_IP_IDLE_EXTENDED": {
        "ip_unassociated": ("ip_allocation",),
        "associated_low_traffic": ("byte_count", "packet_count"),
    },
    "LOAD_BALANCER_IDLE_EXTENDED": {
        "idle_no_backends": ("backend_pools", "backends_empty"),
        "low_traffic": ("byte_count", "backend_pools"),
    },
    "NAT_GATEWAY_IDLE_EXTENDED": {
        "unassociated_nat": ("subnets",),
        "associated_low_traffic": ("byte_count", "snat_connections", "subnets"),
    },
    "KEYVAULT_PROTECTION_EXTENDED": {
        "protection_baseline_gap": ("enableSoftDelete", "enablePurgeProtection", "sku"),
    },
    "KEYVAULT_IDLE_EXTENDED": {
        "idle_vault": ("api_hits", "availability_pct"),
    },
    "KEYVAULT_PREMIUM_EXTENDED": {
        "premium_idle": ("api_hits", "sku"),
    },
    "KEYVAULT_HIGH_OPS_EXTENDED": {
        "high_api_volume": ("api_hits", "api_results"),
    },
}

METRIC_ID_TO_FACT_KEYS: dict[str, list[str]] = {}
for _fact_key, _defn in METRIC_DEFS.items():
    METRIC_ID_TO_FACT_KEYS.setdefault(_defn["id"], []).append(_fact_key)


_ARM_TO_CANONICAL: dict[str, str] = {
    "microsoft.compute/virtualmachines": "compute/vm",
    "microsoft.compute/disks": "compute/disk",
    "microsoft.compute/snapshots": "compute/snapshot",
    "microsoft.containerservice/managedclusters": "containers/aks",
    "microsoft.containerregistry/registries": "containers/acr",
    "microsoft.storage/storageaccounts": "storage/account",
    "microsoft.network/publicipaddresses": "network/publicip",
    "microsoft.network/networkinterfaces": "network/nic",
    "microsoft.network/natgateways": "network/nat",
    "microsoft.network/loadbalancers": "network/loadbalancer",
    "microsoft.network/applicationgateways": "network/appgateway",
    "microsoft.network/networksecuritygroups": "network/nsg",
    "microsoft.web/sites": "appservice/webapp",
    "microsoft.web/serverfarms": "appservice/plan",
    "microsoft.sql/servers": "database/sql",
    "microsoft.documentdb/databaseaccounts": "database/cosmosdb",
    "microsoft.dbforpostgresql/flexibleservers": "database/postgresql",
    "microsoft.cache/redis": "database/redis",
    "microsoft.keyvault/vaults": "security/keyvault",
    "microsoft.operationalinsights/workspaces": "monitoring/loganalytics",
    "microsoft.insights/components": "monitoring/appinsights",
    "microsoft.apimanagement/service": "integration/apim",
    "microsoft.datafactory/factories": "integration/datafactory",
    "microsoft.logic/workflows": "integration/logicapp",
    "microsoft.eventhub/namespaces": "messaging/eventhub",
    "microsoft.servicebus/namespaces": "messaging/servicebus",
    "microsoft.databricks/workspaces": "analytics/databricks",
    "microsoft.synapse/workspaces": "analytics/synapse",
    "microsoft.kusto/clusters": "analytics/adx",
    "microsoft.machinelearningservices/workspaces": "analytics/mlworkspace",
    "microsoft.recoveryservices/vaults": "backup/recoveryvault",
    "microsoft.search/searchservices": "search/cognitivesearch",
}


def _fmt_money(value: float) -> str:
    return f"${value:,.2f}"


def _fmt_percent(value: float) -> str:
    return f"{value:.1f}%"


def _fmt_number(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


_MONTH_ABBR = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _fmt_datetime(value: Any) -> str:
    parsed = _parse_azure_datetime(value)
    if not parsed:
        return str(value)
    local = parsed.astimezone(timezone.utc)
    hour = local.hour % 12 or 12
    minute = f"{local.minute:02d}"
    period = "AM" if local.hour < 12 else "PM"
    return f"{_MONTH_ABBR[local.month - 1]} {local.day}, {local.year} at {hour}:{minute} {period}"


def _format_metric_value(value: Any, fmt: str) -> str:
    if value is None:
        return "—"
    if fmt == "money":
        try:
            return _fmt_money(float(value))
        except (TypeError, ValueError):
            return str(value)
    if fmt == "percent":
        try:
            v = float(value)
            if 0 <= v <= 1 and "ratio" not in fmt:
                v *= 100
            return _fmt_percent(v)
        except (TypeError, ValueError):
            return str(value)
    if fmt == "number":
        try:
            return _fmt_number(float(value))
        except (TypeError, ValueError):
            return str(value)
    if fmt == "bool":
        if isinstance(value, bool):
            return "Yes" if value else "No"
        text = str(value).strip().lower()
        return "Yes" if text in {"true", "yes", "1", "enabled"} else "No"
    if fmt == "datetime":
        return _fmt_datetime(value)
    if fmt == "arm_resource":
        text = str(value).strip()
        if "/subscriptions/" in text.lower() and "/providers/" in text.lower():
            return text.rstrip("/").split("/")[-1] or text
        return text
    return str(value)


def _metric_entry(
    metric_id: str,
    label: str,
    value: Any,
    *,
    unit: str = "",
    fmt: str = "text",
    status: str | None = None,
    source: str | None = None,
    unavailable: bool = False,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": metric_id,
        "label": label,
        "unit": unit,
        "formatted": _format_metric_value(value, fmt) if not unavailable else "Not available",
    }
    if value is not None and not unavailable:
        try:
            if fmt in {"money", "percent", "number"}:
                entry["value"] = float(value)
            elif fmt == "bool":
                entry["value"] = bool(value) if isinstance(value, bool) else str(value).lower() in {"true", "yes", "1"}
            else:
                entry["value"] = value
        except (TypeError, ValueError):
            entry["value"] = value
    else:
        entry["value"] = None
    if status:
        entry["status"] = status
    if unavailable:
        entry["status"] = "unavailable"
    if source:
        entry["source"] = source
    return entry


def _canonical_component(resource_type: str, rule_id: str = "", evidence: dict[str, Any] | None = None) -> str:
    ev = evidence or {}
    if ev.get("data_source") == "cost_export" or ev.get("source") == "cost_export":
        return "cost/export"
    rtype = (resource_type or "").strip().lower()
    known_canonical = set(_ARM_TO_CANONICAL.values())
    if rtype in known_canonical:
        return rtype
    if rtype in _ARM_TO_CANONICAL:
        return _ARM_TO_CANONICAL[rtype]
    if "/providers/" in rtype:
        parts = rtype.split("/providers/")[-1].split("/")
        if len(parts) >= 2:
            arm = f"{parts[0]}/{parts[1]}".lower()
            if arm in _ARM_TO_CANONICAL:
                return _ARM_TO_CANONICAL[arm]
    if (rule_id or "").upper().startswith("BUDGET_"):
        return "budget"
    return rtype.split("/")[0] if "/" in rtype else "generic"


def _metric_source(data_source: str, key: str) -> str:
    ds = (data_source or "").lower()
    if "monitor" in ds or key in {"avg_cpu_pct", "avg_memory_pct", "memory_usage_pct"}:
        return "azure_monitor"
    if "k8s" in ds or key in {"idle_nodes", "idle_node_ratio"}:
        return "k8s_agent"
    if "cost export" in ds:
        return "cost_export"
    return "inventory"


def _normalize_component_facts(facts: dict[str, Any], component: str) -> dict[str, Any]:
    """Drop duplicate generic state when a type-specific state fact exists."""
    out = dict(facts)
    superseded = _STATE_SUPERSEDED_BY.get(component)
    if not superseded:
        return out
    specific = out.get(superseded)
    if specific in (None, ""):
        return out
    generic = out.get("state")
    if generic is not None and str(generic).strip().lower() == str(specific).strip().lower():
        out.pop("state", None)
    return out


def _skip_performance_fact_key(key: str, component: str, facts: dict[str, Any]) -> bool:
    if key in INVENTORY_CONTEXT_FACT_KEYS:
        if component == "cost/export" and key == "arm_resource_type":
            return False
        return True
    superseded = _STATE_SUPERSEDED_BY.get(component)
    if key == "state" and superseded and facts.get(superseded) not in (None, ""):
        return True
    return False


def _collect_fact_sources(evidence: dict[str, Any]) -> dict[str, Any]:
    sources: dict[str, Any] = {}
    blocks: list[dict[str, Any]] = [evidence]
    details = evidence.get("resource_details")
    if isinstance(details, dict):
        blocks.append(details)
    props = evidence.get("properties")
    if isinstance(props, dict):
        blocks.append(props)
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for key, val in block.items():
            if val is not None and val != "" and key not in sources:
                if key == "sku":
                    val = sku_text(val) or val
                sources[key] = val
    return sources


def _infer_data_quality(data_source: str, performance: list[dict], cost: list[dict]) -> str:
    ds = (data_source or "").lower()
    has_monitor = any(m.get("source") == "azure_monitor" for m in performance)
    has_k8s = any(m.get("source") == "k8s_agent" for m in performance)
    has_perf = any(m.get("status") != "unavailable" for m in performance)
    has_cost = bool(cost)

    if "live" in ds and has_monitor:
        return "azure_monitor"
    if has_k8s:
        return "k8s_agent" if not has_monitor else "mixed"
    if "cost export" in ds:
        return "cost_export_with_inventory" if has_perf else "cost_export_only"
    if "azure monitor" in ds.replace("_", " "):
        if has_cost:
            return "azure_monitor_and_cost"
        return "azure_monitor"
    if has_perf and has_cost:
        return "inventory_and_cost"
    if has_cost:
        return "cost_only"
    if has_perf:
        return "inventory_proxy"
    return "limited"


def _rule_metric_profile(rule_id: str, determination: str = "") -> tuple[str, ...] | None:
    rid = (rule_id or "").upper()
    det = (determination or "").strip().lower()
    variants = RULE_METRIC_VARIANTS.get(rid)
    if variants:
        if det and det in variants:
            return variants[det]
        if "default" in variants:
            return variants["default"]
    return RULE_METRIC_PROFILES.get(rid)


def _metric_def_for_id(metric_id: str) -> dict[str, Any] | None:
    for defn in METRIC_DEFS.values():
        if defn.get("id") == metric_id:
            return defn
    return None


def _fact_value_for_metric_id(metric_id: str, facts: dict[str, Any]) -> Any:
    for key in METRIC_ID_TO_FACT_KEYS.get(metric_id, ()):
        val = facts.get(key)
        if val is not None and val != "":
            return val
    return None


def _append_metric_from_id(
    metric_id: str,
    facts: dict[str, Any],
    *,
    data_source: str,
    performance: list[dict[str, Any]],
    seen_perf: set[str],
    component: str,
) -> None:
    if metric_id in seen_perf or metric_id in ENGINE_SCORE_METRIC_IDS:
        return
    val = _fact_value_for_metric_id(metric_id, facts)
    if val is None:
        return
    defn = _metric_def_for_id(metric_id)
    if not defn:
        return
    fact_key = next(
        (k for k in METRIC_ID_TO_FACT_KEYS.get(metric_id, ()) if facts.get(k) is not None),
        METRIC_ID_TO_FACT_KEYS.get(metric_id, [metric_id])[0],
    )
    if _skip_performance_fact_key(fact_key, component, facts):
        return
    status_fn: MetricStatusFn | None = defn.get("status_fn")
    status = status_fn(val) if status_fn else None
    source = _metric_source(data_source, fact_key)
    performance.append(_metric_entry(
        metric_id,
        defn["label"],
        val,
        unit=defn.get("unit", ""),
        fmt=defn.get("format", "text"),
        status=status,
        source=source,
    ))
    seen_perf.add(metric_id)


def build_optimization_metrics(
    evidence: dict[str, Any] | None,
    *,
    finding: dict[str, Any] | None = None,
    rule_id: str = "",
    resource_type: str = "",
) -> dict[str, Any]:
    """Build structured cost + performance metrics for a finding."""
    evidence = dict(evidence or {})
    finding = finding or {}
    facts = _collect_fact_sources(evidence)
    component_hint = _canonical_component(
        resource_type or str(finding.get("resource_type") or ""),
        rule_id,
        evidence,
    )
    if component_hint == "compute/disk":
        facts.update(disk_lineage_from_facts({**evidence, **facts}))
    facts = _normalize_component_facts(facts, component_hint)
    if "uptime_hours" not in facts:
        from app.vm_uptime import parse_azure_datetime, uptime_hours_since
        created_raw = facts.get("time_created") or facts.get("oldest_instance_time_created")
        created = parse_azure_datetime(created_raw)
        if created:
            facts["uptime_hours"] = round(uptime_hours_since(created), 1)
    data_source = str(evidence.get("data_source") or finding.get("data_source") or "")
    determination = str(evidence.get("determination") or "")
    rule_profile = _rule_metric_profile(rule_id, determination)

    cost: list[dict[str, Any]] = []
    performance: list[dict[str, Any]] = []
    seen_cost: set[str] = set()
    seen_perf: set[str] = set()

    monthly = facts.get("monthly_cost_usd") or facts.get("monthly_cost")
    if monthly is not None:
        cost.append(_metric_entry(
            "mtd_cost", "Month-to-date cost", monthly, unit="CAD", fmt="money", source="cost_sync",
            status=_status_mtd_cost(monthly, facts),
        ))
        seen_cost.add("mtd_cost")

    savings = finding.get("estimated_savings_usd")
    try:
        savings_val = float(savings) if savings is not None else 0.0
    except (TypeError, ValueError):
        savings_val = 0.0
    if savings_val > 0:
        cost.append(_metric_entry(
            "estimated_savings", "Estimated monthly savings", savings_val, unit="CAD", fmt="money", source="engine",
        ))
        seen_cost.add("estimated_savings")

    component = _canonical_component(
        resource_type or str(finding.get("resource_type") or ""),
        rule_id,
        evidence,
    )

    if rule_profile is not None:
        for metric_id in rule_profile:
            _append_metric_from_id(
                metric_id,
                facts,
                data_source=data_source,
                performance=performance,
                seen_perf=seen_perf,
                component=component,
            )
    else:
        for key, defn in METRIC_DEFS.items():
            if key not in facts:
                continue
            if _skip_performance_fact_key(key, component, facts):
                continue
            val = facts[key]
            metric_id = defn["id"]
            if metric_id in ENGINE_SCORE_METRIC_IDS:
                continue
            category = defn["category"]
            status_fn: MetricStatusFn | None = defn.get("status_fn")
            status = status_fn(val) if status_fn else None
            source = _metric_source(data_source, key)
            entry = _metric_entry(
                metric_id,
                defn["label"],
                val,
                unit=defn.get("unit", ""),
                fmt=defn.get("format", "text"),
                status=status,
                source=source,
            )
            if category == "cost" and metric_id not in seen_cost:
                cost.append(entry)
                seen_cost.add(metric_id)
            elif category == "performance" and metric_id not in seen_perf:
                performance.append(entry)
                seen_perf.add(metric_id)

    cost = [m for m in cost if m.get("id") in PRIMARY_COST_METRIC_IDS]

    return {
        "cost": cost,
        "performance": performance,
        "data_quality": _infer_data_quality(data_source, performance, cost),
        "component": component,
        "display_mode": "rule_scoped" if rule_profile is not None else "facts_only",
    }


def attach_optimization_metrics(
    evidence: dict[str, Any],
    *,
    finding: dict[str, Any] | None = None,
    rule_id: str = "",
    resource_type: str = "",
) -> dict[str, Any]:
    """Add optimization_metrics block to an evidence payload."""
    out = dict(evidence)
    out["optimization_metrics"] = build_optimization_metrics(
        out,
        finding=finding,
        rule_id=rule_id,
        resource_type=resource_type or (finding or {}).get("resource_type", ""),
    )
    return out

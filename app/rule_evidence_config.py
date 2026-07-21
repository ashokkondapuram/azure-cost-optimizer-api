"""Load per-rule required_evidence contracts from service threshold JSON files."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.optimizer.rule_catalog import RULE_MANIFEST

from app.assessment.config_resolver import assessment_path_for_canonical, load_resource_config

_ROOT = Path(__file__).resolve().parents[1]

# Canonical type → assessment JSON (single source of truth per resource type)
_RULE_EVIDENCE_JSON_PATHS: dict[str, Path] = {
    "containers/aks": _ROOT / "data" / "aks-assessment.json",
    "compute/vm": _ROOT / "data" / "vm-assessment.json",
    "compute/vmss": _ROOT / "data" / "vmss-assessment.json",
    "compute/disk": _ROOT / "data" / "disk-assessment.json",
    "compute/snapshot": _ROOT / "data" / "snapshot-assessment.json",
    "containers/acr": _ROOT / "data" / "container-registry-assessment.json",
    "storage/account": _ROOT / "data" / "storage-account-assessment.json",
    "network/publicip": _ROOT / "data" / "public-ip-assessment.json",
    "network/nic": _ROOT / "data" / "nic-assessment.json",
    "network/nat": _ROOT / "data" / "nat-gateway-assessment.json",
    "network/loadbalancer": _ROOT / "data" / "load-balancer-assessment.json",
    "network/appgateway": _ROOT / "data" / "application-gateway-assessment.json",
    "network/nsg": _ROOT / "data" / "network-security-group-assessment.json",
    "network/frontdoor": _ROOT / "data" / "frontdoor-cdn-assessment.json",
    "network/routetable": _ROOT / "data" / "route-table-assessment.json",
    "database/sql": _ROOT / "data" / "sql-database-assessment.json",
    "database/cosmosdb": _ROOT / "data" / "cosmosdb-assessment.json",
    "database/postgresql": _ROOT / "data" / "postgres-assessment.json",
    "database/redis": _ROOT / "data" / "redis-assessment.json",
    "appservice/webapp": _ROOT / "data" / "appservice-assessment.json",
    "appservice/plan": _ROOT / "data" / "appservice-assessment.json",
    "security/keyvault": _ROOT / "data" / "keyvault-assessment.json",
    "monitoring/loganalytics": _ROOT / "data" / "log-analytics-assessment.json",
    "monitoring/appinsights": _ROOT / "data" / "application-insights-assessment.json",
    "integration/apim": _ROOT / "data" / "api-management-assessment.json",
    "integration/datafactory": _ROOT / "data" / "datafactory-assessment.json",
    "integration/logicapp": _ROOT / "data" / "logic-app-workflow-assessment.json",
    "messaging/eventhub": _ROOT / "data" / "eventhub-assessment.json",
    "messaging/servicebus": _ROOT / "data" / "servicebus-assessment.json",
    "analytics/databricks": _ROOT / "data" / "databricks-assessment.json",
    "analytics/synapse": _ROOT / "data" / "synapse-assessment.json",
    "analytics/adx": _ROOT / "data" / "data-explorer-assessment.json",
    "analytics/mlworkspace": _ROOT / "data" / "machine-learning-workspace-assessment.json",
    "backup/recoveryvault": _ROOT / "data" / "recovery-services-vault-assessment.json",
    "search/cognitivesearch": _ROOT / "data" / "search-service-assessment.json",
    "governance": _ROOT / "data" / "governance_metrics_thresholds.json",
    "cost_anomalies": _ROOT / "data" / "cost_anomaly_metrics_thresholds.json",
}

_MASTER_CONTRACTS_PATH = _ROOT / "data" / "rule_evidence_contracts.json"

# required_evidence.signal → optimization_metrics METRIC_DEFS id
SIGNAL_TO_METRIC_ID: dict[str, str] = {
    "node_cpu_utilization_pct": "cluster_cpu",
    "node_memory_utilization_pct": "cluster_memory",
    "cluster_cpu_utilization_pct": "cluster_cpu",
    "cluster_memory_utilization_pct": "cluster_memory",
    "idle_node_count": "idle_nodes",
    "idle_node_ratio": "idle_node_ratio",
    "cpu_utilization_pct": "avg_cpu",
    "memory_utilization_pct": "avg_memory",
    "avg_cpu_utilization_pct": "avg_cpu",
    "avg_memory_utilization_pct": "avg_memory",
    "power_state": "power_state",
    "disk_iops_utilization_pct": "disk_iops_utilization",
    "disk_throughput_utilization_pct": "disk_throughput_utilization",
    "disk_read_throughput": "disk_read",
    "disk_write_throughput": "disk_write",
    "disk_read_iops": "disk_read_iops",
    "disk_write_iops": "disk_write_iops",
    "provisioned_iops": "provisioned_iops",
    "disk_state": "disk_state",
    "dtu_utilization_pct": "avg_cpu",
    "unattached_days": "age_days",
    "days_idle": "uptime_hours",
    "uptime_hours": "uptime_hours",
    "network_bytes": "byte_count",
    "byte_count": "byte_count",
    "packet_count": "packet_count",
    "request_count": "requests",
    "autoscaler_enabled": "autoscaler",
    "kubernetes_version_supported": "k8s_version",
    "snat_port_utilization_pct": "snat_port_usage_pct",
    "snat_utilization_pct": "snat_utilization_pct",
    "snat_connection_count": "snat_connections",
    "backend_health_pct": "healthy_hosts",
    "transaction_count": "transactions",
    "capacity_used_bytes": "used_capacity",
    "egress_bytes": "egress",
    "api_hits": "api_hits",
    "ru_utilization_pct": "normalized_ru_pct",
    "ru_utilization_peak_pct": "normalized_ru_peak_pct",
    "total_ru_consumed": "total_ru",
    "ru_skew_ratio": "ru_skew_ratio",
    "operations_per_second": "ops_per_sec",
    "server_load_pct": "server_load",
    "cache_hit_rate_pct": "cache_hit_rate",
    "evicted_keys": "evicted_keys",
    "storage_utilization_pct": "storage_utilization",
    "connection_count": "active_connections",
    "replication_lag_seconds": "replication_lag_sec",
    "image_pull_count": "pull_count",
    "registry_storage_gb": "storage_used_bytes",
    "capacity_unit_utilization_pct": "cu_utilization_pct",
    "throughput_bytes": "throughput",
    "budget_utilization_pct": "budget_utilization",
    "monthly_cost_usd": "mtd_cost",
    "risky_rule_count": "risky_rule_count",
    "index_to_data_ratio": "index_to_data_ratio",
    "avg_item_bytes": "avg_item_bytes",
}

# Inventory / configuration facts — belong in Properties, not evidence metrics or checks fallback.
INVENTORY_PROPERTY_FACT_KEYS: frozenset[str] = frozenset({
    "node_count",
    "pool_count",
    "kubernetes_version",
    "kubernetes_minor",
    "supported_versions",
    "default_version",
    "version_source",
    "sku",
    "sku_name",
    "sku_tier",
    "sku_label",
    "tier",
    "state",
    "provisioning_state",
    "provisioningState",
    "vm_size",
    "scale_set_priority",
    "pool_name",
    "environment",
    "system_pool_count",
    "app_count",
    "location",
    "resource_group",
    "arm_resource_type",
    "resource_type",
    "canonical_resource_type",
    "alwaysOn",
    "has_vm",
    "has_private_endpoint",
    "pricing_model",
    "allocation",
    "access_tier",
    "nic_count",
    "replication_count",
    "http_listener_count",
    "backend_pool_count",
    "subnet_count",
    "capacity",
    "size_gb",
    "storage_gb",
    "age_days",
    "time_created",
    "last_owner_name",
    "last_ownership_update",
    "last_ownership_update_time",
    "suggested_sku",
    "suggested_family",
    "sizing_action",
    "missing_tags",
    "api_type",
    "consistency_level",
    "ha_mode",
    "version",
    "backup_retention_days",
    "multi_write_enabled",
    "automatic_failover_enabled",
    "free_tier_enabled",
    "persistence_enabled",
    "shard_count",
    "record_set_count",
    "endpoint_count",
    "ddos_protection",
    "plan_sku",
    "database_count",
    "license_type",
    "enableSoftDelete",
    "enablePurgeProtection",
    "public_ip_count",
    "throughput_gbps",
    "disk_state",
    "all_backends_empty",
    "has_lifecycle_policy",
})

_COMPONENT_TO_CANONICAL: dict[str, str] = {
    "AKS": "containers/aks",
    "VM": "compute/vm",
    "VMSS": "compute/vmss",
    "Virtual Machines": "compute/vm",
    "Virtual Machine Scale Sets": "compute/vmss",
    "Managed Disks": "compute/disk",
    "Disks": "compute/disk",
    "Disk Snapshots": "compute/snapshot",
    "Storage Accounts": "storage/account",
    "Public IPs": "network/publicip",
    "Network Interfaces": "network/nic",
    "NAT Gateways": "network/nat",
    "Load Balancers": "network/loadbalancer",
    "Application Gateways": "network/appgateway",
    "Network Security Groups": "network/nsg",
    "SQL Database": "database/sql",
    "Cosmos DB": "database/cosmosdb",
    "PostgreSQL": "database/postgresql",
    "Redis Cache": "database/redis",
    "Container Registry": "containers/acr",
    "App Service": "appservice/plan",
    "Key Vault": "security/keyvault",
    "Monitoring": "monitoring/loganalytics",
    "Integration": "integration/apim",
    "Messaging": "messaging/eventhub",
    "Analytics": "analytics/databricks",
    "Backup": "backup/recoveryvault",
    "Search": "search/cognitivesearch",
    "Networking": "network/frontdoor",
    "Governance": "governance",
    "Cost Anomalies": "cost_anomalies",
    "Budgets": "governance",
    "Commitments": "compute/vm",
}

_RULE_PREFIX_TO_CANONICAL: tuple[tuple[str, str], ...] = (
    ("AKS_", "containers/aks"),
    ("VMSS_", "compute/vmss"),
    ("VM_", "compute/vm"),
    ("DISK_", "compute/disk"),
    ("SNAPSHOT_", "compute/snapshot"),
    ("STORAGE_", "storage/account"),
    ("PUBLIC_IP_", "network/publicip"),
    ("IP_", "network/publicip"),
    ("NIC_", "network/nic"),
    ("NAT_GATEWAY_", "network/nat"),
    ("LOAD_BALANCER_", "network/loadbalancer"),
    ("LB_", "network/loadbalancer"),
    ("APP_GATEWAY_", "network/appgateway"),
    ("APPGW_", "network/appgateway"),
    ("NSG_", "network/nsg"),
    ("SQL_", "database/sql"),
    ("COSMOS_", "database/cosmosdb"),
    ("POSTGRESQL_", "database/postgresql"),
    ("POSTGRES_", "database/postgresql"),
    ("REDIS_", "database/redis"),
    ("ACR_", "containers/acr"),
    ("ASP_", "appservice/plan"),
    ("WEBAPP_", "appservice/webapp"),
    ("APP_", "appservice/webapp"),
    ("PLAN_", "appservice/plan"),
    ("KEYVAULT_", "security/keyvault"),
    ("LOG_ANALYTICS_", "monitoring/loganalytics"),
    ("APP_INSIGHTS_", "monitoring/appinsights"),
    ("APIM_", "integration/apim"),
    ("API_MANAGEMENT_", "integration/apim"),
    ("DATA_FACTORY_", "integration/datafactory"),
    ("LOGIC_APP_", "integration/logicapp"),
    ("EVENT_HUBS_", "messaging/eventhub"),
    ("SERVICE_BUS_", "messaging/servicebus"),
    ("DATABRICKS_", "analytics/databricks"),
    ("SYNAPSE_", "analytics/synapse"),
    ("ADX_", "analytics/adx"),
    ("ML_WORKSPACE_", "analytics/mlworkspace"),
    ("BACKUP_", "backup/recoveryvault"),
    ("COGNITIVE_SEARCH_", "search/cognitivesearch"),
    ("NETWORK_FRONT_DOOR_", "network/frontdoor"),
    ("CDN_", "network/frontdoor"),
    ("FIREWALL_", "network/frontdoor"),
    ("BUDGET_", "governance"),
    ("GOVERNANCE_", "governance"),
    ("COST_SPIKE_", "cost_anomalies"),
    ("PRIVATE_ENDPOINT_", "network/frontdoor"),
    ("PRIVATE_LINK_", "network/frontdoor"),
    ("PRIVATE_DNS_", "network/frontdoor"),
    ("VNET_", "network/frontdoor"),
)


def canonical_type_for_rule(rule_id: str) -> str:
    manifest = RULE_MANIFEST.get((rule_id or "").upper()) or {}
    component = str(manifest.get("component") or "")
    if component in _COMPONENT_TO_CANONICAL:
        return _COMPONENT_TO_CANONICAL[component]
    rid = (rule_id or "").upper()
    for prefix, ctype in _RULE_PREFIX_TO_CANONICAL:
        if rid.startswith(prefix):
            return ctype
    if rid == "SPOT_OPPORTUNITY":
        return "compute/vm"
    if rid in {"RESERVED_OPPORTUNITY", "SAVINGS_PLAN_OPPORTUNITY", "VM_COMMITMENT_CANDIDATE"}:
        return "compute/vm"
    return ""


@lru_cache(maxsize=1)
def _load_master_contracts() -> dict[str, Any]:
    if not _MASTER_CONTRACTS_PATH.is_file():
        return {}
    with _MASTER_CONTRACTS_PATH.open(encoding="utf-8") as fh:
        return json.load(fh).get("analysis_rules") or {}


@lru_cache(maxsize=32)
def _load_spec(canonical_type: str) -> dict[str, Any]:
    ctype = (canonical_type or "").strip().lower()
    path = _RULE_EVIDENCE_JSON_PATHS.get(ctype) or assessment_path_for_canonical(ctype)
    if not path or not path.is_file():
        config = load_resource_config(ctype)
        return config if config else {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def analysis_rule_config(rule_id: str, canonical_type: str = "") -> dict[str, Any]:
    rid = (rule_id or "").upper()
    ctype = canonical_type or canonical_type_for_rule(rid)

    if ctype:
        spec = _load_spec(ctype)
        schema = str(spec.get("schema_version") or spec.get("schemaVersion") or "")
        if schema.startswith("2"):
            for rule in spec.get("rules") or []:
                if str(rule.get("rule_id") or "").upper() == rid:
                    return {
                        "required_evidence": list(rule.get("required_evidence") or []),
                        "exclude_inventory_facts": True,
                        "evidence_factors": list(rule.get("evidence_factors") or []),
                    }

    # Master contracts file is authoritative for all other rules
    master = _load_master_contracts()
    if rid in master and isinstance(master[rid], dict):
        return dict(master[rid])

    if ctype:
        rules = _load_spec(ctype).get("analysis_rules") or {}
        cfg = rules.get(rid)
        if isinstance(cfg, dict):
            return dict(cfg)

    return {}


def required_evidence_for_rule(rule_id: str, canonical_type: str = "") -> list[dict[str, Any]]:
    cfg = analysis_rule_config(rule_id, canonical_type)
    raw = cfg.get("required_evidence")
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    # Legacy disk JSON uses metrics_required (fact keys)
    ctype = canonical_type or canonical_type_for_rule(rule_id)
    legacy = cfg.get("metrics_required")
    if isinstance(legacy, list) and legacy:
        period = f"{int(_load_spec(ctype).get('optimization_thresholds', {}).get('evaluation_window_days', 7))}d"
        return [
            {"signal": key, "aggregation": "avg", "period": period}
            for key in legacy
            if isinstance(key, str) and key
        ]
    return []


def metric_ids_from_required_evidence(
    rule_id: str,
    canonical_type: str = "",
) -> tuple[str, ...] | None:
    """Return metric ids for rule-scoped evidence, or None when JSON has no contract."""
    cfg = analysis_rule_config(rule_id, canonical_type)
    if "required_evidence" not in cfg and not cfg.get("metrics_required"):
        return None
    evidence = required_evidence_for_rule(rule_id, canonical_type)
    if not evidence and "required_evidence" in cfg:
        return tuple()
    ids: list[str] = []
    for item in evidence:
        signal = str(item.get("signal") or "").strip()
        if not signal:
            continue
        metric_id = SIGNAL_TO_METRIC_ID.get(signal, signal)
        if metric_id not in ids:
            ids.append(metric_id)
    return tuple(ids)


def is_inventory_property_fact(key: str) -> bool:
    return (key or "") in INVENTORY_PROPERTY_FACT_KEYS


def evidence_check_value_keys_for_rule(rule_id: str, canonical_type: str = "") -> frozenset[str]:
    """Fact keys allowed in checks for this rule (from required_evidence signals)."""
    allowed: set[str] = set()
    for item in required_evidence_for_rule(rule_id, canonical_type):
        signal = str(item.get("signal") or "").strip()
        if not signal:
            continue
        for fact_key, metric_id in SIGNAL_TO_METRIC_ID.items():
            if fact_key == signal or metric_id == signal:
                allowed.add(fact_key)
                allowed.add(metric_id)
        allowed.add(signal)
    return frozenset(allowed)


def rules_with_required_evidence() -> dict[str, list[dict[str, Any]]]:
    """All rules that declare required_evidence in JSON contracts."""
    out: dict[str, list[dict[str, Any]]] = {}
    for rid, cfg in _load_master_contracts().items():
        if isinstance(cfg, dict) and cfg.get("required_evidence"):
            out[rid] = list(cfg["required_evidence"])
    return out

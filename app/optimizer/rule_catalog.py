"""Rule catalog metadata — per-rule component grouping and applicable settings.

Each rule exposes only the settings it actually uses, not the full dataclass
field list shared across all rules in the same engine tier.
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any

from app.optimizer.rules import DEFAULT_RULES, Rule
from app.optimizer.advanced_rules import ADVANCED_RULES, AdvancedRule
from app.cost_export_recommendations import COST_EXPORT_RULES
from app.optimizer.rule_overrides import SEVERITY_OPTIONS

# Metadata for every configurable setting key
SETTING_META: dict[str, dict[str, Any]] = {
    "enabled":              {"label": "Rule enabled", "type": "boolean"},
    "cpu_idle_pct":         {"label": "CPU idle threshold", "type": "number", "unit": "%"},
    "cpu_oversize_pct":     {"label": "CPU oversize threshold", "type": "number", "unit": "%"},
    "mem_idle_pct":         {"label": "Memory idle threshold", "type": "number", "unit": "%"},
    "memory_idle_pct":      {"label": "Memory idle threshold", "type": "number", "unit": "%"},
    "disk_unattached":      {"label": "Flag unattached disks", "type": "boolean"},
    "ip_unassociated":      {"label": "Flag unassociated IPs", "type": "boolean"},
    "node_cpu_idle":        {"label": "Node CPU idle threshold", "type": "number", "unit": "%"},
    "node_mem_idle":        {"label": "Node memory idle threshold", "type": "number", "unit": "%"},
    "node_cpu_idle_pct":    {"label": "Node CPU idle threshold", "type": "number", "unit": "%"},
    "node_memory_idle_pct": {"label": "Node memory idle threshold", "type": "number", "unit": "%"},
    "node_count_min":       {"label": "Minimum node count", "type": "number"},
    "cluster_dev_hours":    {"label": "Business hours window", "type": "string", "placeholder": "08:00-18:00"},
    "storage_days_unused":  {"label": "Days without activity", "type": "number", "unit": "days"},
    "db_dtu_idle_pct":      {"label": "SQL DTU idle threshold", "type": "number", "unit": "%"},
    "budget_warn_pct":      {"label": "Budget warning threshold", "type": "number", "unit": "%"},
    "budget_crit_pct":      {"label": "Budget critical threshold", "type": "number", "unit": "%"},
    "reserved_savings_threshold": {"label": "Min savings to recommend RI", "type": "number", "unit": "ratio"},
    "rightsizing_memory_buffer":  {"label": "Memory headroom buffer", "type": "number", "unit": "x"},
    "spot_eligible_workloads":    {"label": "Spot-eligible environments", "type": "list"},
    "evaluation_window_days":     {"label": "Evaluation window", "type": "number", "unit": "days"},
    "min_monthly_savings_usd":    {"label": "Min monthly savings", "type": "number", "unit": "USD"},
    "waste_score_multiplier":     {"label": "Waste score multiplier", "type": "number", "unit": "x"},
    "min_monthly_cost":           {"label": "Min monthly cost", "type": "number", "unit": "USD"},
    "savings_factor":             {"label": "Estimated savings factor", "type": "number", "unit": "ratio"},
    "max_unattached_disk_days":   {"label": "Max unattached disk age", "type": "number", "unit": "days"},
    "disk_io_idle_bps":           {"label": "Disk idle I/O threshold", "type": "number", "unit": "B/s"},
    "disk_idle_min_size_gb":      {"label": "Min disk size for idle I/O check", "type": "number", "unit": "GB"},
    "disk_iops_block_downgrade_pct": {"label": "Block downgrade above IOPS utilization", "type": "number", "unit": "%"},
    "disk_iops_high_util_pct":    {"label": "Under-provisioned IOPS utilization", "type": "number", "unit": "%"},
    "snapshot_retention_days":    {"label": "Snapshot retention", "type": "number", "unit": "days"},
    "snapshot_min_size_gb":       {"label": "Min snapshot size to review", "type": "number", "unit": "GB"},
    "acr_pull_count_low":         {"label": "Low pull count threshold", "type": "number", "unit": "pulls"},
    "acr_storage_high_gb":        {"label": "High storage threshold", "type": "number", "unit": "GB"},
    "acr_push_count_low":         {"label": "Low push count threshold", "type": "number", "unit": "pushes"},
    "kv_api_hits_idle":           {"label": "Idle API hits threshold", "type": "number", "unit": "hits"},
    "kv_api_hits_high":           {"label": "High API hits threshold", "type": "number", "unit": "hits"},
    "public_ip_idle_days":        {"label": "Public IP idle period", "type": "number", "unit": "days"},
    "public_ip_idle_byte_threshold": {"label": "Public IP idle byte threshold", "type": "number", "unit": "bytes"},
    "public_ip_idle_packet_threshold": {"label": "Public IP idle packet threshold", "type": "number", "unit": "packets"},
    "nat_snat_exhaustion_pct": {"label": "NAT SNAT exhaustion threshold", "type": "number", "unit": "%"},
    "nat_snat_low_connection_threshold": {"label": "NAT low SNAT connections", "type": "number", "unit": "count"},
    "nat_throughput_v2_upgrade_gbps": {"label": "NAT StandardV2 throughput threshold", "type": "number", "unit": "Gbps"},
    "nat_idle_byte_threshold": {"label": "NAT idle byte threshold", "type": "number", "unit": "bytes"},
    "lb_snat_pressure_pct": {"label": "Load balancer SNAT pressure threshold", "type": "number", "unit": "%"},
    "lb_throughput_low_pct_of_peak": {"label": "LB avg vs peak throughput %", "type": "number", "unit": "%"},
    "lb_idle_byte_threshold": {"label": "Load balancer idle byte threshold", "type": "number", "unit": "bytes"},
    "min_rightsize_savings_pct":  {"label": "Min right-size savings", "type": "number", "unit": "%"},
    "min_reserved_coverage_hours":{"label": "Min RI coverage hours", "type": "number", "unit": "hrs"},
    "nonprod_shutdown_hours_per_day": {"label": "Non-prod shutdown hours", "type": "number", "unit": "hrs/day"},
    "require_tags":             {"label": "Required governance tags", "type": "list"},
    "prod_tag_values":          {"label": "Production tag values", "type": "list"},
    "nonprod_tag_values":       {"label": "Non-production tag values", "type": "list"},
    "spot_allowed_envs":        {"label": "Spot-allowed environments", "type": "list"},
    "aks_min_system_nodes":     {"label": "Min AKS system nodes", "type": "number"},
    "aks_max_idle_node_ratio":  {"label": "Max idle node ratio", "type": "number", "unit": "ratio"},
    "storage_cool_after_days":  {"label": "Move to Cool after", "type": "number", "unit": "days"},
    "storage_archive_after_days":{"label": "Move to Archive after", "type": "number", "unit": "days"},
    "sql_serverless_candidate_cpu_pct": {"label": "SQL serverless CPU threshold", "type": "number", "unit": "%"},
    "cosmos_autoscale_candidate_utilization_pct": {"label": "Cosmos autoscale utilization", "type": "number", "unit": "%"},
    "cosmos_ru_low_pct": {"label": "Cosmos RU low threshold", "type": "number", "unit": "%"},
    "cosmos_ru_high_pct": {"label": "Cosmos RU high threshold", "type": "number", "unit": "%"},
    "cosmos_throttle_ru_pct": {"label": "Cosmos throttling RU threshold", "type": "number", "unit": "%"},
    "cosmos_serverless_ru_threshold": {"label": "Cosmos serverless RU threshold (7d)", "type": "number", "unit": "RU"},
    "cosmos_index_to_data_ratio": {"label": "Cosmos index-to-data ratio", "type": "number", "unit": "ratio"},
    "cosmos_hot_partition_skew_ratio": {"label": "Cosmos RU skew ratio", "type": "number", "unit": "ratio"},
    "vm_uptime_hours_candidate": {"label": "VM uptime hours for RI", "type": "number", "unit": "hrs"},
    "redis_premium_min_capacity": {"label": "Redis Premium min capacity", "type": "number"},
    "redis_memory_pressure_pct": {"label": "Redis memory pressure threshold", "type": "number", "unit": "%"},
    "redis_low_utilization_pct": {"label": "Redis low memory threshold", "type": "number", "unit": "%"},
    "redis_server_load_low_pct": {"label": "Redis low server load threshold", "type": "number", "unit": "%"},
    "redis_hit_ratio_poor_pct": {"label": "Redis poor hit ratio threshold", "type": "number", "unit": "%"},
    "redis_cluster_ops_threshold": {"label": "Redis cluster ops threshold", "type": "number", "unit": "ops/s"},
    "redis_idle_ops_threshold": {"label": "Redis idle ops threshold", "type": "number", "unit": "ops/s"},
    "asp_min_apps_for_premium": {"label": "Min apps for Premium plan", "type": "number"},
    "savings_plan_min_monthly_usd": {"label": "Min Savings Plan spend", "type": "number", "unit": "USD"},
    "private_dns_max_default_record_sets": {
        "label": "Max default record sets",
        "type": "number",
        "unit": "record sets",
        "placeholder": "2",
    },
    "severity": {
        "label": "Severity",
        "type": "select",
        "options": list(SEVERITY_OPTIONS),
    },
    "exclude_tags": {"label": "Exclude tags", "type": "list"},
    "exclude_resource_group_patterns": {"label": "Exclude resource group patterns", "type": "list"},
    "exclude_resource_types": {"label": "Exclude resource types", "type": "list"},
    "nonprod_severity_cap": {"label": "Non-prod severity cap", "type": "select", "options": list(SEVERITY_OPTIONS)},
}

# Standard rules inherit common tuning knobs in the config UI
_STD_TUNING = ["min_monthly_savings_usd", "waste_score_multiplier", "evaluation_window_days"]

# Per-rule manifest: component label, engine tier, and applicable setting keys
RULE_MANIFEST: dict[str, dict[str, Any]] = {
    # ── Standard / Compute ───────────────────────────────────────────────
    "VM_IDLE":                  {"component": "Virtual Machines", "engine": "standard", "settings": ["cpu_idle_pct", *_STD_TUNING]},
    "VM_OVERSIZE":              {"component": "Virtual Machines", "engine": "standard", "settings": ["cpu_oversize_pct", "mem_idle_pct", "rightsizing_memory_buffer", *_STD_TUNING]},
    "VM_NO_RESERVED":           {"component": "Virtual Machines", "engine": "standard", "settings": ["reserved_savings_threshold", *_STD_TUNING]},
    "VM_STOPPED_DEALLOCATED":   {"component": "Virtual Machines", "engine": "standard", "settings": list(_STD_TUNING)},
    "DISK_UNATTACHED":          {"component": "Managed Disks", "engine": "standard", "settings": ["disk_unattached"]},
    "DISK_OVERSIZE":            {"component": "Managed Disks", "engine": "standard", "settings": []},
    "SNAPSHOT_OLD":             {"component": "Disk Snapshots", "engine": "standard", "settings": ["snapshot_retention_days", "snapshot_min_size_gb"]},
    "ASP_EMPTY":                {"component": "App Service", "engine": "standard", "settings": []},
    "ASP_OVERPROVISIONED":      {"component": "App Service", "engine": "standard", "settings": []},
    # ── Standard / Kubernetes ──────────────────────────────────────────────
    "AKS_NODE_IDLE":            {"component": "AKS", "engine": "standard", "settings": ["node_cpu_idle", "node_mem_idle"]},
    "AKS_OVERPROVISIONED":      {"component": "AKS", "engine": "standard", "settings": ["node_count_min"]},
    "AKS_DEV_RUNNING_NIGHTS":   {"component": "AKS", "engine": "standard", "settings": ["cluster_dev_hours"]},
    "AKS_NO_SPOT":              {"component": "AKS", "engine": "standard", "settings": ["spot_eligible_workloads"]},
    "AKS_OLD_VERSION":          {"component": "AKS", "engine": "standard", "settings": []},
    "AKS_NO_AUTOSCALER":        {"component": "AKS", "engine": "standard", "settings": []},
    "AKS_SINGLE_NODE_POOL":     {"component": "AKS", "engine": "standard", "settings": []},
    # ── Standard / Storage ─────────────────────────────────────────────────
    "STORAGE_HOT_UNUSED":       {"component": "Storage Accounts", "engine": "standard", "settings": ["storage_days_unused"]},
    "STORAGE_NO_LIFECYCLE":    {"component": "Storage Accounts", "engine": "standard", "settings": []},
    "STORAGE_LRS_CRITICAL":     {"component": "Storage Accounts", "engine": "standard", "settings": []},
    # ── Standard / Network ─────────────────────────────────────────────────
    "IP_UNASSOCIATED":          {"component": "Public IPs", "engine": "standard", "settings": ["ip_unassociated"]},
    "NIC_UNATTACHED":           {"component": "Network Interfaces", "engine": "standard", "settings": []},
    "NAT_GATEWAY_IDLE":         {"component": "NAT Gateways", "engine": "standard", "settings": []},
    "LB_NO_BACKEND":            {"component": "Load Balancers", "engine": "standard", "settings": []},
    "APPGW_UNUSED":             {"component": "Application Gateways", "engine": "standard", "settings": []},
    # ── Standard / Database ────────────────────────────────────────────────
    "REDIS_FAILED":             {"component": "Redis Cache", "engine": "standard", "settings": []},
    "REDIS_OVERSIZED":          {"component": "Redis Cache", "engine": "standard", "settings": []},
    "SQL_IDLE":                 {"component": "SQL Database", "engine": "standard", "settings": ["db_dtu_idle_pct"]},
    "SQL_NO_SERVERLESS":        {"component": "SQL Database", "engine": "standard", "settings": []},
    "COSMOS_PROVISIONED":       {"component": "Cosmos DB", "engine": "standard", "settings": []},
    # ── Standard / Cost ────────────────────────────────────────────────────
    "BUDGET_WARNING":           {"component": "Budgets", "engine": "standard", "settings": ["budget_warn_pct"]},
    "BUDGET_CRITICAL":          {"component": "Budgets", "engine": "standard", "settings": ["budget_crit_pct"]},
    "RESERVED_OPPORTUNITY":     {"component": "Commitments", "engine": "standard", "settings": ["reserved_savings_threshold"]},
    "SAVINGS_PLAN_OPPORTUNITY": {"component": "Commitments", "engine": "standard", "settings": []},
    "SPOT_OPPORTUNITY":         {"component": "Virtual Machines", "engine": "standard", "settings": ["spot_eligible_workloads"]},
    # ── Standard / Security ────────────────────────────────────────────────
    "KEYVAULT_SOFT_DELETE_OFF": {"component": "Key Vault", "engine": "standard", "settings": list(_STD_TUNING)},
    # ── Advanced standard-tier rules ───────────────────────────────────────
    "SQL_ELASTIC_POOL_CANDIDATE": {"component": "SQL Database", "engine": "standard", "settings": list(_STD_TUNING)},
    "SQL_HYBRID_BENEFIT_CANDIDATE": {"component": "SQL Database", "engine": "standard", "settings": list(_STD_TUNING)},
    "SQL_QUERY_PERF_REVIEW": {"component": "SQL Database", "engine": "standard", "settings": list(_STD_TUNING)},
    "NETWORK_DDOS_PLAN_REVIEW": {"component": "Networking", "engine": "standard", "settings": list(_STD_TUNING)},
    "NETWORK_TRAFFIC_MANAGER_IDLE": {"component": "Networking", "engine": "standard", "settings": list(_STD_TUNING)},
    "NETWORK_FRONT_DOOR_REVIEW": {"component": "Networking", "engine": "standard", "settings": list(_STD_TUNING)},
    "NETWORK_EXPRESSROUTE_REVIEW": {"component": "Networking", "engine": "standard", "settings": list(_STD_TUNING)},
    "GOVERNANCE_TAG_ENFORCEMENT": {"component": "Governance", "engine": "standard", "settings": list(_STD_TUNING)},
    "FUNCTIONS_PLAN_OPTIMIZATION": {"component": "App Service", "engine": "standard", "settings": list(_STD_TUNING)},
    # ── Extended / Compute ─────────────────────────────────────────────────
    "VM_UNDERUTILIZED_EXTENDED": {"component": "Virtual Machines", "engine": "extended", "settings": ["cpu_idle_pct", "min_monthly_savings_usd", "evaluation_window_days"]},
    "VM_RIGHTSIZE_FAMILY":       {"component": "Virtual Machines", "engine": "extended", "settings": ["cpu_oversize_pct", "min_monthly_savings_usd", "min_rightsize_savings_pct"]},
    "VM_COMMITMENT_CANDIDATE":   {"component": "Commitments", "engine": "extended", "settings": ["min_monthly_savings_usd", "min_reserved_coverage_hours", "vm_uptime_hours_candidate"]},
    "VM_MISSING_GOVERNANCE_TAGS": {"component": "Virtual Machines", "engine": "extended", "settings": ["require_tags", "prod_tag_values", "nonprod_tag_values"]},
    "VM_STOPPED_BILLING_EXTENDED": {"component": "Virtual Machines", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "VM_SKU_SIZING_EXTENDED": {"component": "Virtual Machines", "engine": "extended", "settings": ["cpu_idle_pct", "memory_idle_pct", "cpu_oversize_pct", "min_monthly_savings_usd"]},
    "DISK_UNUSED_EXTENDED":      {"component": "Managed Disks", "engine": "extended", "settings": [
        "max_unattached_disk_days", "disk_io_idle_bps", "disk_idle_min_size_gb", "disk_iops_block_downgrade_pct",
    ]},
    "DISK_OVERSIZE_EXTENDED":    {"component": "Managed Disks", "engine": "extended", "settings": [
        "disk_io_idle_bps", "disk_iops_block_downgrade_pct", "min_monthly_savings_usd",
    ]},
    "DISK_UNDERPROVISIONED":     {"component": "Managed Disks", "engine": "extended", "settings": [
        "disk_iops_high_util_pct", "evaluation_window_days",
    ]},
    "DISK_CAPACITY_RIGHTSIZE_EXTENDED": {"component": "Managed Disks", "engine": "extended", "settings": [
        "min_monthly_savings_usd",
    ]},
    "DISK_QUEUE_DEPTH_EXTENDED": {"component": "Managed Disks", "engine": "extended", "settings": [
        "min_monthly_savings_usd",
    ]},
    "DISK_NEW_GRACE_PERIOD":     {"component": "Managed Disks", "engine": "extended", "settings": []},
    "DISK_ULTRA_DOWNGRADE_PREMIUM": {"component": "Managed Disks", "engine": "extended", "settings": [
        "min_monthly_savings_usd",
    ]},
    "DISK_ULTRA_DOWNGRADE_SSD":  {"component": "Managed Disks", "engine": "extended", "settings": [
        "min_monthly_savings_usd",
    ]},
    "DISK_PREMIUM_DOWNGRADE_HDD": {"component": "Managed Disks", "engine": "extended", "settings": [
        "min_monthly_savings_usd",
    ]},
    "DISK_SSD_DOWNGRADE_HDD":    {"component": "Managed Disks", "engine": "extended", "settings": [
        "min_monthly_savings_usd",
    ]},
    "SNAPSHOT_RETENTION_EXTENDED": {"component": "Disk Snapshots", "engine": "extended", "settings": [
        "snapshot_retention_days", "snapshot_min_size_gb", "min_monthly_savings_usd",
    ]},
    "APP_SERVICE_PLAN_EXTENDED": {"component": "App Service", "engine": "extended", "settings": ["asp_min_apps_for_premium", "min_monthly_savings_usd"]},
    "WEBAPP_STOPPED_EXTENDED":   {"component": "App Service", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "WEBAPP_ALWAYS_ON_EXTENDED": {"component": "App Service", "engine": "extended", "settings": ["prod_tag_values"]},
    # ── Extended / Kubernetes ────────────────────────────────────────────
    "AKS_IDLE_POOL_EXTENDED":    {"component": "AKS", "engine": "extended", "settings": ["node_cpu_idle_pct", "node_memory_idle_pct", "aks_max_idle_node_ratio"]},
    "AKS_NONPROD_SCHEDULING":    {"component": "AKS", "engine": "extended", "settings": ["nonprod_tag_values", "nonprod_shutdown_hours_per_day"]},
    "AKS_SYSTEM_POOL_RELIABILITY": {"component": "AKS", "engine": "extended", "settings": ["aks_min_system_nodes", "prod_tag_values"]},
    # ── Extended / Network ───────────────────────────────────────────────
    "PUBLIC_IP_IDLE_EXTENDED":   {"component": "Public IPs", "engine": "extended", "settings": [
        "public_ip_idle_days", "public_ip_idle_byte_threshold", "public_ip_idle_packet_threshold", "min_monthly_savings_usd",
    ]},
    "PUBLIC_IP_BASIC_SKU_MIGRATION": {"component": "Public IPs", "engine": "extended", "settings": []},
    "LOAD_BALANCER_IDLE_EXTENDED": {"component": "Load Balancers", "engine": "extended", "settings": ["min_monthly_savings_usd", "lb_idle_byte_threshold"]},
    "LOAD_BALANCER_SNAT_PRESSURE": {"component": "Load Balancers", "engine": "extended", "settings": ["lb_snat_pressure_pct"]},
    "LOAD_BALANCER_THROUGHPUT_RIGHTSIZE": {"component": "Load Balancers", "engine": "extended", "settings": ["lb_throughput_low_pct_of_peak", "min_monthly_savings_usd"]},
    "LOAD_BALANCER_BACKEND_CONSOLIDATION": {"component": "Load Balancers", "engine": "extended", "settings": ["lb_idle_byte_threshold", "min_monthly_savings_usd"]},
    "LOAD_BALANCER_BASIC_SKU_MIGRATION": {"component": "Load Balancers", "engine": "extended", "settings": []},
    "APP_GATEWAY_IDLE_EXTENDED": {"component": "Application Gateways", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "APP_GATEWAY_CU_SATURATION": {"component": "Application Gateways", "engine": "extended", "settings": ["app_gateway_cu_saturation_pct"]},
    "APP_GATEWAY_CU_RIGHTSIZE_DOWN": {"component": "Application Gateways", "engine": "extended", "settings": ["app_gateway_cu_downsize_pct", "min_monthly_savings_usd"]},
    "PRIVATE_ENDPOINT_UNDERUTILIZED": {"component": "Private Endpoints", "engine": "extended", "settings": ["pe_underutilized_bytes_monthly", "min_monthly_savings_usd"]},
    "PRIVATE_LINK_NAT_PORT_PRESSURE": {"component": "Private Link Services", "engine": "extended", "settings": ["pls_nat_port_pressure_pct"]},
    "PRIVATE_LINK_NAT_RIGHTSIZE": {"component": "Private Link Services", "engine": "extended", "settings": ["pls_nat_port_low_pct", "min_monthly_savings_usd"]},
    "PRIVATE_DNS_UNUSED_ZONE": {"component": "Private DNS Zones", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "VNET_PEERING_CONSOLIDATION_EXTENDED": {"component": "Virtual Networks", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "VNET_UNUSED_SUBNET_EXTENDED": {"component": "Virtual Networks", "engine": "extended", "settings": []},
    "NSG_FLOW_LOG_COST": {"component": "Network Security Groups", "engine": "extended", "settings": ["nsg_flow_log_min_gb", "min_monthly_savings_usd"]},
    "NIC_ORPHANED_EXTENDED":     {"component": "Network Interfaces", "engine": "extended", "settings": []},
    "NAT_GATEWAY_IDLE_EXTENDED": {"component": "NAT Gateways", "engine": "extended", "settings": [
        "nat_idle_byte_threshold", "nat_snat_low_connection_threshold", "min_monthly_savings_usd",
    ]},
    "NAT_GATEWAY_SNAT_EXHAUSTION": {"component": "NAT Gateways", "engine": "extended", "settings": ["nat_snat_exhaustion_pct"]},
    "NAT_GATEWAY_SKU_V2_UPGRADE": {"component": "NAT Gateways", "engine": "extended", "settings": ["nat_throughput_v2_upgrade_gbps"]},
    "NAT_GATEWAY_SUBNET_CONSOLIDATION": {"component": "NAT Gateways", "engine": "extended", "settings": ["nat_idle_byte_threshold", "min_monthly_savings_usd"]},
    "NSG_ORPHANED_EXTENDED":     {"component": "Network Security Groups", "engine": "extended", "settings": []},
    "NSG_PERMISSIVE_EXTENDED":   {"component": "Network Security Groups", "engine": "extended", "settings": []},
    # ── Extended / Storage ─────────────────────────────────────────────────
    "STORAGE_LIFECYCLE_EXTENDED": {"component": "Storage Accounts", "engine": "extended", "settings": ["storage_cool_after_days", "storage_archive_after_days"]},
    "STORAGE_REDUNDANCY_EXTENDED": {"component": "Storage Accounts", "engine": "extended", "settings": ["nonprod_tag_values"]},
    # ── Extended / Database ────────────────────────────────────────────────
    "SQL_SERVERLESS_EXTENDED":   {"component": "SQL Database", "engine": "extended", "settings": ["sql_serverless_candidate_cpu_pct"]},
    "COSMOS_AUTOSCALE_EXTENDED": {"component": "Cosmos DB", "engine": "extended", "settings": ["cosmos_autoscale_candidate_utilization_pct", "cosmos_serverless_ru_threshold", "min_monthly_savings_usd"]},
    "COSMOS_PROVISIONED_EXTENDED": {"component": "Cosmos DB", "engine": "extended", "settings": []},
    "COSMOS_SERVERLESS": {"component": "Cosmos DB", "engine": "extended", "settings": ["cosmos_serverless_ru_threshold", "min_monthly_savings_usd"]},
    "COSMOS_RU_RIGHT_SIZING_UNDER": {"component": "Cosmos DB", "engine": "extended", "settings": ["cosmos_ru_low_pct", "evaluation_window_days", "min_monthly_savings_usd"]},
    "COSMOS_RU_RIGHT_SIZING_OVER": {"component": "Cosmos DB", "engine": "extended", "settings": ["cosmos_ru_high_pct"]},
    "COSMOS_THROTTLING_DETECTED": {"component": "Cosmos DB", "engine": "extended", "settings": ["cosmos_throttle_ru_pct"]},
    "COSMOS_HOT_CONTAINER_DETECTED": {"component": "Cosmos DB", "engine": "extended", "settings": ["cosmos_hot_partition_skew_ratio"]},
    "COSMOS_API_COST_VARIANCE": {"component": "Cosmos DB", "engine": "extended", "settings": []},
    "COSMOS_CONSISTENCY_OVERPROVISIONED": {"component": "Cosmos DB", "engine": "extended", "settings": ["nonprod_tag_values"]},
    "COSMOS_LARGE_ITEMS_DETECTED": {"component": "Cosmos DB", "engine": "extended", "settings": ["cosmos_large_item_bytes"]},
    "COSMOS_INDEXING_OVERPROVISIONED": {"component": "Cosmos DB", "engine": "extended", "settings": ["cosmos_index_to_data_ratio", "min_monthly_savings_usd"]},
    "COSMOS_MULTI_WRITE_UNNECESSARY": {"component": "Cosmos DB", "engine": "extended", "settings": ["nonprod_tag_values", "min_monthly_savings_usd"]},
    "COSMOS_FAILOVER_UNNECESSARY": {"component": "Cosmos DB", "engine": "extended", "settings": ["nonprod_tag_values"]},
    "COSMOS_FREE_TIER_SUBOPTIMAL": {"component": "Cosmos DB", "engine": "extended", "settings": []},
    "COSMOS_RESERVED_CAPACITY_ELIGIBLE": {"component": "Cosmos DB", "engine": "extended", "settings": ["cosmos_ru_low_pct", "cosmos_ru_high_pct", "min_monthly_savings_usd"]},
    "REDIS_HEALTH_EXTENDED":     {"component": "Redis Cache", "engine": "extended", "settings": []},
    "REDIS_RIGHTSIZE_EXTENDED":  {"component": "Redis Cache", "engine": "extended", "settings": ["redis_premium_min_capacity", "min_monthly_savings_usd"]},
    "REDIS_IDLE_DETECTION":      {"component": "Redis Cache", "engine": "extended", "settings": ["redis_idle_ops_threshold", "evaluation_window_days", "min_monthly_savings_usd"]},
    "REDIS_MEMORY_PRESSURE":     {"component": "Redis Cache", "engine": "extended", "settings": ["redis_memory_pressure_pct", "min_monthly_savings_usd"]},
    "REDIS_LOW_UTILIZATION":     {"component": "Redis Cache", "engine": "extended", "settings": ["redis_low_utilization_pct", "redis_server_load_low_pct", "min_monthly_savings_usd"]},
    "REDIS_HIT_RATIO_POOR":      {"component": "Redis Cache", "engine": "extended", "settings": ["redis_hit_ratio_poor_pct"]},
    "REDIS_CLUSTER_UNNECESSARY": {"component": "Redis Cache", "engine": "extended", "settings": ["redis_cluster_ops_threshold", "min_monthly_savings_usd"]},
    "REDIS_PERSISTENCE_REVIEW":  {"component": "Redis Cache", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "POSTGRESQL_STOPPED_EXTENDED": {"component": "PostgreSQL", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "POSTGRESQL_BURSTABLE_EXTENDED": {"component": "PostgreSQL", "engine": "extended", "settings": ["nonprod_tag_values", "min_monthly_savings_usd"]},
    "POSTGRESQL_STORAGE_EXTENDED": {"component": "PostgreSQL", "engine": "extended", "settings": []},
    "POSTGRESQL_LOW_COMPUTE_UTILIZATION": {"component": "PostgreSQL", "engine": "extended", "settings": [
        "postgresql_cpu_low_pct", "postgresql_memory_low_pct", "evaluation_window_days", "min_monthly_savings_usd",
    ]},
    "POSTGRESQL_HIGH_COMPUTE_DEMAND": {"component": "PostgreSQL", "engine": "extended", "settings": ["postgresql_cpu_high_pct"]},
    "POSTGRESQL_MEMORY_PRESSURE": {"component": "PostgreSQL", "engine": "extended", "settings": ["postgresql_memory_pressure_pct"]},
    "POSTGRESQL_STORAGE_EXPANSION": {"component": "PostgreSQL", "engine": "extended", "settings": ["postgresql_storage_high_pct"]},
    "POSTGRESQL_IOPS_PRESSURE": {"component": "PostgreSQL", "engine": "extended", "settings": ["postgresql_iops_pressure_pct"]},
    "POSTGRESQL_CONNECTION_POOL_RISK": {"component": "PostgreSQL", "engine": "extended", "settings": ["postgresql_connection_risk_absolute"]},
    "POSTGRESQL_HA_UNNECESSARY": {"component": "PostgreSQL", "engine": "extended", "settings": ["nonprod_tag_values", "min_monthly_savings_usd"]},
    "POSTGRESQL_HA_REQUIRED": {"component": "PostgreSQL", "engine": "extended", "settings": ["prod_tag_values"]},
    "POSTGRESQL_READ_REPLICA_ANALYSIS": {"component": "PostgreSQL", "engine": "extended", "settings": [
        "postgresql_replication_lag_seconds", "min_monthly_savings_usd",
    ]},
    "POSTGRESQL_VERSION_OUTDATED": {"component": "PostgreSQL", "engine": "extended", "settings": []},
    "POSTGRESQL_BACKUP_RETENTION_REVIEW": {"component": "PostgreSQL", "engine": "extended", "settings": [
        "postgresql_backup_retention_prod_days", "postgresql_backup_retention_dev_days",
    ]},
    "ACR_PREMIUM_EXTENDED":      {"component": "Container Registry", "engine": "extended", "settings": [
        "acr_pull_count_low", "acr_storage_high_gb", "acr_push_count_low",
        "nonprod_tag_values", "min_monthly_savings_usd",
    ]},
    "ACR_STANDARD_EXTENDED":     {"component": "Container Registry", "engine": "extended", "settings": [
        "acr_pull_count_low", "acr_storage_high_gb", "min_monthly_savings_usd",
    ]},
    "ACR_GEO_REPLICATION_EXTENDED": {"component": "Container Registry", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "ACR_STORAGE_HIGH_EXTENDED": {"component": "Container Registry", "engine": "extended", "settings": [
        "acr_storage_high_gb", "acr_pull_count_low", "acr_push_count_low", "min_monthly_savings_usd",
    ]},
    "ACR_RETENTION_DISABLED_EXTENDED": {"component": "Container Registry", "engine": "extended", "settings": [
        "acr_storage_high_gb", "min_monthly_savings_usd",
    ]},
    # ── Extended / Security & Cost ───────────────────────────────────────
    "KEYVAULT_PROTECTION_EXTENDED": {"component": "Key Vault", "engine": "extended", "settings": []},
    "KEYVAULT_IDLE_EXTENDED": {"component": "Key Vault", "engine": "extended", "settings": [
        "kv_api_hits_idle", "min_monthly_savings_usd",
    ]},
    "KEYVAULT_PREMIUM_EXTENDED": {"component": "Key Vault", "engine": "extended", "settings": [
        "kv_api_hits_idle", "nonprod_tag_values", "min_monthly_savings_usd",
    ]},
    "KEYVAULT_HIGH_OPS_EXTENDED": {"component": "Key Vault", "engine": "extended", "settings": [
        "kv_api_hits_high", "min_monthly_savings_usd",
    ]},
    "BUDGET_GUARDRAIL_EXTENDED": {"component": "Budgets", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "BUDGET_WARNING_EXTENDED": {"component": "Budgets", "engine": "extended", "settings": ["budget_warn_pct"]},
    "BUDGET_CRITICAL_EXTENDED": {"component": "Budgets", "engine": "extended", "settings": ["budget_crit_pct"]},
    # ── Extended / AKS (ported standard rules) ─────────────────────────────
    "AKS_OLD_VERSION_EXTENDED": {"component": "AKS", "engine": "extended", "settings": []},
    "AKS_NO_AUTOSCALER_EXTENDED": {"component": "AKS", "engine": "extended", "settings": ["node_count_min"]},
    "AKS_NO_SPOT_EXTENDED": {"component": "AKS", "engine": "extended", "settings": ["spot_allowed_envs"]},
    "AKS_SINGLE_NODE_POOL_EXTENDED": {"component": "AKS", "engine": "extended", "settings": []},
    # ── Extended / Compute & Storage (ported) ──────────────────────────────
    "DISK_OVERSIZE_EXTENDED": {"component": "Managed Disks", "engine": "extended", "settings": [
        "disk_io_idle_bps", "disk_iops_block_downgrade_pct",
    ]},
    "DISK_UNDERPROVISIONED": {"component": "Managed Disks", "engine": "extended", "settings": [
        "disk_iops_high_util_pct", "evaluation_window_days",
    ]},
    "SQL_IDLE_EXTENDED": {"component": "SQL Database", "engine": "extended", "settings": ["db_dtu_idle_pct"]},
    "COSMOS_PROVISIONED_EXTENDED": {"component": "Cosmos DB", "engine": "extended", "settings": []},
    "STORAGE_HOT_UNUSED_EXTENDED": {"component": "Storage Accounts", "engine": "extended", "settings": ["storage_cool_after_days"]},
    "STORAGE_LRS_CRITICAL_EXTENDED": {"component": "Storage Accounts", "engine": "extended", "settings": ["prod_tag_values"]},
    "VMSS_NO_AUTOSCALE_EXTENDED": {"component": "Virtual Machine Scale Sets", "engine": "extended", "settings": []},
    "VMSS_NONPROD_SCHEDULING_EXTENDED": {"component": "Virtual Machine Scale Sets", "engine": "extended", "settings": ["nonprod_tag_values", "nonprod_shutdown_hours_per_day"]},
    # ── Extended / Commitments ─────────────────────────────────────────────
    "RESERVED_OPPORTUNITY_EXTENDED": {"component": "Commitments", "engine": "extended", "settings": ["reserved_savings_threshold", "min_monthly_savings_usd"]},
    "SAVINGS_PLAN_OPPORTUNITY_EXTENDED": {"component": "Commitments", "engine": "extended", "settings": ["savings_plan_min_monthly_usd"]},
    # ── Extended / Monitoring ──────────────────────────────────────────────
    "LOG_ANALYTICS_RETENTION_EXTENDED": {"component": "Monitoring", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "APP_INSIGHTS_SAMPLING_EXTENDED": {"component": "Monitoring", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    # ── Extended / Integration ─────────────────────────────────────────────
    "APIM_SKU_EXTENDED": {"component": "Integration", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "DATA_FACTORY_IR_EXTENDED": {"component": "Integration", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "LOGIC_APP_PLAN_EXTENDED": {"component": "Integration", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    # ── Extended / Messaging ───────────────────────────────────────────────
    "EVENT_HUBS_TIER_EXTENDED": {"component": "Messaging", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "SERVICE_BUS_TIER_EXTENDED": {"component": "Messaging", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    # ── Extended / Analytics ───────────────────────────────────────────────
    "DATABRICKS_CLUSTER_EXTENDED": {"component": "Analytics", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "SYNAPSE_PAUSE_EXTENDED": {"component": "Analytics", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "ADX_INGESTION_EXTENDED": {"component": "Analytics", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "ML_WORKSPACE_COMPUTE_EXTENDED": {"component": "Analytics", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    # ── Extended / Backup & Search ─────────────────────────────────────────
    "BACKUP_RETENTION_EXTENDED": {"component": "Backup", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "COGNITIVE_SEARCH_SKU_EXTENDED": {"component": "Search", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    # ── Extended / Networking ──────────────────────────────────────────────
    "FIREWALL_FIXED_COST_EXTENDED": {"component": "Networking", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "CDN_EGRESS_EXTENDED": {"component": "Networking", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    # ── Standard / App Service (aliases and additions) ─────────────────────
    "PLAN_EMPTY":               {"component": "App Service", "engine": "standard", "settings": []},
    "PLAN_UNDERUTILIZED":       {"component": "App Service", "engine": "standard", "settings": ["cpu_oversize_pct", "mem_idle_pct"]},
    "APP_IDLE":                 {"component": "App Service", "engine": "standard", "settings": ["cpu_idle_pct"]},
    "AKS_EMPTY_POOL":           {"component": "AKS", "engine": "standard", "settings": ["node_count_min"]},
    # ── Extended / resource-specific additions ─────────────────────────────
    "AKS_UNDERUTILIZED":        {"component": "AKS", "engine": "extended", "settings": ["node_cpu_idle_pct", "node_memory_idle_pct", "aks_max_idle_node_ratio"]},
    "COSMOS_SERVERLESS":        {"component": "Cosmos DB", "engine": "extended", "settings": ["cosmos_serverless_ru_threshold", "min_monthly_savings_usd"]},
    "REDIS_TIER_REVIEW":        {"component": "Redis Cache", "engine": "extended", "settings": ["redis_premium_min_capacity", "min_monthly_savings_usd"]},
    "APP_ALWAYS_ON_OFF":        {"component": "App Service", "engine": "extended", "settings": ["prod_tag_values"]},
    "PRIVATE_ENDPOINT_FAILED_EXTENDED": {"component": "Networking", "engine": "extended", "settings": []},
    "PRIVATE_ENDPOINT_ORPHAN_EXTENDED": {"component": "Networking", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "PRIVATE_LINK_UNUSED_EXTENDED": {"component": "Networking", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "PRIVATE_DNS_EMPTY_EXTENDED": {
        "component": "Networking Extended",
        "engine": "extended",
        "settings": ["private_dns_max_default_record_sets", "min_monthly_savings_usd"],
    },
    "VNET_PEERING_REVIEW_EXTENDED": {"component": "Networking Extended", "engine": "extended", "settings": ["min_monthly_savings_usd"]},
    "VM_DISK_BOTTLENECK":         {"component": "Virtual Machines", "engine": "extended", "settings": []},
    "VM_NETWORK_BOTTLENECK":      {"component": "Virtual Machines", "engine": "extended", "settings": []},
    "VM_MEMORY_PRESSURE_EXTENDED": {"component": "Virtual Machines", "engine": "extended", "settings": ["memory_pressure_pct", "min_monthly_savings_usd"]},
    "VM_EGRESS_HIGH_EXTENDED":    {"component": "Virtual Machines", "engine": "extended", "settings": ["network_egress_bytes_monthly", "min_monthly_savings_usd"]},
    "VMSS_AUTOSCALE_TUNING_EXTENDED": {"component": "Virtual Machine Scale Sets", "engine": "extended", "settings": ["vmss_scale_out_cpu_pct", "vmss_scale_in_cpu_pct", "min_monthly_savings_usd"]},
    "DISK_CAPACITY_RIGHTSIZE_EXTENDED": {"component": "Managed Disks", "engine": "extended", "settings": ["disk_capacity_used_pct_max", "min_monthly_savings_usd"]},
    "DISK_QUEUE_DEPTH_EXTENDED":  {"component": "Managed Disks", "engine": "extended", "settings": ["disk_queue_depth_contention"]},
    "SNAPSHOT_ARCHIVE_EXTENDED":  {"component": "Disk Snapshots", "engine": "extended", "settings": ["snapshot_archive_days", "snapshot_delete_days", "snapshot_min_size_gb", "min_monthly_savings_usd"]},
    "AKS_NODE_MEMORY_PRESSURE_EXTENDED": {"component": "AKS", "engine": "extended", "settings": ["node_memory_pressure_pct"]},
    "AKS_POD_DENSITY_EXTENDED":   {"component": "AKS", "engine": "extended", "settings": ["pod_density_low_threshold", "node_cpu_downsize_pct", "min_monthly_savings_usd"]},
    "ACR_IMAGE_RETENTION_EXTENDED": {"component": "Container Registry", "engine": "extended", "settings": ["acr_image_retention_days", "acr_storage_high_gb", "min_monthly_savings_usd"]},
    "WEBAPP_PLAN_LOAD_LOW_EXTENDED": {"component": "App Service", "engine": "extended", "settings": ["plan_load_low_pct", "min_monthly_savings_usd"]},
    "ASP_CONSOLIDATION_CANDIDATE_EXTENDED": {"component": "App Service", "engine": "extended", "settings": ["asp_consolidation_app_max", "min_monthly_savings_usd"]},
    "STORAGE_EGRESS_HIGH_EXTENDED": {"component": "Storage Accounts", "engine": "extended", "settings": ["storage_egress_bytes_monthly", "min_monthly_savings_usd"]},
    "STORAGE_COOL_TIER_CANDIDATE_EXTENDED": {"component": "Storage Accounts", "engine": "extended", "settings": ["storage_cool_after_days", "storage_transaction_low", "min_monthly_savings_usd"]},
    "VM_SCHEDULE_CANDIDATE_EXTENDED": {"component": "Virtual Machines", "engine": "extended", "settings": ["nonprod_tag_values"]},
    "VM_ZOMBIE_CANDIDATE_EXTENDED":   {"component": "Virtual Machines", "engine": "extended", "settings": []},
    "AKS_POOL_CONSOLIDATION":     {"component": "AKS", "engine": "extended", "settings": []},
    "COST_SPIKE_DETECTED":        {"component": "Cost Anomalies", "engine": "extended", "settings": []},
    # ── Cost export rules (explicit manifest; also auto-registered below) ──
    "LOG_ANALYTICS_INGESTION":  {"component": "Monitoring", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "APP_INSIGHTS_SAMPLING":    {"component": "Monitoring", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "API_MANAGEMENT_SKU":       {"component": "Integration", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "DATA_FACTORY_PIPELINE":    {"component": "Integration", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "LOGIC_APP_RUN_HISTORY":    {"component": "Integration", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "EVENT_HUBS_TIER":         {"component": "Messaging", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "SERVICE_BUS_TIER":         {"component": "Messaging", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "DATABRICKS_CLUSTER":       {"component": "Analytics", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "SYNAPSE_PAUSE":            {"component": "Analytics", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "ADX_INGESTION":            {"component": "Analytics", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "ML_WORKSPACE_COMPUTE":     {"component": "Analytics", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "BACKUP_RETENTION":         {"component": "Backup", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "CDN_EGRESS":               {"component": "Networking", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "FIREWALL_FIXED_COST":      {"component": "Networking", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "COGNITIVE_SEARCH_SKU":     {"component": "Search", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "BANDWIDTH_REVIEW":         {"component": "Networking", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "PRIVATE_ENDPOINT_COST":    {"component": "Networking", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "PRIVATE_LINK_COST":        {"component": "Networking", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "IDLE_APP_SERVICE_PLANS":   {"component": "App Service", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "UNUSED_NIC":               {"component": "Network Interfaces", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "IDLE_NAT_GATEWAY":         {"component": "NAT Gateways", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "IDLE_DB_FLEXIBLE_SERVER":  {"component": "PostgreSQL", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "COST_EXPORT_ONLY_RESOURCE": {"component": "Cost export", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
    "UNCLASSIFIED_SERVICE_SPEND": {"component": "Cost export", "engine": "cost_export", "settings": ["min_monthly_cost", "savings_factor"]},
}

# UI / resource-module aliases → canonical rule IDs in RULE_MANIFEST.
RULE_ALIASES: dict[str, str] = {
    "IP_IDLE_EXTENDED": "PUBLIC_IP_IDLE_EXTENDED",
    "IP_UNASSOCIATED": "PUBLIC_IP_IDLE_EXTENDED",
    "PUBLIC_IP_UNASSOCIATED": "PUBLIC_IP_IDLE_EXTENDED",
    "LB_IDLE_EXTENDED": "LOAD_BALANCER_IDLE_EXTENDED",
    "LB_NO_BACKEND": "LOAD_BALANCER_IDLE_EXTENDED",
    "LOAD_BALANCER_NO_BACKEND": "LOAD_BALANCER_IDLE_EXTENDED",
    "NAT_GATEWAY_UNUSED_EXTENDED": "NAT_GATEWAY_IDLE_EXTENDED",
    "IDLE_NAT_GATEWAY": "NAT_GATEWAY_IDLE_EXTENDED",
    "APP_SERVICE_IDLE_EXTENDED": "WEBAPP_STOPPED_EXTENDED",
    "POSTGRES_STORAGE_EXTENDED": "POSTGRESQL_STORAGE_EXTENDED",
    "COST_APIM_REVIEW": "API_MANAGEMENT_SKU",
    "COST_APP_INSIGHTS_REVIEW": "APP_INSIGHTS_SAMPLING",
    "COST_LOGIC_APP_REVIEW": "LOGIC_APP_RUN_HISTORY",
    "COST_LOG_ANALYTICS_REVIEW": "LOG_ANALYTICS_INGESTION",
    "COST_SEARCH_REVIEW": "COGNITIVE_SEARCH_SKU",
    "PLAN_EMPTY": "ASP_EMPTY",
}

# Per canonical resource type → applicable optimization rule IDs.
CANONICAL_RESOURCE_RULES: dict[str, tuple[str, ...]] = {
    "compute/vm": (
        "VM_IDLE", "VM_OVERSIZE", "VM_NO_RESERVED", "VM_STOPPED_DEALLOCATED",
        "VM_UNDERUTILIZED_EXTENDED", "VM_RIGHTSIZE_FAMILY", "VM_SKU_SIZING_EXTENDED",
        "VM_COMMITMENT_CANDIDATE", "VM_MISSING_GOVERNANCE_TAGS", "VM_STOPPED_BILLING_EXTENDED",
        "VM_DISK_BOTTLENECK", "VM_NETWORK_BOTTLENECK",
        "VM_MEMORY_PRESSURE_EXTENDED", "VM_EGRESS_HIGH_EXTENDED",
        "VM_SCHEDULE_CANDIDATE_EXTENDED", "VM_ZOMBIE_CANDIDATE_EXTENDED",
        "SPOT_OPPORTUNITY", "RESERVED_OPPORTUNITY", "SAVINGS_PLAN_OPPORTUNITY",
        "COST_HIGH_SPEND_REVIEW",
    ),
    "compute/vmss": (
        "VM_IDLE", "VM_OVERSIZE", "VM_RIGHTSIZE_FAMILY", "VM_SKU_SIZING_EXTENDED",
        "VMSS_NO_AUTOSCALE_EXTENDED", "VMSS_NONPROD_SCHEDULING_EXTENDED", "VMSS_AUTOSCALE_TUNING_EXTENDED",
        "AKS_UNDERUTILIZED", "COST_HIGH_SPEND_REVIEW",
    ),
    "compute/disk": (
        "DISK_UNATTACHED", "DISK_OVERSIZE", "DISK_UNUSED_EXTENDED", "DISK_OVERSIZE_EXTENDED",
        "DISK_UNDERPROVISIONED", "DISK_CAPACITY_RIGHTSIZE_EXTENDED", "DISK_QUEUE_DEPTH_EXTENDED",
        "COST_HIGH_SPEND_REVIEW",
    ),
    "compute/snapshot": (
        "SNAPSHOT_OLD", "SNAPSHOT_RETENTION_EXTENDED", "SNAPSHOT_ARCHIVE_EXTENDED", "COST_HIGH_SPEND_REVIEW",
    ),
    "containers/aks": (
        "AKS_NODE_IDLE", "AKS_OVERPROVISIONED", "AKS_DEV_RUNNING_NIGHTS", "AKS_NO_SPOT",
        "AKS_OLD_VERSION", "AKS_NO_AUTOSCALER", "AKS_SINGLE_NODE_POOL", "AKS_EMPTY_POOL",
        "AKS_IDLE_POOL_EXTENDED", "AKS_NONPROD_SCHEDULING", "AKS_SYSTEM_POOL_RELIABILITY",
        "AKS_UNDERUTILIZED", "AKS_OLD_VERSION_EXTENDED", "AKS_NO_AUTOSCALER_EXTENDED",
        "AKS_NO_SPOT_EXTENDED", "AKS_SINGLE_NODE_POOL_EXTENDED", "AKS_POOL_CONSOLIDATION",
        "AKS_NODE_MEMORY_PRESSURE_EXTENDED", "AKS_POD_DENSITY_EXTENDED", "COST_HIGH_SPEND_REVIEW",
    ),
    "containers/acr": (
        "ACR_PREMIUM_EXTENDED", "ACR_STANDARD_EXTENDED", "ACR_GEO_REPLICATION_EXTENDED",
        "ACR_STORAGE_HIGH_EXTENDED", "ACR_RETENTION_DISABLED_EXTENDED", "ACR_IMAGE_RETENTION_EXTENDED",
        "COST_HIGH_SPEND_REVIEW",
    ),
    "storage/account": (
        "STORAGE_HOT_UNUSED", "STORAGE_NO_LIFECYCLE", "STORAGE_LRS_CRITICAL",
        "STORAGE_LIFECYCLE_EXTENDED", "STORAGE_REDUNDANCY_EXTENDED",
        "STORAGE_HOT_UNUSED_EXTENDED", "STORAGE_LRS_CRITICAL_EXTENDED",
        "STORAGE_EGRESS_HIGH_EXTENDED", "STORAGE_COOL_TIER_CANDIDATE_EXTENDED",
        "COST_HIGH_SPEND_REVIEW",
    ),
    "network/publicip": (
        "IP_UNASSOCIATED", "PUBLIC_IP_IDLE_EXTENDED", "IP_IDLE_EXTENDED",
        "PUBLIC_IP_BASIC_SKU_MIGRATION",
        "BANDWIDTH_REVIEW", "COST_HIGH_SPEND_REVIEW",
    ),
    "network/vnet": (
        "VNET_PEERING_REVIEW_EXTENDED", "VNET_PEERING_CONSOLIDATION_EXTENDED", "VNET_UNUSED_SUBNET_EXTENDED",
        "BANDWIDTH_REVIEW", "COST_HIGH_SPEND_REVIEW",
    ),
    "network/nic": (
        "NIC_UNATTACHED", "NIC_ORPHANED_EXTENDED", "UNUSED_NIC", "COST_HIGH_SPEND_REVIEW",
    ),
    "network/nat": (
        "NAT_GATEWAY_IDLE", "NAT_GATEWAY_IDLE_EXTENDED", "IDLE_NAT_GATEWAY",
        "NAT_GATEWAY_SNAT_EXHAUSTION", "NAT_GATEWAY_SKU_V2_UPGRADE", "NAT_GATEWAY_SUBNET_CONSOLIDATION",
        "BANDWIDTH_REVIEW", "COST_HIGH_SPEND_REVIEW",
    ),
    "network/loadbalancer": (
        "LB_NO_BACKEND", "LOAD_BALANCER_IDLE_EXTENDED", "LB_IDLE_EXTENDED",
        "LOAD_BALANCER_SNAT_PRESSURE", "LOAD_BALANCER_THROUGHPUT_RIGHTSIZE",
        "LOAD_BALANCER_BACKEND_CONSOLIDATION", "LOAD_BALANCER_BASIC_SKU_MIGRATION",
        "COST_HIGH_SPEND_REVIEW",
    ),
    "network/appgateway": (
        "APPGW_UNUSED", "APP_GATEWAY_IDLE_EXTENDED", "APP_GATEWAY_CU_SATURATION", "APP_GATEWAY_CU_RIGHTSIZE_DOWN",
        "COST_HIGH_SPEND_REVIEW",
    ),
    "network/nsg": (
        "NSG_ORPHANED_EXTENDED", "NSG_PERMISSIVE_EXTENDED", "NSG_FLOW_LOG_COST", "COST_HIGH_SPEND_REVIEW",
    ),
    "network/privateendpoint": (
        "PRIVATE_ENDPOINT_FAILED_EXTENDED", "PRIVATE_ENDPOINT_ORPHAN_EXTENDED", "PRIVATE_ENDPOINT_UNDERUTILIZED",
        "PRIVATE_ENDPOINT_COST", "BANDWIDTH_REVIEW", "COST_HIGH_SPEND_REVIEW",
    ),
    "network/privatelinkservice": (
        "PRIVATE_LINK_UNUSED_EXTENDED", "PRIVATE_LINK_NAT_PORT_PRESSURE", "PRIVATE_LINK_NAT_RIGHTSIZE",
        "PRIVATE_LINK_COST", "COST_HIGH_SPEND_REVIEW",
    ),
    "network/privatedns": (
        "PRIVATE_DNS_EMPTY_EXTENDED", "PRIVATE_DNS_UNUSED_ZONE", "PRIVATE_LINK_COST", "COST_HIGH_SPEND_REVIEW",
    ),
    "network/firewall": (
        "FIREWALL_FIXED_COST_EXTENDED", "FIREWALL_FIXED_COST", "COST_HIGH_SPEND_REVIEW",
    ),
    "network/cdn": (
        "CDN_EGRESS_EXTENDED", "CDN_EGRESS", "COST_HIGH_SPEND_REVIEW",
    ),
    "network/expressroute": (
        "NETWORK_EXPRESSROUTE_REVIEW", "COST_HIGH_SPEND_REVIEW",
    ),
    "network/trafficmanager": (
        "NETWORK_TRAFFIC_MANAGER_IDLE", "COST_HIGH_SPEND_REVIEW",
    ),
    "network/frontdoor": (
        "NETWORK_FRONT_DOOR_REVIEW", "COST_HIGH_SPEND_REVIEW",
    ),
    "database/sql": (
        "SQL_IDLE", "SQL_NO_SERVERLESS", "SQL_IDLE_EXTENDED", "SQL_SERVERLESS_EXTENDED",
        "COST_HIGH_SPEND_REVIEW",
    ),
    "database/cosmosdb": (
        "COSMOS_PROVISIONED", "COSMOS_SERVERLESS", "COSMOS_AUTOSCALE_EXTENDED",
        "COSMOS_PROVISIONED_EXTENDED",
        "COSMOS_RU_RIGHT_SIZING_UNDER", "COSMOS_RU_RIGHT_SIZING_OVER",
        "COSMOS_THROTTLING_DETECTED", "COSMOS_HOT_CONTAINER_DETECTED",
        "COSMOS_API_COST_VARIANCE", "COSMOS_CONSISTENCY_OVERPROVISIONED",
        "COSMOS_LARGE_ITEMS_DETECTED", "COSMOS_INDEXING_OVERPROVISIONED",
        "COSMOS_MULTI_WRITE_UNNECESSARY", "COSMOS_FAILOVER_UNNECESSARY",
        "COSMOS_FREE_TIER_SUBOPTIMAL", "COSMOS_RESERVED_CAPACITY_ELIGIBLE",
        "COST_HIGH_SPEND_REVIEW",
    ),
    "database/postgresql": (
        "POSTGRESQL_STOPPED_EXTENDED", "POSTGRESQL_BURSTABLE_EXTENDED",
        "POSTGRESQL_LOW_COMPUTE_UTILIZATION", "POSTGRESQL_HIGH_COMPUTE_DEMAND",
        "POSTGRESQL_MEMORY_PRESSURE", "POSTGRESQL_STORAGE_EXTENDED", "POSTGRESQL_STORAGE_EXPANSION",
        "POSTGRESQL_IOPS_PRESSURE", "POSTGRESQL_CONNECTION_POOL_RISK",
        "POSTGRESQL_HA_UNNECESSARY", "POSTGRESQL_HA_REQUIRED",
        "POSTGRESQL_READ_REPLICA_ANALYSIS", "POSTGRESQL_VERSION_OUTDATED",
        "POSTGRESQL_BACKUP_RETENTION_REVIEW",
        "POSTGRES_STORAGE_EXTENDED", "IDLE_DB_FLEXIBLE_SERVER", "COST_HIGH_SPEND_REVIEW",
    ),
    "database/redis": (
        "REDIS_FAILED", "REDIS_OVERSIZED", "REDIS_TIER_REVIEW", "REDIS_HEALTH_EXTENDED",
        "REDIS_RIGHTSIZE_EXTENDED", "REDIS_IDLE_DETECTION", "REDIS_MEMORY_PRESSURE",
        "REDIS_LOW_UTILIZATION", "REDIS_HIT_RATIO_POOR", "REDIS_CLUSTER_UNNECESSARY",
        "REDIS_PERSISTENCE_REVIEW", "COST_HIGH_SPEND_REVIEW",
    ),
    "appservice/webapp": (
        "APP_IDLE", "WEBAPP_STOPPED_EXTENDED", "WEBAPP_ALWAYS_ON_EXTENDED",
        "APP_ALWAYS_ON_OFF", "COST_HIGH_SPEND_REVIEW",
    ),
    "appservice/plan": (
        "ASP_EMPTY", "ASP_OVERPROVISIONED", "PLAN_EMPTY", "PLAN_UNDERUTILIZED",
        "APP_SERVICE_PLAN_EXTENDED", "WEBAPP_PLAN_LOAD_LOW_EXTENDED", "ASP_CONSOLIDATION_CANDIDATE_EXTENDED",
        "IDLE_APP_SERVICE_PLANS", "COST_HIGH_SPEND_REVIEW",
    ),
    "security/keyvault": (
        "KEYVAULT_SOFT_DELETE_OFF", "KEYVAULT_PROTECTION_EXTENDED", "KEYVAULT_IDLE_EXTENDED",
        "KEYVAULT_PREMIUM_EXTENDED", "KEYVAULT_HIGH_OPS_EXTENDED", "COST_HIGH_SPEND_REVIEW",
    ),
    "monitoring/loganalytics": (
        "LOG_ANALYTICS_RETENTION_EXTENDED", "LOG_ANALYTICS_INGESTION",
        "COST_LOG_ANALYTICS_REVIEW", "COST_HIGH_SPEND_REVIEW",
    ),
    "monitoring/appinsights": (
        "APP_INSIGHTS_SAMPLING_EXTENDED", "APP_INSIGHTS_SAMPLING",
        "COST_APP_INSIGHTS_REVIEW", "COST_HIGH_SPEND_REVIEW",
    ),
    "integration/apim": (
        "APIM_SKU_EXTENDED", "API_MANAGEMENT_SKU", "COST_APIM_REVIEW", "COST_HIGH_SPEND_REVIEW",
    ),
    "integration/datafactory": (
        "DATA_FACTORY_IR_EXTENDED", "DATA_FACTORY_PIPELINE", "COST_HIGH_SPEND_REVIEW",
    ),
    "integration/logicapp": (
        "LOGIC_APP_PLAN_EXTENDED", "LOGIC_APP_RUN_HISTORY", "COST_LOGIC_APP_REVIEW",
        "COST_HIGH_SPEND_REVIEW",
    ),
    "messaging/eventhub": (
        "EVENT_HUBS_TIER_EXTENDED", "EVENT_HUBS_TIER", "COST_HIGH_SPEND_REVIEW",
    ),
    "messaging/servicebus": (
        "SERVICE_BUS_TIER_EXTENDED", "SERVICE_BUS_TIER", "COST_HIGH_SPEND_REVIEW",
    ),
    "analytics/databricks": (
        "DATABRICKS_CLUSTER_EXTENDED", "DATABRICKS_CLUSTER", "COST_HIGH_SPEND_REVIEW",
    ),
    "analytics/synapse": (
        "SYNAPSE_PAUSE_EXTENDED", "SYNAPSE_PAUSE", "COST_HIGH_SPEND_REVIEW",
    ),
    "analytics/adx": (
        "ADX_INGESTION_EXTENDED", "ADX_INGESTION", "COST_HIGH_SPEND_REVIEW",
    ),
    "analytics/mlworkspace": (
        "ML_WORKSPACE_COMPUTE_EXTENDED", "ML_WORKSPACE_COMPUTE", "COST_HIGH_SPEND_REVIEW",
    ),
    "backup/recoveryvault": (
        "BACKUP_RETENTION_EXTENDED", "BACKUP_RETENTION", "COST_HIGH_SPEND_REVIEW",
    ),
    "search/cognitivesearch": (
        "COGNITIVE_SEARCH_SKU_EXTENDED", "COGNITIVE_SEARCH_SKU", "COST_SEARCH_REVIEW",
        "COST_HIGH_SPEND_REVIEW",
    ),
}

for _alias, _canonical in RULE_ALIASES.items():
    if _canonical in RULE_MANIFEST and _alias not in RULE_MANIFEST:
        RULE_MANIFEST[_alias] = {
            **RULE_MANIFEST[_canonical],
            "alias_of": _canonical,
        }

for _cost_rule in COST_EXPORT_RULES:
    RULE_MANIFEST.setdefault(
        _cost_rule.id,
        {
            "component": _cost_rule.component,
            "engine": "cost_export",
            "settings": ["min_monthly_cost", "savings_factor"],
        },
    )

COMPONENT_ORDER = [
    "Virtual Machines", "Managed Disks", "Disk Snapshots", "App Service", "AKS",
    "Storage Accounts", "Public IPs", "Network Interfaces", "NAT Gateways",
    "Network Security Groups", "Load Balancers", "Application Gateways", "Networking",
    "Networking Extended",
    "Cost Anomalies",
    "SQL Database", "PostgreSQL", "Cosmos DB", "Redis Cache", "Container Registry",
    "Monitoring", "Integration", "Messaging", "Analytics", "Backup", "Search",
    "Key Vault", "Budgets", "Commitments", "Governance", "Cost export",
]

_SKIP_FIELDS = frozenset({
    "id", "name", "description", "category", "severity",
})


def _severity_default(rule: Rule | AdvancedRule | Any) -> str:
    sev = getattr(rule, "severity", "MEDIUM")
    return sev.value if hasattr(sev, "value") else str(sev)


def _build_setting(key: str, default: Any) -> dict[str, Any]:
    meta = SETTING_META.get(key, {"label": key.replace("_", " "), "type": "string"})
    setting: dict[str, Any] = {
        "key": key,
        "label": meta.get("label", key),
        "type": meta.get("type", "string"),
        "unit": meta.get("unit"),
        "placeholder": meta.get("placeholder"),
        "default": default,
    }
    if meta.get("options"):
        setting["options"] = meta["options"]
    return setting


def _append_severity_setting(settings: list[dict[str, Any]], rule: Any) -> None:
    if any(s["key"] == "severity" for s in settings):
        return
    settings.append(_build_setting("severity", _severity_default(rule)))


def _rule_defaults(rule: Rule | AdvancedRule) -> dict[str, Any]:
    if not is_dataclass(rule):
        return {}
    return {
        f.name: getattr(rule, f.name)
        for f in fields(rule)
        if f.name not in _SKIP_FIELDS
    }


def resolve_rule_id(rule_id: str) -> str:
    """Map UI/resource alias IDs to canonical catalog rule IDs."""
    return RULE_ALIASES.get(rule_id, rule_id)


def manifest_for_rule(rule_id: str) -> dict[str, Any]:
    """Return RULE_MANIFEST entry, following aliases when needed."""
    rid = resolve_rule_id(rule_id)
    entry = RULE_MANIFEST.get(rid, {})
    if entry:
        return entry
    return RULE_MANIFEST.get(rule_id, {})


def list_rules_for_canonical_type(canonical_type: str) -> list[str]:
    """Rule IDs applicable to a canonical inventory resource type."""
    return list(CANONICAL_RESOURCE_RULES.get((canonical_type or "").strip().lower(), ()))


def canonical_resource_rule_catalog() -> list[dict[str, Any]]:
    """Per-resource rule index for API and docs."""
    from app.optimizer.component_map import CANONICAL_TO_COMPONENT

    rows: list[dict[str, Any]] = []
    for canonical in sorted(CANONICAL_RESOURCE_RULES):
        rule_ids = CANONICAL_RESOURCE_RULES[canonical]
        rows.append({
            "canonical_type": canonical,
            "component": CANONICAL_TO_COMPONENT.get(canonical),
            "rule_count": len(rule_ids),
            "rule_ids": list(rule_ids),
        })
    return rows


def serialize_cost_export_rule(rule) -> dict[str, Any]:
    """Serialize a cost-export rule with configurable thresholds."""
    manifest = manifest_for_rule(rule.id)
    setting_keys = manifest.get("settings", ["min_monthly_cost", "savings_factor"])
    settings = []
    for key in setting_keys:
        if not hasattr(rule, key):
            continue
        settings.append(_build_setting(key, getattr(rule, key)))
    _append_severity_setting(settings, rule)
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.impact,
        "category": rule.category,
        "severity": rule.severity,
        "component": manifest.get("component", rule.component),
        "engine": "cost_export",
        "enabled": True,
        "settings": settings,
        "has_settings": len(settings) > 0,
    }


def serialize_rule(rule: Rule | AdvancedRule) -> dict[str, Any]:
    """Serialize a rule with only its component-specific settings."""
    manifest = manifest_for_rule(rule.id)
    defaults = _rule_defaults(rule)
    setting_keys = manifest.get("settings", [])
    settings = []
    for key in setting_keys:
        if key not in defaults:
            continue
        settings.append(_build_setting(key, defaults[key]))
    _append_severity_setting(settings, rule)
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "category": rule.category.value,
        "severity": rule.severity.value,
        "component": manifest.get("component", rule.category.value.title()),
        "engine": manifest.get("engine", "standard"),
        "enabled": defaults.get("enabled", True),
        "settings": settings,
        "has_settings": len(settings) > 0,
    }


def _engine_sort_key(engine: str) -> int:
    return {"standard": 0, "extended": 1, "cost_export": 2}.get(engine, 3)


def list_all_rules() -> list[dict[str, Any]]:
    rules = [serialize_rule(r) for r in DEFAULT_RULES.values()]
    rules += [serialize_rule(r) for r in ADVANCED_RULES.values()]
    rules += [serialize_cost_export_rule(r) for r in COST_EXPORT_RULES]
    rules.sort(key=lambda r: (
        COMPONENT_ORDER.index(r["component"]) if r["component"] in COMPONENT_ORDER else 99,
        _engine_sort_key(r["engine"]),
        r["name"],
    ))
    return rules


def list_components() -> list[dict[str, Any]]:
    """Group rules by Azure component for the UI."""
    all_rules = list_all_rules()
    by_component: dict[str, list] = {}
    for rule in all_rules:
        by_component.setdefault(rule["component"], []).append(rule)
    ordered = []
    for comp in COMPONENT_ORDER:
        if comp in by_component:
            ordered.append({
                "component": comp,
                "rule_count": len(by_component[comp]),
                "rules": by_component[comp],
            })
    for comp, rules in by_component.items():
        if comp not in COMPONENT_ORDER:
            ordered.append({"component": comp, "rule_count": len(rules), "rules": rules})
    return ordered

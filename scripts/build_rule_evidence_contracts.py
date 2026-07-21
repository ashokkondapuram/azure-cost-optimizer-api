#!/usr/bin/env python3
"""Generate production-grade required_evidence contracts for optimization rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# value_key / signal in specs → required_evidence entry template
SIGNAL_TEMPLATES: dict[str, dict[str, Any]] = {
    "avg_cpu_pct": {
        "signal": "cpu_utilization_pct",
        "label": "Average CPU utilization",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "threshold_key": "cpu_idle_pct",
        "pillar": "performance",
    },
    "cpu_pct": {
        "signal": "cpu_utilization_pct",
        "label": "CPU utilization",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "threshold_key": "cpu_idle_pct",
        "pillar": "performance",
    },
    "avg_memory_pct": {
        "signal": "memory_utilization_pct",
        "label": "Average memory utilization",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "threshold_key": "memory_downsize_used_pct_max",
        "pillar": "performance",
    },
    "memory_pct": {
        "signal": "memory_utilization_pct",
        "label": "Memory utilization",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "pillar": "performance",
    },
    "cluster_cpu_pct": {
        "signal": "cluster_cpu_utilization_pct",
        "label": "Cluster CPU utilization",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "threshold_key": "node_cpu_downsize_pct",
        "pillar": "performance",
    },
    "cluster_mem_pct": {
        "signal": "cluster_memory_utilization_pct",
        "label": "Cluster memory utilization",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "threshold_key": "node_memory_pressure_pct",
        "pillar": "performance",
    },
    "idle_nodes": {
        "signal": "idle_node_count",
        "label": "Idle nodes",
        "aggregation": "avg",
        "period": "7d",
        "unit": "nodes",
        "pillar": "performance",
    },
    "idle_node_ratio": {
        "signal": "idle_node_ratio",
        "label": "Idle node ratio",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "threshold_key": "aks_max_idle_node_ratio",
        "pillar": "performance",
    },
    "autoscaler_enabled": {
        "signal": "autoscaler_enabled",
        "label": "Cluster autoscaler enabled",
        "aggregation": "current",
        "period": "sync",
        "unit": "flag",
        "pillar": "performance",
    },
    "disk_read_bps": {
        "signal": "disk_read_throughput",
        "label": "Disk read throughput",
        "aggregation": "avg",
        "period": "7d",
        "unit": "B/s",
        "threshold_key": "disk_io_idle_bps",
        "pillar": "performance",
    },
    "disk_write_bps": {
        "signal": "disk_write_throughput",
        "label": "Disk write throughput",
        "aggregation": "avg",
        "period": "7d",
        "unit": "B/s",
        "threshold_key": "disk_io_idle_bps",
        "pillar": "performance",
    },
    "disk_iops_utilization_pct": {
        "signal": "disk_iops_utilization_pct",
        "label": "Disk IOPS utilization",
        "aggregation": "peak",
        "period": "7d",
        "unit": "%",
        "threshold_key": "disk_iops_high_util_pct",
        "pillar": "performance",
    },
    "disk_throughput_utilization_pct": {
        "signal": "disk_throughput_utilization_pct",
        "label": "Disk throughput utilization",
        "aggregation": "peak",
        "period": "7d",
        "unit": "%",
        "pillar": "performance",
    },
    "provisioned_iops": {
        "signal": "provisioned_iops",
        "label": "Provisioned IOPS",
        "aggregation": "current",
        "period": "sync",
        "unit": "IOPS",
        "pillar": "performance",
    },
    "age_days": {
        "signal": "unattached_days",
        "label": "Days since last attachment",
        "aggregation": "current",
        "period": "sync",
        "unit": "days",
        "threshold_key": "max_unattached_disk_days",
        "pillar": "cost",
    },
    "uptime_hours": {
        "signal": "uptime_hours",
        "label": "Uptime hours",
        "aggregation": "sum",
        "period": "30d",
        "unit": "hours",
        "threshold_key": "vm_uptime_hours_candidate",
        "pillar": "performance",
    },
    "power_state": {
        "signal": "power_state",
        "label": "Power state",
        "aggregation": "current",
        "period": "sync",
        "unit": "state",
        "pillar": "cost",
    },
    "byte_count": {
        "signal": "network_bytes",
        "label": "Bytes transmitted",
        "aggregation": "sum",
        "period": "7d",
        "unit": "bytes",
        "threshold_key": "idle_byte_threshold",
        "pillar": "performance",
    },
    "packet_count": {
        "signal": "packet_count",
        "label": "Packets transmitted",
        "aggregation": "sum",
        "period": "7d",
        "unit": "packets",
        "pillar": "performance",
    },
    "snat_port_usage_pct": {
        "signal": "snat_port_utilization_pct",
        "label": "SNAT port utilization",
        "aggregation": "peak",
        "period": "7d",
        "unit": "%",
        "threshold_key": "lb_snat_pressure_pct",
        "pillar": "reliability",
    },
    "snat_utilization_pct": {
        "signal": "snat_utilization_pct",
        "label": "SNAT utilization",
        "aggregation": "peak",
        "period": "7d",
        "unit": "%",
        "threshold_key": "nat_snat_exhaustion_pct",
        "pillar": "reliability",
    },
    "snat_connection_count": {
        "signal": "snat_connection_count",
        "label": "SNAT connections",
        "aggregation": "sum",
        "period": "7d",
        "unit": "connections",
        "pillar": "performance",
    },
    "throughput_bytes": {
        "signal": "throughput_bytes",
        "label": "Throughput",
        "aggregation": "avg",
        "period": "7d",
        "unit": "bytes",
        "pillar": "performance",
    },
    "request_count": {
        "signal": "request_count",
        "label": "Request count",
        "aggregation": "sum",
        "period": "7d",
        "unit": "requests",
        "threshold_key": "app_idle_request_threshold",
        "pillar": "performance",
    },
    "healthy_host_count": {
        "signal": "backend_health_pct",
        "label": "Backend health",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "threshold_key": "backend_availability_low_pct",
        "pillar": "reliability",
    },
    "transaction_count": {
        "signal": "transaction_count",
        "label": "Transaction count",
        "aggregation": "sum",
        "period": "30d",
        "unit": "transactions",
        "threshold_key": "storage_transaction_low",
        "pillar": "performance",
    },
    "used_capacity_bytes": {
        "signal": "capacity_used_bytes",
        "label": "Capacity used",
        "aggregation": "avg",
        "period": "7d",
        "unit": "bytes",
        "threshold_key": "storage_utilization_low_pct",
        "pillar": "performance",
    },
    "egress_bytes": {
        "signal": "egress_bytes",
        "label": "Data egress",
        "aggregation": "sum",
        "period": "MTD",
        "unit": "bytes",
        "threshold_key": "storage_egress_bytes_monthly",
        "pillar": "cost",
    },
    "api_hits": {
        "signal": "api_hits",
        "label": "API hits",
        "aggregation": "sum",
        "period": "7d",
        "unit": "hits",
        "threshold_key": "kv_api_hits_idle",
        "pillar": "performance",
    },
    "dtu_pct": {
        "signal": "dtu_utilization_pct",
        "label": "DTU utilization",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "threshold_key": "db_dtu_idle_pct",
        "pillar": "performance",
    },
    "normalized_ru_pct": {
        "signal": "ru_utilization_pct",
        "label": "RU utilization",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "threshold_key": "cosmos_ru_low_pct",
        "pillar": "performance",
    },
    "normalized_ru_peak_pct": {
        "signal": "ru_utilization_peak_pct",
        "label": "Peak RU utilization",
        "aggregation": "peak",
        "period": "7d",
        "unit": "%",
        "threshold_key": "cosmos_throttle_ru_pct",
        "pillar": "reliability",
    },
    "total_ru": {
        "signal": "total_ru_consumed",
        "label": "Total RU consumed",
        "aggregation": "sum",
        "period": "7d",
        "unit": "RU",
        "threshold_key": "cosmos_serverless_ru_threshold",
        "pillar": "performance",
    },
    "ru_skew_ratio": {
        "signal": "ru_skew_ratio",
        "label": "RU skew ratio",
        "aggregation": "peak",
        "period": "7d",
        "unit": "ratio",
        "threshold_key": "cosmos_hot_partition_skew_ratio",
        "pillar": "performance",
    },
    "ops_per_sec": {
        "signal": "operations_per_second",
        "label": "Operations per second",
        "aggregation": "avg",
        "period": "7d",
        "unit": "ops/s",
        "threshold_key": "redis_idle_ops_threshold",
        "pillar": "performance",
    },
    "server_load_pct": {
        "signal": "server_load_pct",
        "label": "Server load",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "threshold_key": "redis_server_load_low_pct",
        "pillar": "performance",
    },
    "cache_hit_rate_pct": {
        "signal": "cache_hit_rate_pct",
        "label": "Cache hit rate",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "threshold_key": "redis_hit_ratio_poor_pct",
        "pillar": "performance",
    },
    "evicted_keys": {
        "signal": "evicted_keys",
        "label": "Evicted keys",
        "aggregation": "sum",
        "period": "7d",
        "unit": "count",
        "pillar": "reliability",
    },
    "storage_pct": {
        "signal": "storage_utilization_pct",
        "label": "Storage utilization",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "threshold_key": "postgresql_storage_high_pct",
        "pillar": "performance",
    },
    "disk_iops_pct": {
        "signal": "disk_iops_utilization_pct",
        "label": "Disk IOPS consumed",
        "aggregation": "peak",
        "period": "7d",
        "unit": "%",
        "threshold_key": "postgresql_iops_pressure_pct",
        "pillar": "performance",
    },
    "active_connections": {
        "signal": "connection_count",
        "label": "Active connections",
        "aggregation": "peak",
        "period": "7d",
        "unit": "connections",
        "threshold_key": "postgresql_connection_risk_absolute",
        "pillar": "reliability",
    },
    "replication_lag_sec": {
        "signal": "replication_lag_seconds",
        "label": "Replication lag",
        "aggregation": "peak",
        "period": "7d",
        "unit": "seconds",
        "threshold_key": "postgresql_replication_lag_seconds",
        "pillar": "reliability",
    },
    "pull_count": {
        "signal": "image_pull_count",
        "label": "Image pull count",
        "aggregation": "sum",
        "period": "30d",
        "unit": "pulls",
        "threshold_key": "acr_pull_count_low",
        "pillar": "performance",
    },
    "storage_used_gb": {
        "signal": "registry_storage_gb",
        "label": "Registry storage used",
        "aggregation": "avg",
        "period": "7d",
        "unit": "GB",
        "threshold_key": "acr_storage_high_gb",
        "pillar": "cost",
    },
    "cu_utilization_pct": {
        "signal": "capacity_unit_utilization_pct",
        "label": "Capacity unit utilization",
        "aggregation": "avg",
        "period": "7d",
        "unit": "%",
        "threshold_key": "app_gateway_cu_saturation_pct",
        "pillar": "performance",
    },
    "used_pct": {
        "signal": "budget_utilization_pct",
        "label": "Budget utilization",
        "aggregation": "current",
        "period": "MTD",
        "unit": "%",
        "threshold_key": "budget_warn_pct",
        "pillar": "cost",
    },
    "risky_rule_count": {
        "signal": "risky_rule_count",
        "label": "Risky rule hits",
        "aggregation": "sum",
        "period": "7d",
        "unit": "hits",
        "pillar": "security",
    },
    "index_to_data_ratio": {
        "signal": "index_to_data_ratio",
        "label": "Index to data ratio",
        "aggregation": "avg",
        "period": "7d",
        "unit": "ratio",
        "threshold_key": "cosmos_index_to_data_ratio",
        "pillar": "cost",
    },
    "avg_item_bytes": {
        "signal": "avg_item_bytes",
        "label": "Average item size",
        "aggregation": "avg",
        "period": "7d",
        "unit": "bytes",
        "threshold_key": "cosmos_large_item_bytes",
        "pillar": "performance",
    },
    "monthly_cost_usd": {
        "signal": "monthly_cost_usd",
        "label": "Month-to-date cost",
        "aggregation": "sum",
        "period": "MTD",
        "unit": "USD",
        "threshold_key": "min_monthly_savings_usd",
        "pillar": "cost",
    },
}

INVENTORY_VALUE_KEYS = frozenset({
    "sku", "sku_name", "sku_tier", "tier", "state", "disk_state", "vm_size",
    "suggested_sku", "suggested_family", "sizing_action", "kubernetes_version",
    "supported_versions", "node_count", "pool_count", "system_pool_count",
    "environment", "pricing_model", "allocation", "has_vm", "has_lifecycle_policy",
    "alwaysOn", "app_count", "http_listener_count", "backend_pool_count",
    "subnet_count", "nic_count", "replication_count", "capacity", "size_gb",
    "storage_gb", "provisioning_state", "all_backends_empty", "missing_tags",
    "scale_set_priority", "api_type", "consistency_level", "ha_mode", "version",
    "backup_retention_days", "multi_write_enabled", "automatic_failover_enabled",
    "free_tier_enabled", "persistence_enabled", "shard_count", "record_set_count",
    "endpoint_count", "ddos_protection", "plan_sku", "database_count", "license_type",
    "enableSoftDelete", "enablePurgeProtection", "public_ip_count", "throughput_gbps",
    "arm_resource_type", "azure_service_name", "resource_group", "location",
})

# Manual overrides per rule (measured signals only)
RULE_OVERRIDES: dict[str, list[str]] = {
    "DISK_UNATTACHED": ["age_days"],
    "DISK_UNUSED_EXTENDED": ["disk_read_bps", "disk_write_bps", "age_days"],
    "SNAPSHOT_OLD": ["age_days"],
    "SNAPSHOT_RETENTION_EXTENDED": ["age_days", "monthly_cost_usd"],
    "VM_NO_RESERVED": ["uptime_hours", "power_state"],
    "VM_COMMITMENT_CANDIDATE": ["uptime_hours", "monthly_cost_usd"],
    "SPOT_OPPORTUNITY": ["cpu_pct", "uptime_hours"],
    "LOAD_BALANCER_IDLE_EXTENDED": ["byte_count", "healthy_host_count"],
    "LOAD_BALANCER_BACKEND_CONSOLIDATION": ["byte_count"],
    "PUBLIC_IP_IDLE_EXTENDED": ["byte_count", "packet_count"],
    "NAT_GATEWAY_IDLE_EXTENDED": ["byte_count", "snat_connection_count"],
    "APP_GATEWAY_IDLE_EXTENDED": ["throughput_bytes", "request_count"],
    "STORAGE_HOT_UNUSED": ["transaction_count", "used_capacity_bytes"],
    "STORAGE_HOT_UNUSED_EXTENDED": ["transaction_count", "used_capacity_bytes"],
    "STORAGE_NO_LIFECYCLE": ["transaction_count"],
    "STORAGE_LIFECYCLE_EXTENDED": ["transaction_count", "used_capacity_bytes"],
    "STORAGE_COOL_TIER_CANDIDATE_EXTENDED": ["transaction_count"],
    "SQL_IDLE": ["dtu_pct"],
    "SQL_SERVERLESS_EXTENDED": ["cpu_pct"],
    "COSMOS_AUTOSCALE_EXTENDED": ["normalized_ru_pct", "total_ru"],
    "COSMOS_SERVERLESS": ["total_ru"],
    "POSTGRESQL_LOW_COMPUTE_UTILIZATION": ["cpu_pct", "memory_pct"],
    "POSTGRESQL_HIGH_COMPUTE_DEMAND": ["cpu_pct"],
    "POSTGRESQL_MEMORY_PRESSURE": ["memory_pct"],
    "POSTGRESQL_STORAGE_EXPANSION": ["storage_pct"],
    "POSTGRESQL_IOPS_PRESSURE": ["disk_iops_pct"],
    "POSTGRESQL_CONNECTION_POOL_RISK": ["active_connections"],
    "POSTGRESQL_READ_REPLICA_ANALYSIS": ["replication_lag_sec"],
    "REDIS_IDLE_DETECTION": ["ops_per_sec"],
    "REDIS_MEMORY_PRESSURE": ["memory_pct", "evicted_keys"],
    "REDIS_LOW_UTILIZATION": ["memory_pct", "server_load_pct"],
    "REDIS_HIT_RATIO_POOR": ["cache_hit_rate_pct"],
    "KEYVAULT_IDLE_EXTENDED": ["api_hits"],
    "KEYVAULT_HIGH_OPS_EXTENDED": ["api_hits"],
    "BUDGET_WARNING": ["used_pct"],
    "BUDGET_CRITICAL": ["used_pct"],
    "BUDGET_GUARDRAIL_EXTENDED": ["used_pct"],
    "AKS_DEV_RUNNING_NIGHTS": ["cluster_cpu_pct"],
    "AKS_POD_DENSITY_EXTENDED": ["cluster_cpu_pct", "cluster_mem_pct"],
    "AKS_NODE_MEMORY_PRESSURE_EXTENDED": ["cluster_mem_pct"],
    "VM_MEMORY_PRESSURE_EXTENDED": ["memory_pct"],
    "VM_EGRESS_HIGH_EXTENDED": ["byte_count"],
    "VM_DISK_BOTTLENECK": ["disk_iops_utilization_pct", "disk_throughput_utilization_pct"],
    "VM_NETWORK_BOTTLENECK": ["byte_count"],
    "VMSS_AUTOSCALE_TUNING_EXTENDED": ["cpu_pct"],
    "VMSS_NO_AUTOSCALE_EXTENDED": ["cpu_pct"],
    "NSG_PERMISSIVE_EXTENDED": ["risky_rule_count"],
    "NSG_FLOW_LOG_COST": ["byte_count"],
    "APP_GATEWAY_CU_SATURATION": ["cu_utilization_pct"],
    "APP_GATEWAY_CU_RIGHTSIZE_DOWN": ["cu_utilization_pct"],
    "ACR_PREMIUM_EXTENDED": ["pull_count", "storage_used_gb"],
    "ACR_STANDARD_EXTENDED": ["pull_count", "storage_used_gb"],
    "ACR_STORAGE_HIGH_EXTENDED": ["storage_used_gb", "pull_count"],
    "ACR_RETENTION_DISABLED_EXTENDED": ["storage_used_gb"],
    "PLAN_UNDERUTILIZED": ["cpu_pct", "memory_pct"],
    "APP_IDLE": ["request_count"],
    "WEBAPP_PLAN_LOAD_LOW_EXTENDED": ["cpu_pct", "memory_pct"],
    "COST_SPIKE_DETECTED": ["monthly_cost_usd"],
    "DISK_OVERSIZE": ["disk_read_bps", "disk_write_bps", "disk_iops_utilization_pct"],
    "DISK_OVERSIZE_EXTENDED": ["disk_read_bps", "disk_write_bps", "disk_iops_utilization_pct"],
    "DISK_UNDERPROVISIONED": ["disk_iops_utilization_pct", "disk_throughput_utilization_pct", "provisioned_iops"],
    "DISK_CAPACITY_RIGHTSIZE_EXTENDED": ["disk_iops_utilization_pct", "disk_throughput_utilization_pct"],
    "DISK_QUEUE_DEPTH_EXTENDED": ["disk_iops_utilization_pct"],
    "DISK_PREMIUM_DOWNGRADE_HDD": ["disk_read_bps", "disk_write_bps", "disk_iops_utilization_pct"],
    "DISK_SSD_DOWNGRADE_HDD": ["disk_read_bps", "disk_write_bps", "disk_iops_utilization_pct"],
    "DISK_ULTRA_DOWNGRADE_PREMIUM": ["disk_iops_utilization_pct", "disk_throughput_utilization_pct"],
    "DISK_ULTRA_DOWNGRADE_SSD": ["disk_iops_utilization_pct", "disk_throughput_utilization_pct"],
    "VM_RIGHTSIZE_FAMILY": ["cpu_pct", "memory_pct"],
    "VM_UNDERUTILIZED_EXTENDED": ["cpu_pct", "memory_pct"],
    "VM_ZOMBIE_CANDIDATE_EXTENDED": ["cpu_pct", "uptime_hours"],
    "VM_SCHEDULE_CANDIDATE_EXTENDED": ["cpu_pct", "uptime_hours"],
    "VM_STOPPED_DEALLOCATED": ["power_state"],
    "AKS_IDLE_POOL_EXTENDED": ["cluster_cpu_pct", "cluster_mem_pct", "idle_nodes", "idle_node_ratio"],
    "AKS_NODE_IDLE": ["cluster_cpu_pct", "cluster_mem_pct", "idle_nodes"],
    "AKS_OVERPROVISIONED": ["cluster_cpu_pct", "cluster_mem_pct", "idle_nodes"],
    "AKS_NO_SPOT_EXTENDED": ["cluster_cpu_pct"],
    "AKS_DEV_RUNNING_NIGHTS": ["cluster_cpu_pct", "cluster_mem_pct"],
    "AKS_UNDERUTILIZED": ["cluster_cpu_pct", "cluster_mem_pct", "idle_node_ratio"],
    "AKS_EMPTY_POOL": ["idle_nodes"],
    "AKS_SINGLE_NODE_POOL": ["cluster_cpu_pct", "cluster_mem_pct"],
    "AKS_SINGLE_NODE_POOL_EXTENDED": ["cluster_cpu_pct", "cluster_mem_pct"],
    "AKS_SYSTEM_POOL_RELIABILITY": ["cluster_cpu_pct", "cluster_mem_pct"],
    "AKS_POOL_CONSOLIDATION": ["cluster_cpu_pct", "cluster_mem_pct", "idle_node_ratio"],
    "IP_UNASSOCIATED": ["byte_count", "packet_count"],
    "NAT_GATEWAY_IDLE": ["byte_count", "snat_connection_count"],
    "LB_NO_BACKEND": ["byte_count", "healthy_host_count"],
    "LOAD_BALANCER_THROUGHPUT_RIGHTSIZE": ["byte_count"],
    "LOAD_BALANCER_SNAT_PRESSURE": ["snat_port_usage_pct"],
    "APPGW_UNUSED": ["throughput_bytes", "request_count"],
    "SQL_NO_SERVERLESS": ["dtu_pct", "cpu_pct"],
    "SQL_IDLE_EXTENDED": ["dtu_pct"],
    "SQL_ELASTIC_POOL_CANDIDATE": ["dtu_pct"],
    "COSMOS_PROVISIONED": ["normalized_ru_pct", "total_ru"],
    "COSMOS_PROVISIONED_EXTENDED": ["normalized_ru_pct", "total_ru"],
    "COSMOS_RU_RIGHT_SIZING_UNDER": ["normalized_ru_pct"],
    "COSMOS_RU_RIGHT_SIZING_OVER": ["normalized_ru_pct"],
    "COSMOS_THROTTLING_DETECTED": ["normalized_ru_peak_pct"],
    "COSMOS_HOT_CONTAINER_DETECTED": ["ru_skew_ratio", "normalized_ru_peak_pct"],
    "COSMOS_LARGE_ITEMS_DETECTED": ["avg_item_bytes"],
    "COSMOS_INDEXING_OVERPROVISIONED": ["index_to_data_ratio"],
    "COSMOS_FREE_TIER_SUBOPTIMAL": ["total_ru", "normalized_ru_pct"],
    "COSMOS_RESERVED_CAPACITY_ELIGIBLE": ["normalized_ru_pct"],
    "REDIS_FAILED": ["ops_per_sec", "memory_pct"],
    "REDIS_OVERSIZED": ["memory_pct", "ops_per_sec"],
    "REDIS_RIGHTSIZE_EXTENDED": ["memory_pct", "ops_per_sec"],
    "REDIS_CLUSTER_UNNECESSARY": ["ops_per_sec"],
    "REDIS_TIER_REVIEW": ["memory_pct", "ops_per_sec"],
    "REDIS_HEALTH_EXTENDED": ["ops_per_sec", "memory_pct"],
    "POSTGRESQL_BURSTABLE_EXTENDED": ["cpu_pct", "memory_pct"],
    "POSTGRESQL_STORAGE_EXTENDED": ["storage_pct"],
    "POSTGRESQL_STOPPED_EXTENDED": ["cpu_pct"],
    "PLAN_UNDERUTILIZED": ["cpu_pct", "memory_pct"],
    "ASP_OVERPROVISIONED": ["cpu_pct", "request_count"],
    "ASP_EMPTY": ["request_count"],
    "APP_SERVICE_PLAN_EXTENDED": ["cpu_pct", "request_count"],
    "WEBAPP_STOPPED_EXTENDED": ["request_count"],
    "WEBAPP_ALWAYS_ON_EXTENDED": ["request_count"],
    "APP_ALWAYS_ON_OFF": ["request_count"],
    "ASP_CONSOLIDATION_CANDIDATE_EXTENDED": ["cpu_pct", "request_count"],
    "KEYVAULT_PREMIUM_EXTENDED": ["api_hits"],
    "KEYVAULT_PROTECTION_EXTENDED": ["api_hits"],
    "STORAGE_EGRESS_HIGH_EXTENDED": ["egress_bytes"],
    "STORAGE_REDUNDANCY_EXTENDED": ["egress_bytes", "transaction_count"],
    "STORAGE_LRS_CRITICAL": ["transaction_count", "used_capacity_bytes"],
    "STORAGE_LRS_CRITICAL_EXTENDED": ["transaction_count", "used_capacity_bytes"],
    "NSG_FLOW_LOG_COST": ["byte_count"],
    "NAT_GATEWAY_SNAT_EXHAUSTION": ["snat_utilization_pct"],
    "NAT_GATEWAY_SUBNET_CONSOLIDATION": ["byte_count", "snat_connection_count"],
    "ACR_GEO_REPLICATION_EXTENDED": ["pull_count", "storage_used_gb"],
    "ACR_IMAGE_RETENTION_EXTENDED": ["storage_used_gb", "pull_count"],
    "SNAPSHOT_ARCHIVE_EXTENDED": ["age_days"],
    "VMSS_NONPROD_SCHEDULING_EXTENDED": ["cpu_pct", "uptime_hours"],
    "RESERVED_OPPORTUNITY": ["uptime_hours", "monthly_cost_usd"],
    "RESERVED_OPPORTUNITY_EXTENDED": ["uptime_hours", "monthly_cost_usd"],
    "SAVINGS_PLAN_OPPORTUNITY": ["monthly_cost_usd", "uptime_hours"],
    "SAVINGS_PLAN_OPPORTUNITY_EXTENDED": ["monthly_cost_usd"],
    "NETWORK_FRONT_DOOR_IDLE_EXTENDED": ["request_count", "byte_count"],
    "NETWORK_FRONT_DOOR_COST_EXTENDED": ["monthly_cost_usd", "request_count"],
    "CDN_EGRESS_EXTENDED": ["egress_bytes", "byte_count"],
    "CDN_EGRESS": ["egress_bytes"],
    "FIREWALL_FIXED_COST_EXTENDED": ["byte_count"],
    "FIREWALL_FIXED_COST": ["byte_count"],
    "LOG_ANALYTICS_INGESTION": ["monthly_cost_usd"],
    "LOG_ANALYTICS_INGESTION_EXTENDED": ["monthly_cost_usd"],
    "LOG_ANALYTICS_RETENTION_EXTENDED": ["monthly_cost_usd"],
    "APP_INSIGHTS_SAMPLING": ["request_count", "monthly_cost_usd"],
    "APP_INSIGHTS_SAMPLING_EXTENDED": ["request_count", "monthly_cost_usd"],
    "APP_INSIGHTS_LOW_TRAFFIC_EXTENDED": ["request_count"],
    "APIM_SKU_EXTENDED": ["request_count", "monthly_cost_usd"],
    "APIM_LOW_TRAFFIC_EXTENDED": ["request_count"],
    "API_MANAGEMENT_SKU": ["request_count", "monthly_cost_usd"],
    "DATA_FACTORY_PIPELINE": ["monthly_cost_usd"],
    "DATA_FACTORY_IR_EXTENDED": ["monthly_cost_usd"],
    "DATA_FACTORY_IDLE_PIPELINES_EXTENDED": ["monthly_cost_usd"],
    "LOGIC_APP_RUN_HISTORY": ["request_count", "monthly_cost_usd"],
    "LOGIC_APP_PLAN_EXTENDED": ["request_count", "monthly_cost_usd"],
    "LOGIC_APP_LOW_RUNS_EXTENDED": ["request_count"],
    "EVENT_HUBS_TIER": ["monthly_cost_usd", "byte_count"],
    "EVENT_HUBS_TIER_EXTENDED": ["monthly_cost_usd", "byte_count"],
    "EVENT_HUBS_LOW_THROUGHPUT_EXTENDED": ["byte_count"],
    "SERVICE_BUS_TIER": ["monthly_cost_usd", "byte_count"],
    "SERVICE_BUS_TIER_EXTENDED": ["monthly_cost_usd"],
    "SERVICE_BUS_IDLE_NAMESPACE_EXTENDED": ["byte_count"],
    "DATABRICKS_CLUSTER": ["monthly_cost_usd"],
    "DATABRICKS_CLUSTER_EXTENDED": ["monthly_cost_usd"],
    "DATABRICKS_DEV_WORKSPACE_EXTENDED": ["monthly_cost_usd"],
    "SYNAPSE_PAUSE": ["monthly_cost_usd"],
    "SYNAPSE_PAUSE_EXTENDED": ["monthly_cost_usd"],
    "SYNAPSE_SQL_IDLE_EXTENDED": ["cpu_pct"],
    "ADX_INGESTION": ["monthly_cost_usd", "byte_count"],
    "ADX_INGESTION_EXTENDED": ["monthly_cost_usd", "byte_count"],
    "ADX_LOW_INGESTION_EXTENDED": ["byte_count"],
    "ML_WORKSPACE_COMPUTE": ["monthly_cost_usd"],
    "ML_WORKSPACE_COMPUTE_EXTENDED": ["monthly_cost_usd"],
    "ML_WORKSPACE_IDLE_EXTENDED": ["monthly_cost_usd"],
    "BACKUP_RETENTION": ["monthly_cost_usd"],
    "BACKUP_RETENTION_EXTENDED": ["monthly_cost_usd"],
    "BACKUP_VAULT_GROWTH_EXTENDED": ["monthly_cost_usd"],
    "COGNITIVE_SEARCH_SKU": ["monthly_cost_usd", "request_count"],
    "COGNITIVE_SEARCH_SKU_EXTENDED": ["monthly_cost_usd", "request_count"],
    "COGNITIVE_SEARCH_REPLICA_EXTENDED": ["request_count"],
    "PRIVATE_ENDPOINT_UNDERUTILIZED": ["byte_count"],
    "PRIVATE_ENDPOINT_COST": ["monthly_cost_usd", "byte_count"],
    "PRIVATE_LINK_COST": ["monthly_cost_usd"],
    "IDLE_APP_SERVICE_PLANS": ["monthly_cost_usd", "request_count"],
    "IDLE_DB_FLEXIBLE_SERVER": ["cpu_pct", "monthly_cost_usd"],
    "UNUSED_NIC": ["monthly_cost_usd"],
    "IDLE_NAT_GATEWAY": ["byte_count", "monthly_cost_usd"],
    "BANDWIDTH_REVIEW": ["byte_count", "egress_bytes"],
    "COST_EXPORT_ONLY_RESOURCE": ["monthly_cost_usd"],
    "UNCLASSIFIED_SERVICE_SPEND": ["monthly_cost_usd"],
}

# Default measured evidence for cost-export engine rules without explicit override
COST_EXPORT_DEFAULT = ["monthly_cost_usd"]

# canonical type → rules in that service JSON
CANONICAL_RULES: dict[str, list[str]] = {
    "compute/vm": [
        "VM_IDLE", "VM_OVERSIZE", "VM_NO_RESERVED", "VM_STOPPED_DEALLOCATED",
        "VM_UNDERUTILIZED_EXTENDED", "VM_RIGHTSIZE_FAMILY", "VM_SKU_SIZING_EXTENDED",
        "VM_COMMITMENT_CANDIDATE", "VM_MISSING_GOVERNANCE_TAGS", "VM_STOPPED_BILLING_EXTENDED",
        "VM_DISK_BOTTLENECK", "VM_NETWORK_BOTTLENECK", "VM_MEMORY_PRESSURE_EXTENDED",
        "VM_EGRESS_HIGH_EXTENDED", "VM_SCHEDULE_CANDIDATE_EXTENDED", "VM_ZOMBIE_CANDIDATE_EXTENDED",
        "SPOT_OPPORTUNITY", "RESERVED_OPPORTUNITY", "SAVINGS_PLAN_OPPORTUNITY",
    ],
    "compute/vmss": [
        "VMSS_NO_AUTOSCALE_EXTENDED", "VMSS_NONPROD_SCHEDULING_EXTENDED",
        "VMSS_AUTOSCALE_TUNING_EXTENDED", "VM_IDLE", "VM_OVERSIZE", "VM_SKU_SIZING_EXTENDED",
    ],
    "compute/disk": [
        "DISK_UNATTACHED", "DISK_OVERSIZE", "DISK_UNUSED_EXTENDED", "DISK_OVERSIZE_EXTENDED",
        "DISK_UNDERPROVISIONED", "DISK_CAPACITY_RIGHTSIZE_EXTENDED", "DISK_QUEUE_DEPTH_EXTENDED",
        "DISK_NEW_GRACE_PERIOD", "DISK_ULTRA_DOWNGRADE_PREMIUM", "DISK_ULTRA_DOWNGRADE_SSD",
        "DISK_PREMIUM_DOWNGRADE_HDD", "DISK_SSD_DOWNGRADE_HDD",
    ],
    "compute/snapshot": ["SNAPSHOT_OLD", "SNAPSHOT_RETENTION_EXTENDED", "SNAPSHOT_ARCHIVE_EXTENDED"],
    "containers/aks": [
        "AKS_NODE_IDLE", "AKS_OVERPROVISIONED", "AKS_DEV_RUNNING_NIGHTS", "AKS_NO_SPOT",
        "AKS_OLD_VERSION", "AKS_NO_AUTOSCALER", "AKS_SINGLE_NODE_POOL", "AKS_EMPTY_POOL",
        "AKS_IDLE_POOL_EXTENDED", "AKS_NONPROD_SCHEDULING", "AKS_SYSTEM_POOL_RELIABILITY",
        "AKS_UNDERUTILIZED", "AKS_OLD_VERSION_EXTENDED", "AKS_NO_AUTOSCALER_EXTENDED",
        "AKS_NO_SPOT_EXTENDED", "AKS_SINGLE_NODE_POOL_EXTENDED", "AKS_POOL_CONSOLIDATION",
        "AKS_NODE_MEMORY_PRESSURE_EXTENDED", "AKS_POD_DENSITY_EXTENDED",
    ],
    "containers/acr": [
        "ACR_PREMIUM_EXTENDED", "ACR_STANDARD_EXTENDED", "ACR_GEO_REPLICATION_EXTENDED",
        "ACR_STORAGE_HIGH_EXTENDED", "ACR_RETENTION_DISABLED_EXTENDED", "ACR_IMAGE_RETENTION_EXTENDED",
    ],
    "storage/account": [
        "STORAGE_HOT_UNUSED", "STORAGE_NO_LIFECYCLE", "STORAGE_LRS_CRITICAL",
        "STORAGE_LIFECYCLE_EXTENDED", "STORAGE_REDUNDANCY_EXTENDED",
        "STORAGE_HOT_UNUSED_EXTENDED", "STORAGE_LRS_CRITICAL_EXTENDED",
        "STORAGE_EGRESS_HIGH_EXTENDED", "STORAGE_COOL_TIER_CANDIDATE_EXTENDED",
    ],
    "network/publicip": [
        "IP_UNASSOCIATED", "PUBLIC_IP_IDLE_EXTENDED", "PUBLIC_IP_BASIC_SKU_MIGRATION",
    ],
    "network/nic": ["NIC_UNATTACHED", "NIC_ORPHANED_EXTENDED"],
    "network/nat": [
        "NAT_GATEWAY_IDLE", "NAT_GATEWAY_IDLE_EXTENDED", "NAT_GATEWAY_SNAT_EXHAUSTION",
        "NAT_GATEWAY_SKU_V2_UPGRADE", "NAT_GATEWAY_SUBNET_CONSOLIDATION",
    ],
    "network/loadbalancer": [
        "LB_NO_BACKEND", "LOAD_BALANCER_IDLE_EXTENDED", "LOAD_BALANCER_SNAT_PRESSURE",
        "LOAD_BALANCER_THROUGHPUT_RIGHTSIZE", "LOAD_BALANCER_BACKEND_CONSOLIDATION",
        "LOAD_BALANCER_BASIC_SKU_MIGRATION",
    ],
    "network/appgateway": [
        "APPGW_UNUSED", "APP_GATEWAY_IDLE_EXTENDED", "APP_GATEWAY_CU_SATURATION",
        "APP_GATEWAY_CU_RIGHTSIZE_DOWN",
    ],
    "network/nsg": ["NSG_ORPHANED_EXTENDED", "NSG_PERMISSIVE_EXTENDED", "NSG_FLOW_LOG_COST"],
    "database/sql": [
        "SQL_IDLE", "SQL_NO_SERVERLESS", "SQL_IDLE_EXTENDED", "SQL_SERVERLESS_EXTENDED",
        "SQL_ELASTIC_POOL_CANDIDATE", "SQL_HYBRID_BENEFIT_CANDIDATE", "SQL_QUERY_PERF_REVIEW",
    ],
    "database/cosmosdb": [
        "COSMOS_PROVISIONED", "COSMOS_SERVERLESS", "COSMOS_AUTOSCALE_EXTENDED",
        "COSMOS_PROVISIONED_EXTENDED", "COSMOS_RU_RIGHT_SIZING_UNDER", "COSMOS_RU_RIGHT_SIZING_OVER",
        "COSMOS_THROTTLING_DETECTED", "COSMOS_HOT_CONTAINER_DETECTED", "COSMOS_API_COST_VARIANCE",
        "COSMOS_CONSISTENCY_OVERPROVISIONED", "COSMOS_LARGE_ITEMS_DETECTED",
        "COSMOS_INDEXING_OVERPROVISIONED", "COSMOS_MULTI_WRITE_UNNECESSARY",
        "COSMOS_FAILOVER_UNNECESSARY", "COSMOS_FREE_TIER_SUBOPTIMAL", "COSMOS_RESERVED_CAPACITY_ELIGIBLE",
    ],
    "database/postgresql": [
        "POSTGRESQL_STOPPED_EXTENDED", "POSTGRESQL_BURSTABLE_EXTENDED", "POSTGRESQL_STORAGE_EXTENDED",
        "POSTGRESQL_LOW_COMPUTE_UTILIZATION", "POSTGRESQL_HIGH_COMPUTE_DEMAND", "POSTGRESQL_MEMORY_PRESSURE",
        "POSTGRESQL_STORAGE_EXPANSION", "POSTGRESQL_IOPS_PRESSURE", "POSTGRESQL_CONNECTION_POOL_RISK",
        "POSTGRESQL_HA_UNNECESSARY", "POSTGRESQL_HA_REQUIRED", "POSTGRESQL_READ_REPLICA_ANALYSIS",
        "POSTGRESQL_VERSION_OUTDATED", "POSTGRESQL_BACKUP_RETENTION_REVIEW",
    ],
    "database/redis": [
        "REDIS_FAILED", "REDIS_OVERSIZED", "REDIS_TIER_REVIEW", "REDIS_HEALTH_EXTENDED",
        "REDIS_RIGHTSIZE_EXTENDED", "REDIS_IDLE_DETECTION", "REDIS_MEMORY_PRESSURE",
        "REDIS_LOW_UTILIZATION", "REDIS_HIT_RATIO_POOR", "REDIS_CLUSTER_UNNECESSARY",
        "REDIS_PERSISTENCE_REVIEW",
    ],
    "appservice/webapp": [
        "APP_IDLE", "WEBAPP_STOPPED_EXTENDED", "WEBAPP_ALWAYS_ON_EXTENDED", "APP_ALWAYS_ON_OFF",
    ],
    "appservice/plan": [
        "ASP_EMPTY", "ASP_OVERPROVISIONED", "PLAN_EMPTY", "PLAN_UNDERUTILIZED",
        "APP_SERVICE_PLAN_EXTENDED", "WEBAPP_PLAN_LOAD_LOW_EXTENDED", "ASP_CONSOLIDATION_CANDIDATE_EXTENDED",
    ],
    "security/keyvault": [
        "KEYVAULT_SOFT_DELETE_OFF", "KEYVAULT_PROTECTION_EXTENDED", "KEYVAULT_IDLE_EXTENDED",
        "KEYVAULT_PREMIUM_EXTENDED", "KEYVAULT_HIGH_OPS_EXTENDED",
    ],
    "monitoring/loganalytics": ["LOG_ANALYTICS_RETENTION_EXTENDED", "LOG_ANALYTICS_INGESTION"],
    "monitoring/appinsights": ["APP_INSIGHTS_SAMPLING_EXTENDED", "APP_INSIGHTS_SAMPLING", "APP_INSIGHTS_LOW_TRAFFIC_EXTENDED"],
    "integration/apim": ["APIM_SKU_EXTENDED", "APIM_LOW_TRAFFIC_EXTENDED", "API_MANAGEMENT_SKU"],
    "integration/datafactory": ["DATA_FACTORY_IR_EXTENDED", "DATA_FACTORY_PIPELINE", "DATA_FACTORY_IDLE_PIPELINES_EXTENDED"],
    "integration/logicapp": ["LOGIC_APP_PLAN_EXTENDED", "LOGIC_APP_RUN_HISTORY", "LOGIC_APP_LOW_RUNS_EXTENDED"],
    "messaging/eventhub": ["EVENT_HUBS_TIER_EXTENDED", "EVENT_HUBS_TIER", "EVENT_HUBS_LOW_THROUGHPUT_EXTENDED"],
    "messaging/servicebus": ["SERVICE_BUS_TIER_EXTENDED", "SERVICE_BUS_TIER", "SERVICE_BUS_IDLE_NAMESPACE_EXTENDED"],
    "analytics/databricks": ["DATABRICKS_CLUSTER_EXTENDED", "DATABRICKS_CLUSTER", "DATABRICKS_DEV_WORKSPACE_EXTENDED"],
    "analytics/synapse": ["SYNAPSE_PAUSE_EXTENDED", "SYNAPSE_PAUSE", "SYNAPSE_SQL_IDLE_EXTENDED"],
    "analytics/adx": ["ADX_INGESTION_EXTENDED", "ADX_INGESTION", "ADX_LOW_INGESTION_EXTENDED"],
    "analytics/mlworkspace": ["ML_WORKSPACE_COMPUTE_EXTENDED", "ML_WORKSPACE_COMPUTE", "ML_WORKSPACE_IDLE_EXTENDED"],
    "backup/recoveryvault": ["BACKUP_RETENTION_EXTENDED", "BACKUP_RETENTION", "BACKUP_VAULT_GROWTH_EXTENDED"],
    "search/cognitivesearch": ["COGNITIVE_SEARCH_SKU_EXTENDED", "COGNITIVE_SEARCH_SKU", "COGNITIVE_SEARCH_REPLICA_EXTENDED"],
    "network/frontdoor": ["NETWORK_FRONT_DOOR_REVIEW", "NETWORK_FRONT_DOOR_IDLE_EXTENDED", "NETWORK_FRONT_DOOR_COST_EXTENDED"],
    "network/firewall": ["FIREWALL_FIXED_COST_EXTENDED", "FIREWALL_FIXED_COST"],
    "network/cdn": ["CDN_EGRESS_EXTENDED", "CDN_EGRESS"],
    "network/privatedns": ["PRIVATE_DNS_EMPTY_EXTENDED", "PRIVATE_DNS_UNUSED_ZONE"],
    "governance": ["GOVERNANCE_TAG_ENFORCEMENT", "BUDGET_WARNING", "BUDGET_CRITICAL", "BUDGET_GUARDRAIL_EXTENDED"],
    "cost_anomalies": ["COST_SPIKE_DETECTED"],
}

CANONICAL_JSON_PATH: dict[str, Path] = {
    "compute/vm": ROOT / "data" / "vm-assessment.json",
    "compute/vmss": ROOT / "data" / "vmss-assessment.json",
    "compute/disk": ROOT / "data" / "disk-assessment.json",
    "compute/snapshot": ROOT / "data" / "snapshot_metrics_thresholds.json",
    "containers/aks": ROOT / "data" / "aks_cluster_metrics_thresholds.json",
    "containers/acr": ROOT / "data" / "acr_metrics_thresholds.json",
    "storage/account": ROOT / "data" / "storage_account_metrics_thresholds.json",
    "network/publicip": ROOT / "data" / "public_ip_metrics_thresholds.json",
    "network/nic": ROOT / "data" / "nic_metrics_thresholds.json",
    "network/nat": ROOT / "data" / "nat_gateway_metrics_thresholds.json",
    "network/loadbalancer": ROOT / "data" / "load_balancer_metrics_thresholds.json",
    "network/appgateway": ROOT / "data" / "app_gateway_metrics_thresholds.json",
    "network/nsg": ROOT / "data" / "nsg_metrics_thresholds.json",
    "database/sql": ROOT / "data" / "sql_database_metrics_thresholds.json",
    "database/cosmosdb": ROOT / "data" / "cosmosdb-assessment.json",
    "database/postgresql": ROOT / "data" / "postgresql_metrics_thresholds.json",
    "database/redis": ROOT / "data" / "redis_metrics_thresholds.json",
    "appservice/webapp": ROOT / "data" / "app_service_metrics_thresholds.json",
    "appservice/plan": ROOT / "data" / "app_service_metrics_thresholds.json",
    "security/keyvault": ROOT / "data" / "recoveryvault_metrics_thresholds.json",
    "monitoring/loganalytics": ROOT / "data" / "loganalytics_metrics_thresholds.json",
    "monitoring/appinsights": ROOT / "data" / "appinsights_metrics_thresholds.json",
    "integration/apim": ROOT / "data" / "apim_metrics_thresholds.json",
    "integration/datafactory": ROOT / "data" / "datafactory_metrics_thresholds.json",
    "integration/logicapp": ROOT / "data" / "logicapp_metrics_thresholds.json",
    "messaging/eventhub": ROOT / "data" / "eventhub_metrics_thresholds.json",
    "messaging/servicebus": ROOT / "data" / "servicebus_metrics_thresholds.json",
    "analytics/databricks": ROOT / "data" / "databricks_metrics_thresholds.json",
    "analytics/synapse": ROOT / "data" / "synapse_metrics_thresholds.json",
    "analytics/adx": ROOT / "data" / "adx_metrics_thresholds.json",
    "analytics/mlworkspace": ROOT / "data" / "mlworkspace_metrics_thresholds.json",
    "backup/recoveryvault": ROOT / "data" / "recoveryvault_metrics_thresholds.json",
    "search/cognitivesearch": ROOT / "data" / "cognitivesearch_metrics_thresholds.json",
    "network/frontdoor": ROOT / "data" / "frontdoor_metrics_thresholds.json",
    "governance": ROOT / "data" / "governance_metrics_thresholds.json",
    "cost_anomalies": ROOT / "data" / "cost_anomaly_metrics_thresholds.json",
}


def _evidence_from_value_keys(value_keys: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in value_keys:
        if key in INVENTORY_VALUE_KEYS:
            continue
        tmpl = SIGNAL_TEMPLATES.get(key)
        if not tmpl:
            continue
        sig = tmpl["signal"]
        if sig in seen:
            continue
        seen.add(sig)
        out.append(dict(tmpl))
    return out


def build_rule_contract(rule_id: str, *, engine: str = "") -> dict[str, Any]:
    from app.rule_evidence_specs import RULE_EVIDENCE_SPECS

    override_keys = RULE_OVERRIDES.get(rule_id)
    if override_keys is not None:
        evidence = _evidence_from_value_keys(override_keys)
    else:
        spec = RULE_EVIDENCE_SPECS.get(rule_id)
        value_keys: list[str] = []
        if spec:
            value_keys = [s.value_key for s in spec.signals]
        evidence = _evidence_from_value_keys(value_keys)
        if not evidence and engine == "cost_export":
            evidence = _evidence_from_value_keys(COST_EXPORT_DEFAULT)

    return {
        "required_evidence": evidence,
        "exclude_inventory_facts": True,
    }


def main() -> None:
    from app.optimizer.rule_catalog import RULE_MANIFEST

    all_rules: dict[str, dict[str, Any]] = {}
    for rid, meta in RULE_MANIFEST.items():
        all_rules[rid] = build_rule_contract(rid, engine=str(meta.get("engine") or ""))

    # Merge aliases
    from app.optimizer.rule_catalog import RULE_ALIASES
    for alias, canonical in RULE_ALIASES.items():
        if canonical in all_rules and alias not in all_rules:
            all_rules[alias] = all_rules[canonical]

    # Group by JSON file
    file_rules: dict[Path, dict[str, Any]] = {}
    for ctype, rules in CANONICAL_RULES.items():
        path = CANONICAL_JSON_PATH.get(ctype)
        if not path:
            continue
        bucket = file_rules.setdefault(path, {})
        for rid in rules:
            if rid in all_rules:
                bucket[rid] = all_rules[rid]

    # Write / merge into JSON files
    modified: list[str] = []
    for path, rules in file_rules.items():
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = {
                "schema_version": 1,
                "service": path.stem.replace("_metrics_thresholds", "").replace("_", " ").title(),
                "optimization_thresholds": {"evaluation_window_days": 7, "min_monthly_savings_usd": 5.0},
            }
        existing = data.get("analysis_rules") or {}
        existing.update(rules)
        data["analysis_rules"] = existing
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        modified.append(str(path.relative_to(ROOT)))

    # Master contracts file
    master_path = ROOT / "data" / "rule_evidence_contracts.json"
    master_path.write_text(
        json.dumps({"schema_version": 1, "analysis_rules": all_rules}, indent=2) + "\n",
        encoding="utf-8",
    )
    modified.append(str(master_path.relative_to(ROOT)))

    with_evidence = sum(1 for c in all_rules.values() if c.get("required_evidence"))
    print(f"Rules with required_evidence: {with_evidence}/{len(all_rules)}")
    print(f"Modified {len(modified)} JSON files:")
    for p in sorted(modified):
        print(f"  - {p}")


if __name__ == "__main__":
    main()

"""Azure SKU defaults per canonical resource type (Microsoft docs + retail baselines)."""

from __future__ import annotations

from typing import Any

# Values sourced from Azure product documentation and retail pricing pages.
AZURE_SKU_DEFAULTS: dict[str, dict[str, Any]] = {
    "compute/vm": {
        "skus": {
            "Standard_B1s": {"family": "B", "vcpus": 1, "memory_gb": 1, "burstable": True},
            "Standard_B2s": {"family": "B", "vcpus": 2, "memory_gb": 4, "burstable": True},
            "Standard_D2s_v3": {"family": "Dsv3", "vcpus": 2, "memory_gb": 8},
            "Standard_D4s_v3": {"family": "Dsv3", "vcpus": 4, "memory_gb": 16},
            "Standard_D8s_v3": {"family": "Dsv3", "vcpus": 8, "memory_gb": 32},
            "Standard_E2s_v3": {"family": "Esv3", "vcpus": 2, "memory_gb": 16},
            "Standard_F2s_v2": {"family": "Fsv2", "vcpus": 2, "memory_gb": 4},
        },
        "pricing": {"billing_model": "per_minute", "currency": "USD"},
    },
    "compute/vmss": {
        "skus": {
            "Standard_D2s_v3": {"vcpus": 2, "memory_gb": 8},
            "Standard_D4s_v3": {"vcpus": 4, "memory_gb": 16},
        },
        "pricing": {"billing_model": "per_minute", "currency": "USD"},
    },
    "compute/snapshot": {
        "skus": {
            "Standard_LRS": {"tier": "hdd", "per_gb_month_usd": 0.06},
            "Standard_ZRS": {"tier": "hdd", "zone_redundant": True, "per_gb_month_usd": 0.06},
            "Premium_LRS": {"tier": "premium_ssd", "per_gb_month_usd": 0.12},
        },
        "pricing": {"billing_model": "per_gb_month", "currency": "USD"},
    },
    "containers/aks": {
        "skus": {
            "Free": {"control_plane_cost_usd": 0, "sla": None},
            "Standard": {"control_plane_cost_usd_per_hour": 0.10, "sla": 99.95},
            "Premium": {"control_plane_cost_usd_per_hour": 0.60, "sla": 99.95, "uptime_guarantee": True},
        },
        "pricing": {"billing_model": "control_plane_plus_nodes", "currency": "USD"},
    },
    "containers/acr": {
        "skus": {
            "Basic": {"storage_gb": 10, "webhooks": 2, "geo_replication": False},
            "Standard": {"storage_gb": 100, "webhooks": 10, "geo_replication": False},
            "Premium": {"storage_gb": 500, "webhooks": 500, "geo_replication": True},
        },
        "pricing": {"billing_model": "daily", "currency": "USD"},
    },
    "database/sql": {
        "skus": {
            "Basic": {"dtu_max": 5, "max_db_gb": 2},
            "S0": {"dtu": 10, "max_db_gb": 250},
            "S3": {"dtu": 100, "max_db_gb": 250},
            "P1": {"vcores": 2, "max_db_gb": 1024},
            "P2": {"vcores": 4, "max_db_gb": 1024},
            "GP_Gen5_2": {"vcores": 2, "tier": "GeneralPurpose"},
            "BC_Gen5_2": {"vcores": 2, "tier": "BusinessCritical"},
        },
        "pricing": {"billing_model": "dtu_or_vcore", "currency": "USD"},
    },
    "database/cosmosdb": {
        "skus": {
            "ProvisionedThroughput": {"mode": "provisioned", "min_ru": 400},
            "Serverless": {"mode": "serverless"},
            "Autoscale": {"mode": "autoscale", "max_ru": 4000},
        },
        "pricing": {"billing_model": "request_units", "currency": "USD"},
    },
    "database/postgresql": {
        "skus": {
            "Burstable": {"tier": "Burstable", "vcores": [1, 2, 4, 8, 12, 16, 20]},
            "GeneralPurpose": {"tier": "GeneralPurpose", "vcores": [2, 4, 8, 16, 32, 48, 64]},
            "MemoryOptimized": {"tier": "MemoryOptimized", "vcores": [2, 4, 8, 16, 32, 48, 64]},
        },
        "pricing": {"billing_model": "vcore_hour", "currency": "USD"},
    },
    "integration/apim": {
        "skus": {
            "Developer": {"units": 1, "sla": False, "vnet": False},
            "Basic": {"units": 2, "sla": True, "vnet": False},
            "Standard": {"units": 4, "sla": True, "vnet": True},
            "Premium": {"units": 12, "sla": True, "vnet": True, "multi_region": True},
        },
        "pricing": {"billing_model": "unit_hour", "currency": "USD"},
    },
    "integration/datafactory": {
        "skus": {"Standard": {"billing": "activity_run"}},
        "pricing": {"billing_model": "activity_execution", "currency": "USD"},
    },
    "integration/logicapp": {
        "skus": {
            "Consumption": {"billing": "action_execution"},
            "Standard": {"billing": "workflow_hosting"},
        },
        "pricing": {"billing_model": "consumption_or_hosted", "currency": "USD"},
    },
    "messaging/eventhub": {
        "skus": {
            "Basic": {"partitions": 32, "retention_days": 1, "throughput_units": 1},
            "Standard": {"partitions": 32, "retention_days": 7, "throughput_units": 20},
            "Premium": {"partitions": 100, "retention_days": 90, "processing_units": True},
        },
        "pricing": {"billing_model": "throughput_unit", "currency": "USD"},
    },
    "messaging/servicebus": {
        "skus": {
            "Basic": {"queues": True, "topics": False},
            "Standard": {"queues": True, "topics": True},
            "Premium": {"messaging_units": True, "dedicated": True},
        },
        "pricing": {"billing_model": "messaging_operations", "currency": "USD"},
    },
    "monitoring/loganalytics": {
        "skus": {
            "PerGB2018": {"billing": "per_gb_ingested"},
            "CapacityReservation": {"billing": "daily_capacity_tiers"},
        },
        "pricing": {"billing_model": "ingestion", "currency": "USD"},
    },
    "monitoring/appinsights": {
        "skus": {"PerGB2018": {"billing": "per_gb_ingested"}},
        "pricing": {"billing_model": "ingestion", "currency": "USD"},
    },
    "network/firewall": {
        "skus": {
            "AZFW_VNet": {"deployment": "vnet", "threat_intel": True},
            "AZFW_Hub": {"deployment": "secured_hub", "threat_intel": True},
        },
        "pricing": {"billing_model": "deployment_hour_plus_data", "currency": "USD"},
    },
    "network/cdn": {
        "skus": {
            "Standard_Microsoft": {"provider": "microsoft"},
            "Standard_Akamai": {"provider": "akamai"},
            "Standard_Verizon": {"provider": "verizon"},
            "Premium_Verizon": {"provider": "verizon", "tier": "premium"},
        },
        "pricing": {"billing_model": "egress_gb", "currency": "USD"},
    },
    "network/expressroute": {
        "skus": {
            "Standard": {"bandwidth_mbps": [50, 100, 200, 500, 1000, 2000, 5000, 10000]},
            "Premium": {"bandwidth_mbps": [50, 100, 200, 500, 1000, 2000, 5000, 10000], "expressroute_global_reach": True},
        },
        "pricing": {"billing_model": "port_monthly", "currency": "USD"},
    },
    "network/frontdoor": {
        "skus": {
            "Standard_AzureFrontDoor": {"waf": False},
            "Premium_AzureFrontDoor": {"waf": True},
        },
        "pricing": {"billing_model": "request_and_egress", "currency": "USD"},
    },
    "network/nic": {
        "skus": {"Standard": {"accelerated_networking": "optional"}},
        "pricing": {"billing_model": "included_with_vm", "currency": "USD"},
    },
    "network/nsg": {
        "skus": {"Standard": {}},
        "pricing": {"billing_model": "free", "currency": "USD"},
    },
    "network/privatedns": {
        "skus": {"Standard": {"zones_billed": True}},
        "pricing": {"billing_model": "zone_monthly", "currency": "USD"},
    },
    "network/privateendpoint": {
        "skus": {"Standard": {"hourly_usd": 0.01, "data_processed_per_gb_usd": 0.01}},
        "pricing": {"billing_model": "hourly_plus_data", "currency": "USD"},
    },
    "network/privatelinkservice": {
        "skus": {"Standard": {"nat_ip_hourly_usd": 0.01}},
        "pricing": {"billing_model": "hourly", "currency": "USD"},
    },
    "network/trafficmanager": {
        "skus": {
            "Performance": {"routing": "performance"},
            "Priority": {"routing": "priority"},
            "Geographic": {"routing": "geographic"},
            "MultiValue": {"routing": "multivalue"},
            "Subnet": {"routing": "subnet"},
        },
        "pricing": {"billing_model": "dns_query", "currency": "USD"},
    },
    "network/vnet": {
        "skus": {"Standard": {"peering_ingress_per_gb_usd": 0.01, "peering_egress_per_gb_usd": 0.01}},
        "pricing": {"billing_model": "peering_and_ip", "currency": "USD"},
    },
    "search/cognitivesearch": {
        "skus": {
            "Free": {"partitions": 1, "replicas": 1, "storage_gb": 50},
            "Basic": {"partitions": 3, "replicas": 3, "storage_gb": 15},
            "Standard": {"partitions": 12, "replicas": 12},
            "StorageOptimized": {"partitions": 12, "replicas": 12, "storage_optimized": True},
        },
        "pricing": {"billing_model": "search_unit", "currency": "USD"},
    },
    "security/keyvault": {
        "skus": {
            "standard": {"hsm": False, "soft_delete": True},
            "premium": {"hsm": False, "soft_delete": True, "keys_rsa_2048": True},
        },
        "pricing": {"billing_model": "operation", "currency": "USD"},
    },
    "analytics/adx": {
        "skus": {
            "Standard_E2a_v4": {"vcpus": 2, "memory_gb": 16},
            "Standard_E4a_v4": {"vcpus": 4, "memory_gb": 32},
            "Standard_E8a_v4": {"vcpus": 8, "memory_gb": 64},
        },
        "pricing": {"billing_model": "cluster_hour", "currency": "USD"},
    },
    "analytics/databricks": {
        "skus": {
            "Standard": {"tier": "standard"},
            "Premium": {"tier": "premium", "compliance": True},
        },
        "pricing": {"billing_model": "dbu_plus_vm", "currency": "USD"},
    },
    "analytics/mlworkspace": {
        "skus": {"Basic": {}, "Enterprise": {"private_link": True}},
        "pricing": {"billing_model": "compute_hour", "currency": "USD"},
    },
    "analytics/synapse": {
        "skus": {
            "DW100c": {"compute_units": 100},
            "DW500c": {"compute_units": 500},
            "DW1000c": {"compute_units": 1000},
        },
        "pricing": {"billing_model": "c_hour", "currency": "USD"},
    },
    "backup/recoveryvault": {
        "skus": {"Standard": {"backup_storage_redundancy": ["LRS", "GRS", "ZRS"]}},
        "pricing": {"billing_model": "protected_instance", "currency": "USD"},
    },
    "appservice/plan": {
        "skus": {
            "F1": {"tier": "Free", "instances": 1},
            "B1": {"tier": "Basic", "instances": 3},
            "S1": {"tier": "Standard", "instances": 10},
            "P1v3": {"tier": "PremiumV3", "instances": 30},
        },
        "pricing": {"billing_model": "plan_hour", "currency": "USD"},
    },
    "appservice/webapp": {
        "skus": {
            "F1": {"tier": "Free"},
            "B1": {"tier": "Basic"},
            "S1": {"tier": "Standard"},
            "P1v3": {"tier": "PremiumV3"},
        },
        "pricing": {"billing_model": "plan_hour", "currency": "USD"},
    },
}

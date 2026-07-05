"""OpenAPI document for Azure Resource Manager — shown in the in-app API explorer."""

from __future__ import annotations

from typing import Any

from app.arm_api_versions import (
    ARM_GET_API_VERSIONS,
    MONITOR_METRICS_API_VERSION,
    RESOURCES_LIST_API_VERSION,
    SUBSCRIPTIONS_LIST_API_VERSION,
)

AZURE_MGMT_BASE = "https://management.azure.com"

# ARM path regex → app proxy template (used by the SPA request interceptor).
# Named groups become query params; {name} in proxy path uses path segment captures.
PROXY_ROUTE_SPECS: list[dict[str, Any]] = [
    {
        "arm": r"^/subscriptions$",
        "proxy": "/api/azure/subscriptions",
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/resourcegroups$",
        "proxy": "/api/azure/resource-groups",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/resources$",
        "proxy": "/api/azure/resources",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Compute/virtualMachines$",
        "proxy": "/api/azure/vms",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Compute/virtualMachineScaleSets$",
        "proxy": "/api/azure/vmss",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Compute/disks$",
        "proxy": "/api/azure/disks",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Compute/snapshots$",
        "proxy": "/api/azure/snapshots",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.ContainerService/managedClusters$",
        "proxy": "/api/azure/aks",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/resourceGroups/(?<resourceGroup>[^/]+)/providers/Microsoft\.Compute/virtualMachines/(?<vmName>[^/]+)$",
        "proxy": "/api/azure/vms/{resourceGroup}/{vmName}",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/resourceGroups/(?<resourceGroup>[^/]+)/providers/Microsoft\.ContainerService/managedClusters/(?<clusterName>[^/]+)$",
        "proxy": "/api/azure/aks/{resourceGroup}/{clusterName}",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/resourceGroups/(?<resourceGroup>[^/]+)/providers/Microsoft\.ContainerService/managedClusters/(?<clusterName>[^/]+)/agentPools$",
        "proxy": "/api/azure/aks/{resourceGroup}/{clusterName}/node-pools",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Storage/storageAccounts$",
        "proxy": "/api/azure/storage",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Web/sites$",
        "proxy": "/api/azure/appservices",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Web/serverfarms$",
        "proxy": "/api/azure/appserviceplans",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Sql/servers$",
        "proxy": "/api/azure/sql",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.DBforPostgreSQL/flexibleServers$",
        "proxy": "/api/azure/postgresql",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.DBforMySQL/flexibleServers$",
        "proxy": "/api/azure/mysql",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.DocumentDB/databaseAccounts$",
        "proxy": "/api/azure/cosmosdb",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Network/publicIPAddresses$",
        "proxy": "/api/azure/publicips",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Network/virtualNetworks$",
        "proxy": "/api/azure/vnets",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Network/loadBalancers$",
        "proxy": "/api/azure/loadbalancers",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Network/applicationGateways$",
        "proxy": "/api/azure/appgateways",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Network/networkSecurityGroups$",
        "proxy": "/api/azure/nsgs",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Network/networkInterfaces$",
        "proxy": "/api/azure/nics",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Network/privateEndpoints$",
        "proxy": "/api/azure/privateendpoints",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Network/privateLinkServices$",
        "proxy": "/api/azure/privatelinkservices",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Network/privateDnsZones$",
        "proxy": "/api/azure/privatedns",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.Cache/redis$",
        "proxy": "/api/azure/redis",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.KeyVault/vaults$",
        "proxy": "/api/azure/keyvaults",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^/subscriptions/(?<subscriptionId>[^/]+)/providers/Microsoft\.ContainerRegistry/registries$",
        "proxy": "/api/azure/acr",
        "query": {"subscription_id": "{subscriptionId}"},
    },
    {
        "arm": r"^(?<resourceId>/subscriptions/[^/]+(?:/[^/]+)*/providers/[^/]+/[^/]+(?:/[^/]+)*)/providers/Microsoft\.Insights/metrics$",
        "proxy": "/api/azure/metrics/resource",
        "query": {"resource_id": "{resourceId}"},
        "forwardQuery": ["metricnames", "timespan", "interval", "aggregation"],
    },
]


def _api_version_param(version: str) -> dict[str, Any]:
    return {
        "name": "api-version",
        "in": "query",
        "required": True,
        "schema": {"type": "string", "default": version},
    }


def _subscription_path_param() -> dict[str, Any]:
    return {
        "name": "subscriptionId",
        "in": "path",
        "required": True,
        "schema": {"type": "string", "format": "uuid"},
    }


def _list_op(summary: str, api_version: str, *, extra_params: list[dict] | None = None) -> dict[str, Any]:
    params = [_api_version_param(api_version)]
    if extra_params:
        params.extend(extra_params)
    return {
        "get": {
            "tags": ["Azure Resource Manager"],
            "summary": summary,
            "parameters": params,
            "responses": {"200": {"description": "Azure ARM response (proxied)"}},
        },
    }


def build_azure_arm_openapi_schema(*, version: str = "5.0.0") -> dict[str, Any]:
    """OpenAPI spec that documents real Azure management.azure.com endpoints."""
    paths: dict[str, Any] = {}

    paths["/subscriptions"] = _list_op(
        "List subscriptions",
        SUBSCRIPTIONS_LIST_API_VERSION,
    )
    paths["/subscriptions/{subscriptionId}/resourcegroups"] = {
        "get": {
            "tags": ["Azure Resource Manager"],
            "summary": "List resource groups",
            "parameters": [
                _subscription_path_param(),
                _api_version_param(RESOURCES_LIST_API_VERSION),
            ],
            "responses": {"200": {"description": "Azure ARM response (proxied)"}},
        },
    }
    paths["/subscriptions/{subscriptionId}/resources"] = {
        "get": {
            "tags": ["Azure Resource Manager"],
            "summary": "List resources",
            "parameters": [
                _subscription_path_param(),
                _api_version_param(RESOURCES_LIST_API_VERSION),
                {
                    "name": "$filter",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "string"},
                    "example": "resourceType eq 'Microsoft.Compute/virtualMachines'",
                },
            ],
            "responses": {"200": {"description": "Azure ARM response (proxied)"}},
        },
    }

    provider_lists = [
        ("Microsoft.Compute/virtualMachines", "List virtual machines"),
        ("Microsoft.Compute/virtualMachineScaleSets", "List VM scale sets"),
        ("Microsoft.Compute/disks", "List managed disks"),
        ("Microsoft.Compute/snapshots", "List snapshots"),
        ("Microsoft.ContainerService/managedClusters", "List AKS clusters"),
        ("Microsoft.Storage/storageAccounts", "List storage accounts"),
        ("Microsoft.Web/sites", "List App Services"),
        ("Microsoft.Web/serverfarms", "List App Service plans"),
        ("Microsoft.Sql/servers", "List SQL servers"),
        ("Microsoft.DBforPostgreSQL/flexibleServers", "List PostgreSQL flexible servers"),
        ("Microsoft.DBforMySQL/flexibleServers", "List MySQL flexible servers"),
        ("Microsoft.DocumentDB/databaseAccounts", "List Cosmos DB accounts"),
        ("Microsoft.Network/publicIPAddresses", "List public IP addresses"),
        ("Microsoft.Network/virtualNetworks", "List virtual networks"),
        ("Microsoft.Network/loadBalancers", "List load balancers"),
        ("Microsoft.Network/applicationGateways", "List application gateways"),
        ("Microsoft.Network/networkSecurityGroups", "List network security groups"),
        ("Microsoft.Network/networkInterfaces", "List network interfaces"),
        ("Microsoft.Network/privateEndpoints", "List private endpoints"),
        ("Microsoft.Network/privateLinkServices", "List private link services"),
        ("Microsoft.Network/privateDnsZones", "List private DNS zones"),
        ("Microsoft.Cache/redis", "List Redis caches"),
        ("Microsoft.KeyVault/vaults", "List Key Vaults"),
        ("Microsoft.ContainerRegistry/registries", "List container registries"),
    ]
    for arm_type, summary in provider_lists:
        provider, type_name = arm_type.split("/", 1)
        api_ver = ARM_GET_API_VERSIONS.get(arm_type.lower(), RESOURCES_LIST_API_VERSION)
        paths[f"/subscriptions/{{subscriptionId}}/providers/{provider}/{type_name}"] = {
            "get": {
                "tags": ["Azure Resource Manager"],
                "summary": summary,
                "parameters": [
                    _subscription_path_param(),
                    _api_version_param(api_ver),
                ],
                "responses": {"200": {"description": "Azure ARM response (proxied)"}},
            },
        }

    compute_ver = ARM_GET_API_VERSIONS["microsoft.compute/virtualmachines"]
    aks_ver = ARM_GET_API_VERSIONS["microsoft.containerservice/managedclusters"]

    paths["/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.Compute/virtualMachines/{vmName}"] = {
        "get": {
            "tags": ["Azure Resource Manager"],
            "summary": "Get virtual machine",
            "parameters": [
                _subscription_path_param(),
                {"name": "resourceGroup", "in": "path", "required": True, "schema": {"type": "string"}},
                {"name": "vmName", "in": "path", "required": True, "schema": {"type": "string"}},
                _api_version_param(compute_ver),
            ],
            "responses": {"200": {"description": "Azure ARM response (proxied)"}},
        },
    }
    paths["/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.ContainerService/managedClusters/{clusterName}"] = {
        "get": {
            "tags": ["Azure Resource Manager"],
            "summary": "Get AKS cluster",
            "parameters": [
                _subscription_path_param(),
                {"name": "resourceGroup", "in": "path", "required": True, "schema": {"type": "string"}},
                {"name": "clusterName", "in": "path", "required": True, "schema": {"type": "string"}},
                _api_version_param(aks_ver),
            ],
            "responses": {"200": {"description": "Azure ARM response (proxied)"}},
        },
    }
    paths["/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.ContainerService/managedClusters/{clusterName}/agentPools"] = {
        "get": {
            "tags": ["Azure Resource Manager"],
            "summary": "List AKS node pools",
            "parameters": [
                _subscription_path_param(),
                {"name": "resourceGroup", "in": "path", "required": True, "schema": {"type": "string"}},
                {"name": "clusterName", "in": "path", "required": True, "schema": {"type": "string"}},
                _api_version_param(aks_ver),
            ],
            "responses": {"200": {"description": "Azure ARM response (proxied)"}},
        },
    }
    paths["/{resourceId}/providers/Microsoft.Insights/metrics"] = {
        "get": {
            "tags": ["Azure Monitor"],
            "summary": "List metrics for a resource",
            "parameters": [
                {
                    "name": "resourceId",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                    "example": "/subscriptions/{subscriptionId}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
                },
                _api_version_param(MONITOR_METRICS_API_VERSION),
                {"name": "metricnames", "in": "query", "required": True, "schema": {"type": "string"}},
                {"name": "timespan", "in": "query", "schema": {"type": "string", "default": "PT1H"}},
                {"name": "interval", "in": "query", "schema": {"type": "string", "default": "PT5M"}},
                {"name": "aggregation", "in": "query", "schema": {"type": "string", "default": "Average"}},
            ],
            "responses": {"200": {"description": "Azure Monitor response (proxied)"}},
        },
    }

    # Profile-driven metrics (app routes — no ARM proxy rewrite).
    paths["/api/azure/metrics/profiles"] = {
        "get": {
            "tags": ["Metrics API"],
            "summary": "Catalog of monitor profiles and metric names per ARM resource type",
            "responses": {"200": {"description": "Monitor profile catalog"}},
        },
    }
    paths["/api/azure/metrics/resource/plan"] = {
        "get": {
            "tags": ["Metrics API"],
            "summary": "Metric names that apply to one resource (by ARM type)",
            "parameters": [
                {
                    "name": "resource_id",
                    "in": "query",
                    "required": True,
                    "schema": {"type": "string"},
                    "example": "/subscriptions/{subscriptionId}/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
                },
            ],
            "responses": {"200": {"description": "Metric plan for resource"}},
        },
    }
    paths["/api/azure/metrics/resource/auto"] = {
        "get": {
            "tags": ["Metrics API"],
            "summary": "Fetch Azure Monitor metrics for one resource (profile-driven)",
            "parameters": [
                {
                    "name": "resource_id",
                    "in": "query",
                    "required": True,
                    "schema": {"type": "string"},
                },
                {"name": "timespan", "in": "query", "schema": {"type": "string", "default": "P7D"}},
            ],
            "responses": {"200": {"description": "Metrics and derived facts"}},
        },
    }
    paths["/api/azure/metrics/by-type"] = {
        "get": {
            "tags": ["Metrics API"],
            "summary": "Fetch metrics for all synced resources of one type",
            "parameters": [
                {"name": "subscription_id", "in": "query", "required": True, "schema": {"type": "string", "format": "uuid"}},
                {"name": "canonical_type", "in": "query", "required": True, "schema": {"type": "string"}, "example": "compute/vm"},
                {"name": "timespan", "in": "query", "schema": {"type": "string", "default": "P7D"}},
                {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 0}},
            ],
            "responses": {"200": {"description": "Metrics per resource in subscription inventory"}},
        },
    }
    paths["/api/azure/metrics/subscription"] = {
        "get": {
            "tags": ["Metrics API"],
            "summary": "Fetch metrics for synced inventory (all types or one filter)",
            "parameters": [
                {"name": "subscription_id", "in": "query", "required": True, "schema": {"type": "string", "format": "uuid"}},
                {"name": "canonical_type", "in": "query", "schema": {"type": "string"}, "example": "compute/vm"},
                {"name": "timespan", "in": "query", "schema": {"type": "string", "default": "P7D"}},
                {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 0}},
            ],
            "responses": {"200": {"description": "Metrics grouped by canonical type"}},
        },
    }

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Azure Resource Manager",
            "version": version,
            "description": (
                "Azure management API endpoints (management.azure.com). "
                "Try it out sends the request through this app, which attaches the "
                "managed identity token server-side."
            ),
        },
        "servers": [{"url": "", "description": "Proxied to management.azure.com"}],
        "tags": [
            {"name": "Azure Resource Manager", "description": "Subscription and resource inventory"},
            {"name": "Azure Monitor", "description": "Metrics API"},
            {"name": "Metrics API", "description": "Profile-driven Azure Monitor metrics per resource"},
        ],
        "paths": paths,
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "App session JWT (Azure token is applied by the server proxy).",
                },
            },
        },
        "security": [{"BearerAuth": []}],
        "x-proxy-config": {
            "managementHost": "management.azure.com",
            "routes": PROXY_ROUTE_SPECS,
        },
    }

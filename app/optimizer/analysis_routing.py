"""Route optimization work — assessment JSON rules run inside legacy sub-engines.

Architecture
------------
* **Data pipeline** (metrics + data quality): inventory snapshots and
  ``pythonAssessment`` scoring from ``data/*-assessment.json``.

* **Sub-engines** (recommendations): ``it_services/*/engine/`` loads assessment JSON
  rules per ARM type, evaluates them on each resource, then runs Python analyzers
  for pricing/savings enrichment. One optimization run — no separate assessment path.

Set ``LEGACY_SUB_ENGINES_ENABLED=false`` only to disable per-resource engines
during troubleshooting; platform engines still run.
"""

from __future__ import annotations

import os
from typing import Any

from app.assessment.catalog import indexed_arm_types
from app.resource_type_map import arm_provider_type

# Platform analyzers — not replaced by per-resource assessment JSON.
PLATFORM_SUB_ENGINE_NAMES: frozenset[str] = frozenset({
    "BudgetSubEngine",
    "CostAnomalySubEngine",
    "CommitmentsSubEngine",
})

# Buckets that are subscription-scoped, not per-resource ARM inventory.
PLATFORM_BUCKETS: frozenset[str] = frozenset({
    "budgets",
    "cost_anomalies",
})

# Canonical DB types → ARM provider types (subset used for routing checks).
_CANONICAL_TO_ARM: dict[str, str] = {
    "compute/vm": "Microsoft.Compute/virtualMachines",
    "compute/vmss": "Microsoft.Compute/virtualMachineScaleSets",
    "compute/disk": "Microsoft.Compute/disks",
    "compute/snapshot": "Microsoft.Compute/snapshots",
    "containers/aks": "Microsoft.ContainerService/managedClusters",
    "containers/acr": "Microsoft.ContainerRegistry/registries",
    "storage/account": "Microsoft.Storage/storageAccounts",
    "network/publicip": "Microsoft.Network/publicIPAddresses",
    "network/vnet": "Microsoft.Network/virtualNetworks",
    "network/nic": "Microsoft.Network/networkInterfaces",
    "network/nat": "Microsoft.Network/natGateways",
    "network/loadbalancer": "Microsoft.Network/loadBalancers",
    "network/appgateway": "Microsoft.Network/applicationGateways",
    "network/nsg": "Microsoft.Network/networkSecurityGroups",
    "database/sql": "Microsoft.Sql/servers",
    "database/cosmosdb": "Microsoft.DocumentDB/databaseAccounts",
    "database/postgresql": "Microsoft.DBforPostgreSQL/flexibleServers",
    "database/redis": "Microsoft.Cache/redis",
    "appservice/webapp": "Microsoft.Web/sites",
    "appservice/plan": "Microsoft.Web/serverfarms",
    "security/keyvault": "Microsoft.KeyVault/vaults",
    "monitoring/loganalytics": "Microsoft.OperationalInsights/workspaces",
    "monitoring/appinsights": "Microsoft.Insights/components",
    "integration/apim": "Microsoft.ApiManagement/service",
    "integration/datafactory": "Microsoft.DataFactory/factories",
    "integration/logicapp": "Microsoft.Logic/workflows",
    "messaging/eventhub": "Microsoft.EventHub/namespaces",
    "messaging/servicebus": "Microsoft.ServiceBus/namespaces",
    "analytics/databricks": "Microsoft.Databricks/workspaces",
    "analytics/synapse": "Microsoft.Synapse/workspaces",
    "analytics/adx": "Microsoft.Kusto/clusters",
    "analytics/mlworkspace": "Microsoft.MachineLearningServices/workspaces",
    "backup/recoveryvault": "Microsoft.RecoveryServices/vaults",
    "search/cognitivesearch": "Microsoft.Search/searchServices",
    "network/firewall": "Microsoft.Network/azureFirewalls",
    "network/cdn": "Microsoft.Cdn/profiles",
    "network/privateendpoint": "Microsoft.Network/privateEndpoints",
    "network/privatelinkservice": "Microsoft.Network/privateLinkServices",
    "network/privatedns": "Microsoft.Network/privateDnsZones",
}


def assessment_pipeline_primary() -> bool:
    """When true, indexed ARM types are owned by the assessment pipeline."""
    if os.getenv("ASSESSMENT_PIPELINE_ENABLED") is not None:
        return os.getenv("ASSESSMENT_PIPELINE_ENABLED", "true").lower() not in {"0", "false", "no"}
    return True


def unified_recommendation_mode() -> bool:
    """Sub-engines own recommendations using assessment JSON rules (default)."""
    return assessment_pipeline_primary() and integrated_sub_engines_enabled()


def integrated_sub_engines_enabled() -> bool:
    """Per-resource Python sub-engines run alongside the assessment pipeline (default on)."""
    return os.getenv("LEGACY_SUB_ENGINES_ENABLED", "true").lower() not in {"0", "false", "no"}


def legacy_sub_engines_enabled() -> bool:
    """Alias for :func:`integrated_sub_engines_enabled`."""
    return integrated_sub_engines_enabled()


def is_indexed_arm_type(arm_type: str | None) -> bool:
    return (arm_type or "").strip().lower() in indexed_arm_types()


def is_indexed_resource(resource: dict[str, Any]) -> bool:
    rid = resource.get("id") or resource.get("resource_id") or ""
    arm = (arm_provider_type(rid) or resource.get("type") or "").strip().lower()
    return is_indexed_arm_type(arm)


def component_has_non_indexed_types(component: str) -> bool:
    """Return True when a UI component includes types not covered by assessment JSON."""
    from app.optimizer.component_map import sync_types_for_component

    indexed = indexed_arm_types()
    for canonical in sync_types_for_component(component):
        arm = _CANONICAL_TO_ARM.get((canonical or "").strip().lower(), "").lower()
        if not arm or arm not in indexed:
            return True
    return False


def should_run_sub_engine(engine_cls: type) -> bool:
    """Decide whether a registered sub-engine should execute."""
    name = getattr(engine_cls, "__name__", "")
    if name in PLATFORM_SUB_ENGINE_NAMES:
        return True
    if not assessment_pipeline_primary():
        return True
    return integrated_sub_engines_enabled()


def filter_resources_for_legacy(resources: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Drop indexed ARM resources only when sub-engines are explicitly disabled."""
    rows = list(resources or [])
    if integrated_sub_engines_enabled() or not assessment_pipeline_primary():
        return rows
    return [row for row in rows if not is_indexed_resource(row)]


def filter_buckets_for_legacy_analysis(
    buckets: dict[str, list],
    *,
    preserve_canonical_types: set[str] | frozenset[str] | None = None,
) -> dict[str, list]:
    """Prepare bucket dict for legacy extended-engine analysis."""
    if integrated_sub_engines_enabled() or not assessment_pipeline_primary():
        return dict(buckets)

    preserve = {(t or "").strip().lower() for t in (preserve_canonical_types or ()) if t}
    filtered: dict[str, list] = {}
    for key, items in buckets.items():
        if key in PLATFORM_BUCKETS:
            filtered[key] = list(items or [])
            continue
        if key == "cost_anomalies":
            filtered[key] = list(items or [])
            continue
        if preserve:
            kept: list[dict] = []
            for row in items or []:
                rid = (row.get("id") or row.get("resource_id") or "").strip()
                from app.resource_type_map import internal_resource_type

                canonical = (
                    (row.get("_canonical_type") or "").strip().lower()
                    or internal_resource_type(rid)
                    or (row.get("type") or "").strip().lower()
                )
                if canonical in preserve:
                    kept.append(row)
                elif not is_indexed_resource(row):
                    kept.append(row)
            filtered[key] = kept
            continue
        filtered[key] = filter_resources_for_legacy(items)
    return filtered


def legacy_analysis_has_work(
    buckets: dict[str, list],
    *,
    budgets: list | None = None,
    scoped_canonical_types: set[str] | frozenset[str] | None = None,
) -> bool:
    """True when legacy analysis still has platform or non-indexed resources to process."""
    preserve = {(t or "").strip().lower() for t in (scoped_canonical_types or ()) if t}
    merged = filter_buckets_for_legacy_analysis(
        buckets,
        preserve_canonical_types=preserve or None,
    )
    if budgets:
        merged = {**merged, "budgets": budgets}
    return any(merged.get(key) for key in merged)


def should_chain_component_analysis(component: str) -> bool:
    """Component sync chains legacy analysis when sub-engines are integrated (default)."""
    if integrated_sub_engines_enabled() or not assessment_pipeline_primary():
        return True
    return component_has_non_indexed_types(component)


def analysis_routing_status() -> dict[str, Any]:
    """Expose routing policy for scheduler / admin surfaces."""
    return {
        "assessment_pipeline_primary": assessment_pipeline_primary(),
        "integrated_sub_engines_enabled": integrated_sub_engines_enabled(),
        "unified_recommendation_mode": unified_recommendation_mode(),
        "legacy_sub_engines_enabled": integrated_sub_engines_enabled(),
        "indexed_arm_types": len(indexed_arm_types()),
        "platform_sub_engines": sorted(PLATFORM_SUB_ENGINE_NAMES),
        "resource_sub_engines_default": integrated_sub_engines_enabled(),
    }

"""DB-first optimization analysis — reads synced inventory and writes recommendations back."""
from __future__ import annotations

import json
import structlog
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.analysis_persist import persist_optimization_run
from app.analysis_summary import merge_analysis_results, summarize_findings
from app.optimizer.component_map import ANALYSIS_BATCHES, resolve_batches, resource_types_for_components
from app.analysis.resource_graph import assign_action_chains, build_disk_snapshot_links, build_resource_graph
from app.cost_db import daily_rate_by_service, resource_cost_map_from_db, resource_daily_cost_histories
from app.optimizer.engine_config import get_effective_config, get_global_engine_config
from app.optimizer.engine_runtime import filter_bucket_dict, split_rule_overrides
from app.optimizer.analysis_routing import (
    filter_buckets_for_legacy_analysis,
    legacy_analysis_has_work,
    legacy_sub_engines_enabled,
)
from app.optimizer.unified_engine import append_cost_export_findings
from app.models import BudgetSnapshot
from app.optimizer.engine import OptimizationEngine
from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.workload_classifier import classify_workloads_for_buckets
from app.metrics_loader import (
    analysis_metrics_summary,
    load_analysis_metrics,
    load_cached_resource_facts,
)
from app.utilization_history import (
    batch_utilization_trends,
    collect_resource_ids_from_buckets,
    persist_utilization_snapshot,
)
from app.resource_store import (
    apply_costs_to_resources,
    list_all_resources_db,
    list_resources_by_types_db,
    list_resources_by_types_parallel,
)
from app.resource_type_map import arm_provider_type, internal_resource_type
from app.focus_mapping import normalize_arm_id

log = structlog.get_logger()

# Canonical DB type → ARM resource type (for engine metadata)
CANONICAL_TO_ARM: dict[str, str] = {
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

# Map canonical types into optimization engine argument buckets
TYPE_TO_BUCKET: dict[str, str] = {
    "compute/vm": "vms",
    "compute/disk": "disks",
    "compute/snapshot": "snapshots",
    "containers/aks": "aks_clusters",
    "containers/acr": "container_registries",
    "storage/account": "storage",
    "network/publicip": "public_ips",
    "network/vnet": "vnets",
    "network/nic": "network_interfaces",
    "network/nat": "nat_gateways",
    "network/loadbalancer": "load_balancers",
    "network/appgateway": "app_gateways",
    "network/nsg": "nsgs",
    "database/sql": "sql_servers",
    "database/cosmosdb": "cosmosdb",
    "database/postgresql": "postgresql",
    "database/redis": "redis_caches",
    "appservice/webapp": "app_services",
    "appservice/plan": "app_service_plans",
    "security/keyvault": "keyvaults",
    "monitoring/loganalytics": "log_analytics_workspaces",
    "monitoring/appinsights": "app_insights_components",
    "integration/apim": "apim_services",
    "integration/datafactory": "data_factories",
    "integration/logicapp": "logic_apps",
    "messaging/eventhub": "event_hubs",
    "messaging/servicebus": "service_bus_namespaces",
    "analytics/databricks": "databricks_workspaces",
    "analytics/synapse": "synapse_workspaces",
    "analytics/adx": "adx_clusters",
    "analytics/mlworkspace": "ml_workspaces",
    "backup/recoveryvault": "recovery_vaults",
    "search/cognitivesearch": "cognitive_search_services",
    "network/firewall": "firewalls",
    "network/cdn": "cdn_profiles",
    "network/expressroute": "expressroute_circuits",
    "network/trafficmanager": "traffic_managers",
    "network/frontdoor": "front_doors",
    "network/privateendpoint": "private_endpoints",
    "network/privatelinkservice": "private_link_services",
    "network/privatedns": "private_dns_zones",
}

# Engine bucket → canonical types (for per-batch DB loads)
BUCKET_TO_TYPES: dict[str, list[str]] = {}
for _canonical, _bucket in TYPE_TO_BUCKET.items():
    BUCKET_TO_TYPES.setdefault(_bucket, []).append(_canonical)


def _resolve_inventory_bucket(canonical: str, resource_id: str) -> str | None:
    """Route inventory rows to engine buckets, including SQL server vs database."""
    if canonical == "database/sql":
        rid_lower = (resource_id or "").lower()
        if "/databases/" in rid_lower:
            return "sql_databases"
        return "sql_servers"
    return TYPE_TO_BUCKET.get(canonical)


def _enrich_properties(canonical_type: str, state: str | None, props: dict) -> dict:
    """Normalize DB row fields into shapes the rule engine expects."""
    out = dict(props or {})
    state_text = (state or "").strip()
    if canonical_type == "compute/disk" and state_text:
        out.setdefault("diskState", state_text)
    if canonical_type == "compute/vm" and state_text:
        power = state_text.split("/")[-1] if "/" in state_text else state_text
        out.setdefault(
            "instanceView",
            {"statuses": [{"code": f"PowerState/{power}"}]},
        )
    if canonical_type == "compute/vmss" and state_text:
        power = state_text.split("/")[-1] if "/" in state_text else state_text
        out.setdefault("powerState", power)
    if canonical_type == "appservice/webapp" and state_text:
        out.setdefault("state", state_text)
    if canonical_type == "database/postgresql" and state_text:
        out.setdefault("state", state_text)
    if canonical_type == "storage/account":
        out.setdefault("accessTier", out.get("accessTier") or state_text or "Hot")
    if canonical_type == "network/publicip":
        if state_text and "ipConfiguration" not in out:
            out["ipConfiguration"] = None if state_text.lower() in {"unassociated", "none"} else {}
    if canonical_type == "network/nic" and state_text:
        out.setdefault("virtualMachine", None if "unattached" in state_text.lower() else {"id": "attached"})
    if canonical_type == "database/redis" and state_text:
        out.setdefault("provisioningState", state_text)
    return out


def row_to_arm_resource(row: dict[str, Any]) -> dict[str, Any]:
    canonical = row.get("type") or ""
    rid = row.get("id") or ""
    props = _enrich_properties(canonical, row.get("state"), row.get("properties") or {})
    sku_value = row.get("sku")
    sku_details = row.get("skuDetails") or row.get("sku_json") or {}
    if isinstance(sku_details, str):
        try:
            sku_details = json.loads(sku_details)
        except Exception:
            sku_details = {}
    sku = dict(sku_details.get("arm") or {})
    if not sku and sku_details.get("name"):
        sku = {"name": sku_details["name"]}
    if sku_value and not sku.get("name"):
        sku["name"] = sku_value
    if canonical == "compute/vm" and sku_details.get("vm_size"):
        props.setdefault("hardwareProfile", {})["vmSize"] = sku_details["vm_size"]
    arm_type = arm_provider_type(rid) or CANONICAL_TO_ARM.get(canonical, canonical)
    return {
        "id": rid,
        "name": row.get("name") or "",
        "type": arm_type,
        "location": row.get("location") or "",
        "resourceGroup": row.get("resourceGroup") or "",
        "tags": row.get("tags") or {},
        "sku": sku,
        "skuDetails": sku_details,
        "properties": props,
        "state": row.get("state") or "",
    }


def load_inventory_from_db(
    db: Session,
    subscription_id: str,
    *,
    global_config: dict | None = None,
    parallel: bool = True,
) -> tuple[dict[str, list], dict[str, int], dict[str, list]]:
    """Load all active resources and group them for the optimization engine."""
    subscription_id = subscription_id.lower()
    if parallel:
        rows = list_resources_by_types_parallel(
            subscription_id,
            list(TYPE_TO_BUCKET.keys()),
            global_config=global_config,
        )
        cost_map = resource_cost_map_from_db(db, subscription_id)
        rows = apply_costs_to_resources(rows, cost_map)
    else:
        rows = list_all_resources_db(db, subscription_id, global_config=global_config)

    buckets = empty_buckets()
    counts: dict[str, int] = {}

    for row in rows:
        canonical = row.get("type") or ""
        counts[canonical] = counts.get(canonical, 0) + 1
        bucket = _resolve_inventory_bucket(canonical, row.get("id") or "")
        if not bucket:
            continue
        buckets[bucket].append(row_to_arm_resource(row))

    aks_node_pools: dict[str, list] = {}
    for cluster in buckets["aks_clusters"]:
        cid = cluster.get("id") or ""
        pools = (cluster.get("properties") or {}).get("agentPoolProfiles") or []
        if cid:
            aks_node_pools[cid] = pools
            aks_node_pools[cid.lower()] = pools

    inventory_counts = {k: len(v) for k, v in buckets.items() if v}
    return buckets, inventory_counts, aks_node_pools


def load_buckets_for_keys(
    db: Session,
    subscription_id: str,
    bucket_keys: list[str],
    *,
    global_config: dict | None = None,
    parallel: bool = True,
) -> tuple[dict[str, list], dict[str, list]]:
    """Load only the inventory rows needed for one analysis batch."""
    sub = subscription_id.lower()
    buckets = empty_buckets()
    types: list[str] = []
    for key in bucket_keys:
        if key == "budgets":
            continue
        types.extend(BUCKET_TO_TYPES.get(key, []))
    if not types:
        return buckets, {}

    unique_types = sorted({t.strip().lower() for t in types if t})
    if parallel and len(unique_types) > 1:
        rows = list_resources_by_types_parallel(sub, unique_types, global_config=global_config)
        cost_map = resource_cost_map_from_db(db, sub)
        rows = apply_costs_to_resources(rows, cost_map)
    else:
        rows = list_resources_by_types_db(db, sub, unique_types, global_config=global_config)

    for row in rows:
        canonical = row.get("type") or ""
        bucket = _resolve_inventory_bucket(canonical, row.get("id") or "")
        if bucket:
            buckets[bucket].append(row_to_arm_resource(row))

    aks_node_pools: dict[str, list] = {}
    if "aks_clusters" in bucket_keys:
        for cluster in buckets["aks_clusters"]:
            cid = cluster.get("id") or ""
            pools = (cluster.get("properties") or {}).get("agentPoolProfiles") or []
            if cid:
                aks_node_pools[cid] = pools
                aks_node_pools[cid.lower()] = pools
    return buckets, aks_node_pools


def count_inventory_resources(db: Session, subscription_id: str) -> int:
    """Fast count of synced inventory rows (excludes cost-export-only snapshots)."""
    _, counts, _ = load_inventory_from_db(db, subscription_id.lower())
    return sum(counts.values())


def load_cost_by_resource_from_db(db: Session, subscription_id: str) -> dict[str, float]:
    """Build resource-id → MTD billing-currency map from cost_by_resource (PreTaxCost)."""
    from app.cost_utils import billing_cost_map_from_details

    cost_details = resource_cost_map_from_db(db, subscription_id)
    return billing_cost_map_from_details(cost_details)


def load_budgets_from_db(db: Session, subscription_id: str) -> list[dict]:
    subscription_id = subscription_id.lower()
    rows = (
        db.query(BudgetSnapshot)
        .filter(BudgetSnapshot.subscription_id == subscription_id)
        .all()
    )
    budgets = []
    for row in rows:
        budgets.append({
            "name": row.budget_name,
            "properties": {
                "amount": row.amount,
                "timeGrain": row.time_grain,
                "currentSpend": {"amount": row.current_spend},
                "forecastSpend": {"amount": row.forecast_spend},
                "currency": row.currency,
            },
        })
    return budgets


def empty_buckets() -> dict[str, list]:
    return {
        "vms": [], "vmss": [], "disks": [], "snapshots": [], "aks_clusters": [], "storage": [],
        "public_ips": [], "load_balancers": [], "app_gateways": [], "app_services": [],
        "app_service_plans": [], "network_interfaces": [], "nat_gateways": [],
        "redis_caches": [], "sql_servers": [], "sql_databases": [], "cosmosdb": [],
        "postgresql": [], "keyvaults": [], "nsgs": [], "container_registries": [],
        "log_analytics_workspaces": [], "app_insights_components": [],
        "apim_services": [], "data_factories": [], "logic_apps": [],
        "event_hubs": [], "service_bus_namespaces": [],
        "databricks_workspaces": [], "synapse_workspaces": [], "adx_clusters": [],
        "ml_workspaces": [], "recovery_vaults": [], "cognitive_search_services": [],
        "firewalls": [], "cdn_profiles": [], "expressroute_circuits": [], "traffic_managers": [],
        "front_doors": [], "vnets": [],
        "private_endpoints": [], "private_link_services": [], "private_dns_zones": [],
        "cost_anomalies": [],
    }


def run_engine_on_buckets(
    db: Session,
    *,
    subscription_id: str,
    buckets: dict[str, list],
    aks_node_pools: dict[str, list],
    cost_by_resource: dict[str, float],
    budgets: list[dict],
    profile: str,
    engine_version: str,
    rule_overrides: dict | None = None,
    vm_metrics: dict[str, dict] | None = None,
    node_metrics: dict[str, dict] | None = None,
    resource_metrics: dict[str, dict] | None = None,
    resource_facts: dict[str, dict[str, float]] | None = None,
    load_metrics: bool = True,
    include_ai: bool = True,
    scoped_canonical_types: list[str] | None = None,
) -> dict[str, Any]:
    """Run optimization engine on a (possibly partial) resource bucket set."""
    sub = subscription_id.lower()
    subscription_spend = sum(
        float(v) if not isinstance(v, dict) else float(v.get("usd") or v.get("pretax") or 0)
        for v in cost_by_resource.values()
    )
    db_overrides = get_effective_config(db, profile)
    merged_overrides = {**db_overrides, **(rule_overrides or {})}
    from app.optimizer.engine_config import get_global_engine_config
    from app.optimizer.engine_runtime import split_rule_overrides

    rule_only_overrides, inline_global = split_rule_overrides(merged_overrides)
    global_config = {**get_global_engine_config(db, profile), **inline_global}
    engine_version = engine_version.lower()
    if engine_version != "extended":
        log.warning(
            "legacy_engine_selected",
            engine_version=engine_version,
            message="Standard engine uses heuristic savings; extended engine is recommended for production.",
        )
    eng = (
        ExtendedOptimizationEngine(rule_overrides=rule_only_overrides, global_config=global_config)
        if engine_version == "extended"
        else OptimizationEngine(rule_overrides=rule_only_overrides, global_config=global_config)
    )

    if vm_metrics is None or node_metrics is None or resource_metrics is None:
        if load_metrics:
            loaded_vm, loaded_node, loaded_resource, loaded_facts, monitor_stats = load_analysis_metrics(
                db,
                buckets=buckets,
                cost_by_resource=cost_by_resource,
                rule_overrides=rule_only_overrides,
            )
            vm_metrics = loaded_vm if vm_metrics is None else vm_metrics
            node_metrics = loaded_node if node_metrics is None else node_metrics
            resource_metrics = loaded_resource if resource_metrics is None else resource_metrics
            resource_facts = loaded_facts if resource_facts is None else resource_facts
        else:
            vm_metrics = vm_metrics or {}
            node_metrics = node_metrics or {}
            resource_metrics = resource_metrics or vm_metrics or {}
            resource_facts = resource_facts or {}
            monitor_stats = {}
    else:
        resource_metrics = resource_metrics or vm_metrics or {}
        resource_facts = resource_facts or {}
        monitor_stats = {}

    resource_graph = build_resource_graph(buckets)
    cost_history = daily_rate_by_service(db, sub, days=14) if engine_version == "extended" else {}
    vm_ids = [(vm.get("id") or "") for vm in buckets.get("vms") or [] if vm.get("id")]
    resource_cost_histories = (
        resource_daily_cost_histories(db, sub, vm_ids, days=28)
        if engine_version == "extended" and vm_ids else {}
    )
    utilization_trends = (
        batch_utilization_trends(
            db,
            sub,
            collect_resource_ids_from_buckets(buckets),
            metrics=["avg_cpu_pct", "storage_pct"],
        )
        if engine_version == "extended" else {}
    )
    workload_classes = (
        classify_workloads_for_buckets(buckets, resource_facts)
        if engine_version == "extended" else {}
    )
    advisor_vm_targets = {}
    advisor_by_resource: dict[str, list[Any]] = {}
    if engine_version == "extended":
        from app.advisor_vm_targets import load_advisor_vm_targets
        from app.assessment.advisor_bridge import index_advisor_by_resource

        advisor_vm_targets = load_advisor_vm_targets(db, sub)
        advisor_by_resource = index_advisor_by_resource(db, sub)
    if engine_version == "extended":
        from app.demand_forecaster import batch_forecasts

        demand_forecasts = batch_forecasts(
            db,
            sub,
            collect_resource_ids_from_buckets(buckets),
            metrics=["avg_cpu_pct", "storage_pct"],
        )
        for rid, metric_map in demand_forecasts.items():
            for metric_name, forecast in metric_map.items():
                utilization_trends.setdefault(rid, {}).setdefault(metric_name, {}).update({
                    "projected_4w": forecast.get("projected_4w"),
                    "growth_rate_per_week": forecast.get("slope_per_week"),
                    "forecast_trend": forecast.get("trend"),
                    "downsize_allowed": forecast.get("downsize_allowed", True),
                })

    if engine_version == "extended":
        result = eng.analyze(
            subscription_id=sub,
            vms=buckets.get("vms", []),
            vmss=buckets.get("vmss", []),
            disks=buckets.get("disks", []),
            snapshots=buckets.get("snapshots", []),
            aks_clusters=buckets.get("aks_clusters", []),
            aks_node_pools=aks_node_pools,
            storage=buckets.get("storage", []),
            public_ips=buckets.get("public_ips", []),
            load_balancers=buckets.get("load_balancers", []),
            app_gateways=buckets.get("app_gateways", []),
            app_services=buckets.get("app_services", []),
            app_service_plans=buckets.get("app_service_plans", []),
            network_interfaces=buckets.get("network_interfaces", []),
            nat_gateways=buckets.get("nat_gateways", []),
            redis_caches=buckets.get("redis_caches", []),
            sql_databases=buckets.get("sql_databases", []),
            cosmosdb=buckets.get("cosmosdb", []),
            postgresql=buckets.get("postgresql", []),
            keyvaults=buckets.get("keyvaults", []),
            nsgs=buckets.get("nsgs", []),
            container_registries=buckets.get("container_registries", []),
            log_analytics_workspaces=buckets.get("log_analytics_workspaces", []),
            app_insights_components=buckets.get("app_insights_components", []),
            apim_services=buckets.get("apim_services", []),
            data_factories=buckets.get("data_factories", []),
            logic_apps=buckets.get("logic_apps", []),
            event_hubs=buckets.get("event_hubs", []),
            service_bus_namespaces=buckets.get("service_bus_namespaces", []),
            databricks_workspaces=buckets.get("databricks_workspaces", []),
            synapse_workspaces=buckets.get("synapse_workspaces", []),
            adx_clusters=buckets.get("adx_clusters", []),
            ml_workspaces=buckets.get("ml_workspaces", []),
            recovery_vaults=buckets.get("recovery_vaults", []),
            cognitive_search_services=buckets.get("cognitive_search_services", []),
            firewalls=buckets.get("firewalls", []),
            cdn_profiles=buckets.get("cdn_profiles", []),
            expressroute_circuits=buckets.get("expressroute_circuits", []),
            traffic_managers=buckets.get("traffic_managers", []),
            front_doors=buckets.get("front_doors", []),
            vnets=buckets.get("vnets", []),
            private_endpoints=buckets.get("private_endpoints", []),
            private_link_services=buckets.get("private_link_services", []),
            private_dns_zones=buckets.get("private_dns_zones", []),
            vm_metrics=vm_metrics,
            node_metrics=node_metrics,
            resource_metrics=resource_metrics,
            resource_facts=resource_facts,
            cost_by_resource=cost_by_resource,
            budgets=budgets,
            subscription_spend_usd=subscription_spend,
            resource_graph=resource_graph,
            cost_history=cost_history,
            resource_cost_histories=resource_cost_histories,
            utilization_trends=utilization_trends,
            workload_classes=workload_classes,
            advisor_vm_targets=advisor_vm_targets,
            advisor_by_resource=advisor_by_resource,
            db=db,
            scoped_canonical_types=scoped_canonical_types,
        )
        result["metrics_context"] = analysis_metrics_summary(
            vm_metrics, node_metrics, resource_metrics, resource_facts, monitor_stats,
        )
        result["findings"] = assign_action_chains(
            result.get("findings") or [],
            resource_graph,
            disk_snapshot_links=build_disk_snapshot_links(buckets.get("snapshots") or []),
        )
        result["summary"] = summarize_findings(
            result["findings"],
            engine_version,
            metrics_context=result.get("metrics_context"),
        )
        return result

    result = eng.analyze(
        vms=buckets.get("vms", []),
        disks=buckets.get("disks", []),
        snapshots=buckets.get("snapshots", []),
        aks_clusters=buckets.get("aks_clusters", []),
        aks_node_pools=aks_node_pools,
        storage=buckets.get("storage", []),
        public_ips=buckets.get("public_ips", []),
        load_balancers=buckets.get("load_balancers", []),
        app_gateways=buckets.get("app_gateways", []),
        app_services=buckets.get("app_services", []),
        app_service_plans=buckets.get("app_service_plans", []),
        network_interfaces=buckets.get("network_interfaces", []),
        nat_gateways=buckets.get("nat_gateways", []),
        redis_caches=buckets.get("redis_caches", []),
        sql_servers=buckets.get("sql_servers", []),
        sql_databases=buckets.get("sql_databases", []),
        cosmosdb=buckets.get("cosmosdb", []),
        keyvaults=buckets.get("keyvaults", []),
        expressroute_circuits=buckets.get("expressroute_circuits", []),
        traffic_managers=buckets.get("traffic_managers", []),
        front_doors=buckets.get("front_doors", []),
        cdn_profiles=buckets.get("cdn_profiles", []),
        vm_metrics=vm_metrics,
        cost_by_resource=cost_by_resource,
        budgets=budgets,
    )
    result["engine_version"] = "standard"
    result["metrics_context"] = analysis_metrics_summary(
        vm_metrics, node_metrics, resource_metrics, resource_facts,
    )
    return result


def filter_buckets(full: dict[str, list], bucket_keys: list[str]) -> dict[str, list]:
    """Return a bucket dict containing only the requested keys (others empty)."""
    base = empty_buckets()
    for key in bucket_keys:
        if key in base:
            base[key] = list(full.get(key) or [])
    return base


def filter_buckets_by_resource_ids(
    buckets: dict[str, list],
    resource_ids: list[str] | set[str],
) -> dict[str, list]:
    """Keep only inventory rows whose ARM id is in ``resource_ids``."""
    want = {normalize_arm_id(rid) for rid in resource_ids if rid}
    if not want:
        return empty_buckets()
    filtered = empty_buckets()
    for key, rows in buckets.items():
        filtered[key] = [
            row for row in (rows or [])
            if normalize_arm_id(row.get("id") or row.get("resource_id") or "") in want
        ]
    return filtered


def bucket_keys_for_canonical_types(types: set[str] | list[str]) -> list[str]:
    """Analysis bucket keys for a scoped canonical-type list."""
    keys: list[str] = []
    for ct in types:
        key = TYPE_TO_BUCKET.get((ct or "").strip().lower())
        if key and key != "budgets" and key not in keys:
            keys.append(key)
    return keys


def run_db_analysis(
    db: Session,
    *,
    subscription_id: str,
    profile: str = "default",
    engine_version: str = "extended",
    rule_overrides: dict | None = None,
    scope_components: list[str] | None = None,
    scope_resource_types: list[str] | None = None,
    scope_resource_ids: list[str] | None = None,
    progress_callback: Callable[[int, str | None], None] | None = None,
    include_ai: bool = True,
    fetch_monitor_metrics: bool = True,
) -> dict[str, Any]:
    """
    Analyze synced database inventory, persist findings, and update resource rows.
    Runs the full engine in one pass (no per-component throttling).
    Returns the same shape as live analyze for API/UI compatibility.

    When ``fetch_monitor_metrics`` is False, reuses cached utilization facts from
    prior runs (rule-config refresh — no Azure Monitor API calls).
    """
    sub = subscription_id.lower()
    scope_components = [c for c in (scope_components or []) if c]
    scoped_types = [t.strip().lower() for t in (scope_resource_types or []) if t and t.strip()]
    scoped_resource_ids = [
        rid.strip() for rid in (scope_resource_ids or []) if rid and rid.strip()
    ]
    scoped = bool(scoped_types) or bool(scoped_resource_ids) or (
        bool(scope_components) and len(resolve_batches(scope_components)) < len(ANALYSIS_BATCHES)
    )

    from app.optimizer.analysis_routing import unified_recommendation_mode

    if unified_recommendation_mode() and not scoped and not scoped_types:
        from app.pipeline.orchestrator import pipeline_enabled
        from app.pipeline.unified_recommendations import run_analysis_via_unified_pipeline

        if pipeline_enabled():
            return run_analysis_via_unified_pipeline(
                db,
                subscription_id=sub,
                profile=profile,
                engine_version=engine_version,
                progress_callback=progress_callback,
            )

        log.info(
            "analysis.legacy_fallback",
            subscription_id=sub,
            reason="assessment_pipeline_disabled",
        )

    def _progress(pct: int, component: str | None = None) -> None:
        if progress_callback:
            progress_callback(pct, component)

    _progress(5, "Loading inventory")
    db_overrides = get_effective_config(db, profile)
    merged_overrides = {**db_overrides, **(rule_overrides or {})}
    rule_only_overrides, inline_global = split_rule_overrides(merged_overrides)
    global_config = {**get_global_engine_config(db, profile), **inline_global}

    from concurrent.futures import ThreadPoolExecutor
    from app.database import SessionLocal

    def _load_inventory_bundle() -> tuple[dict[str, list], dict[str, int], dict[str, list]]:
        session = SessionLocal()
        try:
            if scoped_types:
                bucket_keys = bucket_keys_for_canonical_types(scoped_types)
                loaded_buckets, aks_pools = load_buckets_for_keys(
                    session, sub, bucket_keys, global_config=global_config, parallel=True,
                )
                counts = {k: len(v) for k, v in loaded_buckets.items() if v}
                return loaded_buckets, counts, aks_pools
            if scoped:
                bucket_keys: list[str] = []
                for batch in resolve_batches(scope_components):
                    for key in batch.get("buckets") or []:
                        if key != "budgets" and key not in bucket_keys:
                            bucket_keys.append(key)
                loaded_buckets, aks_pools = load_buckets_for_keys(
                    session, sub, bucket_keys, global_config=global_config, parallel=True,
                )
                counts = {k: len(v) for k, v in loaded_buckets.items() if v}
                return loaded_buckets, counts, aks_pools
            return load_inventory_from_db(session, sub, global_config=global_config, parallel=True)
        finally:
            session.close()

    def _load_budgets() -> list[dict]:
        session = SessionLocal()
        try:
            return load_budgets_from_db(session, sub)
        finally:
            session.close()

    def _load_costs() -> dict[str, float]:
        session = SessionLocal()
        try:
            return load_cost_by_resource_from_db(session, sub)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=3) as pool:
        inv_future = pool.submit(_load_inventory_bundle)
        budget_future = pool.submit(_load_budgets)
        cost_future = pool.submit(_load_costs)
        buckets, inventory_counts, aks_node_pools = inv_future.result()
        budgets = budget_future.result()
        cost_by_resource = cost_future.result()

    buckets = filter_bucket_dict(buckets, global_config)
    scoped_type_set = {t.strip().lower() for t in scoped_types if t}
    buckets = filter_buckets_for_legacy_analysis(
        buckets,
        preserve_canonical_types=scoped_type_set or None,
    )
    if scoped_resource_ids:
        buckets = filter_buckets_by_resource_ids(buckets, scoped_resource_ids)
        want_ids = {normalize_arm_id(rid) for rid in scoped_resource_ids}
        aks_node_pools = {
            key: pools
            for key, pools in (aks_node_pools or {}).items()
            if normalize_arm_id(key) in want_ids
        }
    inventory_counts = {k: len(v) for k, v in buckets.items() if v}

    total_resources = sum(len(v) for v in buckets.values())

    log.info(
        "analysis.inventory_loaded",
        subscription_id=sub,
        scoped_types=sorted(scoped_type_set) if scoped_type_set else None,
        total_resources=total_resources,
        bucket_counts=inventory_counts,
    )

    if not legacy_analysis_has_work(buckets, budgets=budgets, scoped_canonical_types=scoped_type_set or None):
        from app.optimizer.analysis_routing import integrated_sub_engines_enabled

        if not integrated_sub_engines_enabled():
            log.info(
                "analysis.skipped_indexed_only",
                subscription_id=sub,
                message="All inventory types are handled by the assessment pipeline.",
            )
            empty_result: dict[str, Any] = {
                "summary": {
                    "total_findings": 0,
                    "total_estimated_monthly_savings_usd": 0.0,
                    "by_severity": {},
                },
                "findings": [],
                "data_source": "db",
                "analysis_trigger": "skipped_assessment_pipeline_primary",
                "coverage_note": (
                    "Per-resource legacy analysis skipped — indexed types are handled by "
                    "the assessment pipeline. Run the pipeline for resource recommendations."
                ),
            }
            run_id = persist_optimization_run(
                db,
                subscription_id=sub,
                profile=profile,
                engine_version=engine_version,
                result=empty_result,
                data_source="db",
            )
            empty_result["run_id"] = run_id
            return empty_result
        raise ValueError(
            "No resources in the database for this subscription. "
            "Run Sync from Azure first, then run analysis again."
        )

    _progress(20, "Loading costs")

    monitor_stats: dict[str, Any] = {}
    if fetch_monitor_metrics:
        vm_metrics, node_metrics, resource_metrics, resource_facts, monitor_stats = load_analysis_metrics(
            db,
            buckets=buckets,
            cost_by_resource=cost_by_resource,
            fetch_monitor_metrics=True,
            rule_overrides=rule_only_overrides,
        )
    else:
        vm_metrics, node_metrics, resource_metrics, resource_facts, monitor_stats = load_analysis_metrics(
            db,
            buckets=buckets,
            cost_by_resource=cost_by_resource,
            fetch_monitor_metrics=False,
            rule_overrides=rule_only_overrides,
        )
        cached_facts = load_cached_resource_facts(db, sub)
        for rid, facts in cached_facts.items():
            merged = dict(resource_facts.get(rid) or {})
            merged.update(facts)
            resource_facts[rid] = merged
        monitor_stats = {
            "source": "cached_findings",
            "loaded": len(cached_facts),
            "requested": 0,
        }
    _progress(45, "Loading metrics")

    engine_version = engine_version.lower()
    if engine_version not in {"standard", "extended"}:
        raise ValueError("engine_version must be 'standard' or 'extended'")

    _progress(55, "Running analysis")

    result = run_engine_on_buckets(
        db,
        subscription_id=sub,
        buckets=buckets,
        aks_node_pools=aks_node_pools,
        cost_by_resource=cost_by_resource,
        budgets=budgets,
        profile=profile,
        engine_version=engine_version,
        rule_overrides=rule_overrides,
        vm_metrics=vm_metrics,
        node_metrics=node_metrics,
        resource_metrics=resource_metrics,
        resource_facts=resource_facts,
        load_metrics=False,
        include_ai=False,
        scoped_canonical_types=list(scoped_type_set) if scoped_type_set else None,
    )
    _progress(80, "Saving results")

    result = append_cost_export_findings(
        db,
        sub,
        result,
        profile=profile,
        rule_overrides=rule_overrides,
        engine_version=engine_version,
    )

    if engine_version == "extended" and buckets.get("vms") and legacy_sub_engines_enabled():
        from app.commitment_findings import dedupe_commitment_findings
        from app.vm_sizing_persist import supplement_vm_rightsizing_findings

        merged_overrides = {**get_effective_config(db, profile), **(rule_overrides or {})}
        findings = supplement_vm_rightsizing_findings(
            result.get("findings") or [],
            subscription_id=sub,
            vms=buckets.get("vms") or [],
            vm_metrics=vm_metrics or {},
            cost_by_resource=cost_by_resource,
            rule_overrides=merged_overrides,
        )
        findings = dedupe_commitment_findings(findings)
        result["findings"] = findings
        result["summary"] = summarize_findings(
            findings,
            engine_version,
            metrics_context=result.get("metrics_context"),
        )
    elif engine_version == "extended":
        from app.commitment_findings import dedupe_commitment_findings

        findings = dedupe_commitment_findings(result.get("findings") or [])
        if findings is not result.get("findings"):
            result["findings"] = findings
            result["summary"] = summarize_findings(
                findings,
                engine_version,
                metrics_context=result.get("metrics_context"),
            )

    if engine_version == "extended":
        from app.recommendation_execution import escalate_persisted_findings_after_execution

        escalated = escalate_persisted_findings_after_execution(db, result.get("findings") or [])
        if escalated is not result.get("findings"):
            result["findings"] = escalated
            result["summary"] = summarize_findings(
                escalated,
                engine_version,
                metrics_context=result.get("metrics_context"),
            )

    scope_types = scoped_types or (resource_types_for_components(scope_components) if scoped else None)
    scope_ids = (
        {normalize_arm_id(rid) for rid in scoped_resource_ids}
        if scoped_resource_ids
        else None
    )
    run_id = persist_optimization_run(
        db,
        subscription_id=sub,
        profile=profile,
        engine_version=engine_version,
        result=result,
        data_source="db",
        scope_resource_types=scope_types,
        scope_resource_ids=scope_ids,
    )

    history_rows = persist_utilization_snapshot(
        db,
        sub,
        buckets,
        resource_facts=resource_facts,
    )
    if history_rows:
        db.commit()

    try:
        from app.topology_discovery import discover_dependencies
        discover_dependencies(db, sub)
    except Exception as exc:
        log.warning("topology_discovery_failed", error=str(exc)[:200])

    from app.perf_cache import invalidate_subscription
    invalidate_subscription(sub)

    result["run_id"] = run_id
    result["utilization_history_persisted"] = history_rows
    result["data_source"] = "db"
    result["analysis_trigger"] = "rule_config" if not fetch_monitor_metrics else "full"
    result["superseded_findings"] = 0
    result["resources_analyzed"] = inventory_counts
    result["inventory_total"] = total_resources
    result["coverage_note"] = (
        "Analysis used synced database inventory. "
        f"Resource types in DB: {', '.join(sorted(inventory_counts.keys()))}."
    )
    if not fetch_monitor_metrics:
        result["coverage_note"] += (
            " Rule refresh reused cached monitor facts from prior runs (no Azure fetch)."
        )
    elif result.get("metrics_context"):
        ctx = result["metrics_context"]
        sources = ctx.get("sources") or []
        if sources:
            result["coverage_note"] += (
                f" Performance signals: {', '.join(sources)} "
                f"({ctx.get('monitor_metrics_count', 0)} resources with monitor data, "
                f"{ctx.get('monitor_facts_count', 0)} with extracted utilization facts, "
                f"{ctx.get('node_metrics_count', 0)} K8s nodes)."
            )
    return result


def run_resource_db_analysis(
    db: Session,
    *,
    subscription_id: str,
    resource_id: str,
    profile: str = "default",
    engine_version: str = "extended",
    rule_overrides: dict | None = None,
    include_ai: bool = False,
    fetch_monitor_metrics: bool = True,
) -> dict[str, Any]:
    """Analyze one synced inventory resource and persist findings scoped to that resource."""
    from app.inventory_standalone import (
        EMBEDDED_VMSS_ANALYSIS_MESSAGE,
        is_managed_aks_vmss,
        resolve_aks_cluster_for_embedded_vmss,
    )
    from app.models import ResourceSnapshot

    rid = normalize_arm_id(resource_id)
    if not rid:
        raise ValueError("resource_id is required")

    sub = subscription_id.lower()
    canonical_type: str | None = None
    for row in (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.is_cost_export_only.is_(False),
        )
        .all()
    ):
        if normalize_arm_id(row.resource_id or "") != rid:
            continue
        canonical_type = (row.resource_type or "").strip().lower() or None
        break

    if not canonical_type:
        canonical_type = internal_resource_type(rid).strip().lower()

    if is_managed_aks_vmss(rid, canonical_type):
        parent_cluster_id = resolve_aks_cluster_for_embedded_vmss(db, sub, rid)
        if not parent_cluster_id:
            raise ValueError(EMBEDDED_VMSS_ANALYSIS_MESSAGE)
        log.info(
            "resource_analyze_redirected_from_vmss",
            subscription_id=sub,
            vmss_resource_id=rid,
            parent_cluster_id=parent_cluster_id,
        )
        rid = parent_cluster_id
        canonical_type = "containers/aks"

    if not canonical_type or canonical_type.startswith("other/"):
        raise ValueError(
            "Resource is not in synced inventory. Sync from Azure first, then open the resource again."
        )

    return run_db_analysis(
        db,
        subscription_id=sub,
        profile=profile,
        engine_version=engine_version,
        rule_overrides=rule_overrides,
        scope_resource_types=[canonical_type],
        scope_resource_ids=[rid],
        include_ai=include_ai,
        fetch_monitor_metrics=fetch_monitor_metrics,
    )

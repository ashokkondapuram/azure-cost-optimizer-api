"""DB-first optimization analysis — reads synced inventory and writes recommendations back."""
from __future__ import annotations

import json
import uuid
import structlog
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.analysis_persist import close_open_findings, persist_optimization_run
from app.cost_db import resource_cost_map_from_db
from app.optimizer.engine_config import get_effective_config
from app.optimizer.unified_engine import append_cost_export_findings
from app.models import BudgetSnapshot
from app.optimizer.engine import OptimizationEngine
from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.metrics_loader import (
    analysis_metrics_summary,
    load_analysis_metrics,
    load_cached_resource_facts,
)
from app.resource_store import list_all_resources_db, list_resources_by_types_db
from app.resource_type_map import arm_provider_type
from app.analysis.orchestrator import bucket_keys_for_canonical_types

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
}

# Engine bucket → canonical types (for per-batch DB loads)
BUCKET_TO_TYPES: dict[str, list[str]] = {}
for _canonical, _bucket in TYPE_TO_BUCKET.items():
    BUCKET_TO_TYPES.setdefault(_bucket, []).append(_canonical)


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


def load_inventory_from_db(db: Session, subscription_id: str) -> tuple[dict[str, list], dict[str, int], dict[str, list]]:
    """Load all active resources and group them for the optimization engine."""
    subscription_id = subscription_id.lower()
    rows = list_all_resources_db(db, subscription_id)
    buckets = empty_buckets()
    counts: dict[str, int] = {}

    for row in rows:
        canonical = row.get("type") or ""
        counts[canonical] = counts.get(canonical, 0) + 1
        bucket = TYPE_TO_BUCKET.get(canonical)
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

    for row in list_resources_by_types_db(db, sub, types):
        canonical = row.get("type") or ""
        bucket = TYPE_TO_BUCKET.get(canonical)
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
) -> dict[str, Any]:
    """Run optimization engine on a (possibly partial) resource bucket set."""
    sub = subscription_id.lower()
    subscription_spend = sum(
        float(v) if not isinstance(v, dict) else float(v.get("usd") or v.get("pretax") or 0)
        for v in cost_by_resource.values()
    )
    db_overrides = get_effective_config(db, profile)
    merged_overrides = {**db_overrides, **(rule_overrides or {})}
    engine_version = engine_version.lower()
    eng = (
        ExtendedOptimizationEngine(rule_overrides=merged_overrides)
        if engine_version == "extended"
        else OptimizationEngine(rule_overrides=merged_overrides)
    )

    if vm_metrics is None or node_metrics is None or resource_metrics is None:
        if load_metrics:
            loaded_vm, loaded_node, loaded_resource, loaded_facts, monitor_stats = load_analysis_metrics(
                db,
                buckets=buckets,
                cost_by_resource=cost_by_resource,
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
            vm_metrics=vm_metrics,
            node_metrics=node_metrics,
            resource_metrics=resource_metrics,
            resource_facts=resource_facts,
            cost_by_resource=cost_by_resource,
            budgets=budgets,
            subscription_spend_usd=subscription_spend,
        )
        result["metrics_context"] = analysis_metrics_summary(
            vm_metrics, node_metrics, resource_metrics, resource_facts, monitor_stats,
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
        vm_metrics=vm_metrics,
        cost_by_resource=cost_by_resource,
        budgets=budgets,
    )
    result["engine_version"] = "standard"
    result["metrics_context"] = analysis_metrics_summary(
        vm_metrics, node_metrics, resource_metrics, resource_facts,
    )
    return result


from app.analysis_summary import merge_analysis_results, summarize_findings
from app.optimizer.component_map import ANALYSIS_BATCHES, resolve_batches, resource_types_for_components
def filter_buckets(full: dict[str, list], bucket_keys: list[str]) -> dict[str, list]:
    """Return a bucket dict containing only the requested keys (others empty)."""
    base = empty_buckets()
    for key in bucket_keys:
        if key in base:
            base[key] = list(full.get(key) or [])
    return base


def run_db_analysis(
    db: Session,
    *,
    subscription_id: str,
    profile: str = "default",
    engine_version: str = "extended",
    rule_overrides: dict | None = None,
    scope_components: list[str] | None = None,
    scope_resource_types: list[str] | None = None,
    progress_callback: Callable[[int, str | None], None] | None = None,
    fetch_monitor_metrics: bool = True,
) -> dict[str, Any]:
    """
    Analyze synced database inventory, persist findings, and update resource rows.
    Runs the full engine in one pass (no per-component throttling).
    Returns the same shape as live analyze for API/UI compatibility.

    When ``fetch_monitor_metrics`` is False, reuses cached utilization facts from
    prior runs (metrics already synced — no Azure Monitor API calls).
    """
    sub = subscription_id.lower()
    scope_components = [c for c in (scope_components or []) if c]
    scoped_types = [t.strip().lower() for t in (scope_resource_types or []) if t and t.strip()]
    scoped = bool(scoped_types) or (
        bool(scope_components) and len(resolve_batches(scope_components)) < len(ANALYSIS_BATCHES)
    )

    def _progress(pct: int, component: str | None = None) -> None:
        if progress_callback:
            progress_callback(pct, component)

    _progress(5, "Loading inventory")
    if scoped_types:
        bucket_keys = bucket_keys_for_canonical_types(scoped_types)
        buckets, aks_node_pools = load_buckets_for_keys(db, sub, bucket_keys)
        inventory_counts = {k: len(v) for k, v in buckets.items() if v}
    elif scoped:
        bucket_keys: list[str] = []
        for batch in resolve_batches(scope_components):
            for key in batch.get("buckets") or []:
                if key != "budgets" and key not in bucket_keys:
                    bucket_keys.append(key)
        buckets, aks_node_pools = load_buckets_for_keys(db, sub, bucket_keys)
        inventory_counts = {k: len(v) for k, v in buckets.items() if v}
    else:
        buckets, inventory_counts, aks_node_pools = load_inventory_from_db(db, sub)

    total_resources = sum(len(v) for v in buckets.values())
    budgets = load_budgets_from_db(db, sub)

    if total_resources == 0 and not budgets:
        raise ValueError(
            "No resources in the database for this subscription. "
            "Run Sync from Azure first, then run analysis again."
        )

    cost_by_resource = load_cost_by_resource_from_db(db, sub)
    _progress(20, "Loading costs")

    vm_metrics, node_metrics, resource_metrics, resource_facts, _monitor_stats = load_analysis_metrics(
        db,
        buckets=buckets,
        cost_by_resource=cost_by_resource,
        fetch_monitor_metrics=fetch_monitor_metrics,
    )
    if not fetch_monitor_metrics:
        cached_facts = load_cached_resource_facts(db, sub)
        for rid, facts in cached_facts.items():
            merged = dict(resource_facts.get(rid) or {})
            merged.update(facts)
            resource_facts[rid] = merged
    _progress(45, "Loading metrics")

    engine_version = engine_version.lower()
    if engine_version not in {"standard", "extended"}:
        raise ValueError("engine_version must be 'standard' or 'extended'")

    from app.messaging.data_collector import get_collector

    collector = get_collector()
    if collector is None:
        close_open_findings(db, sub, components=scope_components if scoped else None)
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
    )
    _progress(80, "Saving results")

    if not scoped:
        result = append_cost_export_findings(
            db,
            sub,
            result,
            profile=profile,
            rule_overrides=rule_overrides,
            engine_version=engine_version,
        )

    scope_types = scoped_types or (resource_types_for_components(scope_components) if scoped else None)

    collector = get_collector()
    if collector is not None:
        collector.add_section(
            "analysis",
            {
                "result": result,
                "profile": profile,
                "engine_version": engine_version,
                "scope_components": scope_components,
                "scope_resource_types": list(scope_types) if scope_types else None,
            },
        )
        result["run_id"] = str(uuid.uuid4())
        result["data_source"] = "db"
        result["analysis_trigger"] = "rule_config" if not fetch_monitor_metrics else "full"
        result["superseded_findings"] = 0
        result["resources_analyzed"] = inventory_counts
        result["inventory_total"] = total_resources
        return result

    run_id = persist_optimization_run(
        db,
        subscription_id=sub,
        profile=profile,
        engine_version=engine_version,
        result=result,
        data_source="db",
        scope_resource_types=scope_types,
    )

    result["run_id"] = run_id
    result["data_source"] = "db"
    result["superseded_findings"] = 0
    result["resources_analyzed"] = inventory_counts
    result["inventory_total"] = total_resources
    result["analysis_trigger"] = "rule_config" if not fetch_monitor_metrics else "full"
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

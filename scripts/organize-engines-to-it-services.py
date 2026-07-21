#!/usr/bin/env python3
"""Move resource-specific sub-engines into it_services/<pkg>/engine/.

Platform-only code stays under app/optimizer/platform/.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import textwrap
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_JSON = ROOT / "packages" / "costoptimizer-core" / "service_registry.json"
PLATFORM_RUNTIME = ROOT / "app" / "optimizer" / "platform" / "runtime"
LEGACY_RUNTIME = ROOT / "app" / "optimizer" / "resource_engines" / "runtime"

RUNTIME_IMPORT_OLD = "app.optimizer.resource_engines.runtime"
RUNTIME_IMPORT_NEW = "app.optimizer.platform.runtime"

# service_id -> copy entire engine directory from app/optimizer/resource_engines/...
DEDICATED_ENGINE_DIRS: dict[str, str] = {
    "compute-vm": "compute/vm",
    "compute-vmss": "compute/vmss",
    "compute-disk": "compute/disk",
    "compute-snapshot": "compute/snapshot",
    "containers-aks": "containers/aks",
    "containers-acr": "containers/acr",
    "appservice-webapp": "appservice/webapp",
    "storage-account": "storage/account",
    "network-publicip": "network/publicip",
    "network-nic": "network/nic",
    "network-nat": "network/nat",
    "network-nsg": "network/nsg",
    "network-loadbalancer": "network/loadbalancer",
    "network-appgateway": "network/appgateway",
    "database-sql": "database/sql",
    "database-postgresql": "database/postgresql",
    "database-cosmosdb": "database/cosmos",
    "database-redis": "database/redis",
    "security-keyvault": "security/keyvault",
    "backup-recoveryvault": "backup",
    "search-cognitivesearch": "search",
}

# Split one analysis module into per-service functions
SPLIT_ANALYSIS: dict[str, dict[str, str]] = {
    "analytics/analysis.py": {
        "analyze_databricks": "analytics-databricks",
        "analyze_synapse": "analytics-synapse",
        "analyze_adx": "analytics-adx",
        "analyze_ml_workspaces": "analytics-mlworkspace",
    },
    "integration/analysis.py": {
        "analyze_apim": "integration-apim",
        "analyze_data_factories": "integration-datafactory",
        "analyze_logic_apps": "integration-logicapp",
    },
    "messaging/analysis.py": {
        "analyze_event_hubs": "messaging-eventhub",
        "analyze_service_bus": "messaging-servicebus",
    },
    "monitoring/analysis.py": {
        "analyze_log_analytics": "monitoring-loganalytics",
        "analyze_app_insights": "monitoring-appinsights",
    },
    "networking/analysis.py": {
        "analyze_firewalls": "network-firewall",
        "analyze_cdn_profiles": "network-cdn",
        "analyze_vnets": "network-vnet",
        "analyze_private_endpoints": "network-privateendpoint",
        "analyze_private_link_services": "network-privatelinkservice",
        "analyze_private_dns_zones": "network-privatedns",
    },
}

# Per-service sub-engine registration metadata
SUB_ENGINE_META: dict[str, dict[str, Any]] = {
    "compute-vm": {"class": "VmSubEngine", "component": "Virtual Machines", "buckets": ("vms",), "analyze_fn": "analyze_vms", "bucket_arg": "vms"},
    "compute-vmss": {
        "class": "VmssSubEngine",
        "component": "Virtual Machine Scale Sets",
        "buckets": ("vmss",),
        "dedicated_sub_engine": True,
    },
    "compute-disk": {"class": "DiskSubEngine", "component": "Managed Disks", "buckets": ("disks",), "analyze_fn": "analyze_disks", "bucket_arg": "disks"},
    "compute-snapshot": {"class": "SnapshotSubEngine", "component": "Disk Snapshots", "buckets": ("snapshots",), "analyze_fn": "analyze_snapshots", "bucket_arg": "snapshots"},
    "containers-aks": {
        "class": "AksSubEngine",
        "component": "AKS",
        "buckets": ("aks_clusters",),
        "dedicated_sub_engine": True,
    },
    "containers-acr": {"class": "AcrSubEngine", "component": "Container Registry", "buckets": ("container_registries",), "analyze_fn": "analyze_acr", "bucket_arg": "container_registries"},
    "appservice-webapp": {
        "class": "AppServiceSubEngine",
        "component": "App Service",
        "buckets": ("app_services", "app_service_plans"),
        "dedicated_sub_engine": True,
    },
    "storage-account": {"class": "StorageSubEngine", "component": "Storage Accounts", "buckets": ("storage",), "analyze_fn": "analyze_storage", "bucket_arg": "storage"},
    "network-publicip": {"class": "PublicIpSubEngine", "component": "Public IPs", "buckets": ("public_ips",), "analyze_fn": "analyze_public_ips", "bucket_arg": "public_ips"},
    "network-nic": {"class": "NicSubEngine", "component": "Network Interfaces", "buckets": ("network_interfaces",), "analyze_fn": "analyze_network_interfaces", "bucket_arg": "network_interfaces", "cost_optional": True},
    "network-nat": {"class": "NatSubEngine", "component": "NAT Gateways", "buckets": ("nat_gateways",), "analyze_fn": "analyze_nat_gateways", "bucket_arg": "nat_gateways"},
    "network-nsg": {"class": "NsgSubEngine", "component": "Network Security Groups", "buckets": ("nsgs",), "analyze_fn": "analyze_nsgs", "bucket_arg": "nsgs"},
    "network-loadbalancer": {"class": "LoadBalancerSubEngine", "component": "Load Balancers", "buckets": ("load_balancers",), "analyze_fn": "analyze_load_balancers", "bucket_arg": "load_balancers"},
    "network-appgateway": {"class": "AppGatewaySubEngine", "component": "Application Gateways", "buckets": ("app_gateways",), "analyze_fn": "analyze_app_gateways", "bucket_arg": "app_gateways"},
    "database-sql": {
        "class": "SqlSubEngine",
        "component": "SQL Database",
        "buckets": ("sql_servers", "sql_databases"),
        "dedicated_sub_engine": True,
    },
    "database-postgresql": {"class": "PostgresqlSubEngine", "component": "PostgreSQL", "buckets": ("postgresql",), "analyze_fn": "analyze_postgresql", "bucket_arg": "postgresql"},
    "database-cosmosdb": {"class": "CosmosSubEngine", "component": "Cosmos DB", "buckets": ("cosmosdb",), "analyze_fn": "analyze_cosmos", "bucket_arg": "cosmosdb"},
    "database-redis": {"class": "RedisSubEngine", "component": "Redis Cache", "buckets": ("redis_caches",), "analyze_fn": "analyze_redis", "bucket_arg": "redis_caches"},
    "security-keyvault": {"class": "KeyVaultSubEngine", "component": "Key Vault", "buckets": ("keyvaults",), "analyze_fn": "analyze_keyvaults", "bucket_arg": "keyvaults"},
    "backup-recoveryvault": {"class": "BackupSubEngine", "component": "Backup", "buckets": ("recovery_vaults",), "analyze_fn": "analyze_recovery_vaults", "bucket_arg": "recovery_vaults"},
    "search-cognitivesearch": {"class": "SearchSubEngine", "component": "Search", "buckets": ("cognitive_search_services",), "analyze_fn": "analyze_cognitive_search", "bucket_arg": "cognitive_search_services"},
    "analytics-databricks": {"class": "DatabricksSubEngine", "component": "Azure Databricks", "buckets": ("databricks_workspaces",), "analyze_fn": "analyze_databricks", "bucket_arg": "databricks_workspaces"},
    "analytics-synapse": {"class": "SynapseSubEngine", "component": "Azure Synapse", "buckets": ("synapse_workspaces",), "analyze_fn": "analyze_synapse", "bucket_arg": "synapse_workspaces"},
    "analytics-adx": {"class": "AdxSubEngine", "component": "Azure Data Explorer", "buckets": ("adx_clusters",), "analyze_fn": "analyze_adx", "bucket_arg": "adx_clusters"},
    "analytics-mlworkspace": {"class": "MlWorkspaceSubEngine", "component": "Azure ML workspace", "buckets": ("ml_workspaces",), "analyze_fn": "analyze_ml_workspaces", "bucket_arg": "ml_workspaces"},
    "integration-apim": {"class": "ApimSubEngine", "component": "API Management", "buckets": ("apim_services",), "analyze_fn": "analyze_apim", "bucket_arg": "apim_services"},
    "integration-datafactory": {"class": "DataFactorySubEngine", "component": "Data Factory", "buckets": ("data_factories",), "analyze_fn": "analyze_data_factories", "bucket_arg": "data_factories"},
    "integration-logicapp": {"class": "LogicAppSubEngine", "component": "Logic App", "buckets": ("logic_apps",), "analyze_fn": "analyze_logic_apps", "bucket_arg": "logic_apps"},
    "messaging-eventhub": {"class": "EventHubSubEngine", "component": "Event Hubs namespace", "buckets": ("event_hubs",), "analyze_fn": "analyze_event_hubs", "bucket_arg": "event_hubs"},
    "messaging-servicebus": {"class": "ServiceBusSubEngine", "component": "Service Bus namespace", "buckets": ("service_bus_namespaces",), "analyze_fn": "analyze_service_bus", "bucket_arg": "service_bus_namespaces"},
    "monitoring-loganalytics": {"class": "LogAnalyticsSubEngine", "component": "Log Analytics workspace", "buckets": ("log_analytics_workspaces",), "analyze_fn": "analyze_log_analytics", "bucket_arg": "log_analytics_workspaces"},
    "monitoring-appinsights": {"class": "AppInsightsSubEngine", "component": "Application Insights", "buckets": ("app_insights_components",), "analyze_fn": "analyze_app_insights", "bucket_arg": "app_insights_components"},
    "network-firewall": {"class": "FirewallSubEngine", "component": "Azure Firewall", "buckets": ("firewalls",), "analyze_fn": "analyze_firewalls", "bucket_arg": "firewalls"},
    "network-cdn": {"class": "CdnSubEngine", "component": "CDN profile", "buckets": ("cdn_profiles",), "analyze_fn": "analyze_cdn_profiles", "bucket_arg": "cdn_profiles"},
    "network-vnet": {"class": "VnetSubEngine", "component": "Virtual network", "buckets": ("vnets",), "analyze_fn": "analyze_vnets", "bucket_arg": "vnets"},
    "network-privateendpoint": {"class": "PrivateEndpointSubEngine", "component": "Private endpoint", "buckets": ("private_endpoints",), "analyze_fn": "analyze_private_endpoints", "bucket_arg": "private_endpoints"},
    "network-privatelinkservice": {"class": "PrivateLinkServiceSubEngine", "component": "Private link service", "buckets": ("private_link_services",), "analyze_fn": "analyze_private_link_services", "bucket_arg": "private_link_services"},
    "network-privatedns": {"class": "PrivateDnsSubEngine", "component": "Private DNS zone", "buckets": ("private_dns_zones",), "analyze_fn": "analyze_private_dns_zones", "bucket_arg": "private_dns_zones"},
}

PLATFORM_COST_ENGINES = ("cost/budget", "cost/commitments", "cost/anomaly")


def service_pkg(service_id: str) -> str:
    return service_id.replace("-", "_")


def rewrite_engine_imports(text: str, old_engine_prefix: str, pkg: str) -> str:
    text = text.replace(RUNTIME_IMPORT_OLD, RUNTIME_IMPORT_NEW)
    text = text.replace(
        f"app.optimizer.resource_engines.{old_engine_prefix}",
        f"it_services.{pkg}.engine",
    )
    for old, new in (
        ("app.optimizer.resource_engines.compute.vm.", "it_services.compute_vm.engine."),
        ("app.optimizer.resource_engines.compute.vmss.", "it_services.compute_vmss.engine."),
        ("app.optimizer.resource_engines.containers.aks.", "it_services.containers_aks.engine."),
        ("app.optimizer.resource_engines.cost.commitments.", "app.optimizer.platform.cost.commitments."),
    ):
        text = text.replace(old, new)
    return text


def copy_py_files(src_dir: Path, dest_dir: Path, old_prefix: str, pkg: str) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in src_dir.glob("*.py"):
        if src.name == "__init__.py":
            continue
        content = rewrite_engine_imports(src.read_text(encoding="utf-8"), old_prefix, pkg)
        (dest_dir / src.name).write_text(content, encoding="utf-8")
    (dest_dir / "__init__.py").write_text(
        f'"""Optimization engine — owned by {pkg} IT service."""\n',
        encoding="utf-8",
    )


def write_legacy_shim(target: Path, import_path: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f'"""Compatibility shim — implementation: {import_path}"""\n\n'
        "from importlib import import_module\n\n"
        f'_impl = import_module("{import_path}")\n\n\n'
        "def __getattr__(name: str):\n"
        "    return getattr(_impl, name)\n",
        encoding="utf-8",
    )


def extract_function_source(module_path: Path, func_name: str) -> tuple[str, str]:
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    header_lines: list[str] = []
    func_lines: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            segment = lines[node.lineno - 1 : node.end_lineno]
            header_lines.extend(segment)
        elif isinstance(node, ast.FunctionDef) and node.name.startswith("_") and node.name != func_name:
            segment = lines[node.lineno - 1 : node.end_lineno]
            header_lines.extend(segment)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            func_lines = lines[node.lineno - 1 : node.end_lineno]
            break
    if not func_lines:
        raise ValueError(f"Function {func_name} not found in {module_path}")
    return "\n".join(header_lines), "\n".join(func_lines)


def migrate_split_analysis(rel_path: str, mapping: dict[str, str]) -> None:
    src = ROOT / "app" / "optimizer" / "resource_engines" / rel_path
    reexports = []
    for func_name, service_id in mapping.items():
        pkg = service_pkg(service_id)
        dest_dir = ROOT / "it_services" / pkg / "engine"
        dest_dir.mkdir(parents=True, exist_ok=True)
        header, body = extract_function_source(src, func_name)
        header = header.replace(RUNTIME_IMPORT_OLD, RUNTIME_IMPORT_NEW)
        content = f'"""Analysis rules — owned by {service_id} IT service."""\nfrom __future__ import annotations\n\n{header}\n\n\n{body}\n'
        (dest_dir / "analysis.py").write_text(content, encoding="utf-8")
        (dest_dir / "__init__.py").write_text(
            f'"""Optimization engine — owned by {pkg} IT service."""\n',
            encoding="utf-8",
        )
        reexports.append(f"from it_services.{pkg}.engine.analysis import {func_name}")
    shim_lines = [
        f'"""Compatibility aggregate — functions moved to it_services."""',
        *reexports,
        "",
        "__all__ = " + repr(list(mapping.keys())),
    ]
    src.write_text("\n".join(shim_lines) + "\n", encoding="utf-8")


def generate_sub_engine(service_id: str, meta: dict[str, Any]) -> str:
    pkg = service_pkg(service_id)
    class_name = meta["class"]
    component = meta["component"]
    buckets = meta["buckets"]
    analyze_fn = meta["analyze_fn"]
    bucket_arg = meta["bucket_arg"]
    extra_bucket = meta.get("extra_bucket")
    extra_args = meta.get("extra_analyze_args", "")
    cost_optional = meta.get("cost_optional", False)

    cost_arg = "" if cost_optional else ", self.ctx.cost_by_resource"
    extra_analyze = f", {extra_args}" if extra_args else ""
    if extra_bucket:
        analyze_call = (
            f"findings = {analyze_fn}(self.engine, self.ctx.subscription_id, "
            f"resources, buckets.get(\"{extra_bucket}\") or []{cost_arg}{extra_analyze})"
        )
        prepare_second = f'buckets.get("{extra_bucket}") or []'
    else:
        analyze_call = (
            f"findings = {analyze_fn}(self.engine, self.ctx.subscription_id, "
            f"resources{cost_arg}{extra_analyze})"
        )
        prepare_second = None

    if prepare_second:
        enhance_list = f"resources + self.prepare_resources({prepare_second})"
    else:
        enhance_list = "resources"

    return textwrap.dedent(
        f'''
        """Sub-engine — owned by {service_id} IT service."""
        from __future__ import annotations

        from typing import Any

        from app.optimizer.platform.runtime.base import ResourceSubEngine
        from it_services.{pkg}.engine.analysis import {analyze_fn}


        class {class_name}(ResourceSubEngine):
            component = {component!r}
            bucket_keys = {buckets!r}

            def analyze(self, buckets: dict[str, list]) -> list[Any]:
                resources = self.prepare_resources(buckets.get("{bucket_arg}") or [])
                {analyze_call}
                return self.enhance_findings(findings, {enhance_list})
        '''
    ).strip() + "\n"


def migrate_dedicated(service_id: str, rel_dir: str) -> None:
    pkg = service_pkg(service_id)
    src = ROOT / "app" / "optimizer" / "resource_engines" / rel_dir
    dest = ROOT / "it_services" / pkg / "engine"
    if not src.is_dir():
        return
    copy_py_files(src, dest, rel_dir.replace("/", "."), pkg)
    # shims for each file
    for src_file in src.glob("*.py"):
        if src_file.name == "__init__.py":
            continue
        write_legacy_shim(
            src_file,
            f"it_services.{pkg}.engine.{src_file.stem}",
        )


def setup_platform_runtime() -> None:
    PLATFORM_RUNTIME.mkdir(parents=True, exist_ok=True)
    for src in LEGACY_RUNTIME.glob("*.py"):
        dest = PLATFORM_RUNTIME / src.name
        if not dest.exists() or src.name != "__init__.py":
            shutil.copy2(src, dest)
    (PLATFORM_RUNTIME / "__init__.py").write_text(
        '"""Platform runtime for resource sub-engines (resource-independent)."""\n',
        encoding="utf-8",
    )
    # legacy shims
    for name in ("base.py", "context.py", "envelope.py"):
        write_legacy_shim(LEGACY_RUNTIME / name, f"{RUNTIME_IMPORT_NEW}.{name[:-3]}")


def migrate_platform_cost() -> None:
    platform_cost = ROOT / "app" / "optimizer" / "platform" / "cost"
    for rel in PLATFORM_COST_ENGINES:
        src = ROOT / "app" / "optimizer" / "resource_engines" / rel
        dest = platform_cost / rel.split("/", 1)[1]
        if not src.is_dir():
            continue
        copy_py_files(src, dest, rel.replace("/", "."), rel.split("/")[-1])
        for src_file in src.glob("*.py"):
            if src_file.name == "__init__.py":
                continue
            write_legacy_shim(
                src_file,
                f"app.optimizer.platform.cost.{rel.split('/')[-1]}.{src_file.stem}",
            )


def write_engine_catalog() -> None:
    entries = []
    for service_id, meta in sorted(SUB_ENGINE_META.items()):
        entries.append({
            "service_id": service_id,
            "package": service_pkg(service_id),
            "class_name": meta["class"],
            "component": meta["component"],
            "bucket_keys": list(meta["buckets"]),
        })
    catalog_path = ROOT / "it_services" / "_engine_catalog.json"
    catalog_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")

    # Python loader for registry
    lines = [
        '"""Auto-generated sub-engine catalog — run scripts/organize-engines-to-it-services.py."""',
        "from __future__ import annotations",
        "",
        "ENGINE_CATALOG = " + repr(entries),
        "",
    ]
    (ROOT / "it_services" / "_engine_catalog.py").write_text("\n".join(lines), encoding="utf-8")


def write_platform_registry() -> None:
    imports = []
    classes = []
    for service_id, meta in sorted(SUB_ENGINE_META.items()):
        pkg = service_pkg(service_id)
        cls = meta["class"]
        imports.append(f"from it_services.{pkg}.engine.sub_engine import {cls}")
        classes.append(cls)

    imports.extend([
        "from app.optimizer.platform.cost.budget.sub_engine import BudgetSubEngine",
        "from app.optimizer.platform.cost.commitments.sub_engine import CommitmentsSubEngine",
        "from app.optimizer.platform.cost.anomaly.sub_engine import CostAnomalySubEngine",
    ])
    classes.extend(["BudgetSubEngine", "CommitmentsSubEngine", "CostAnomalySubEngine"])

    parallel_groups = _parallel_groups(classes)

    content = f'''"""Platform sub-engine registry — loads per-resource engines from it_services."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.optimizer.component_map import ANALYSIS_BATCHES
from app.optimizer.platform.runtime.base import ResourceSubEngine
from app.optimizer.platform.runtime.context import AnalysisContext

{chr(10).join(imports)}

SUB_ENGINE_CLASSES: tuple[type[ResourceSubEngine], ...] = (
    {", ".join(classes)},
)

SUB_ENGINES_BY_COMPONENT: dict[str, type[ResourceSubEngine]] = {{
    cls.component: cls for cls in SUB_ENGINE_CLASSES
}}

PARALLEL_ENGINE_GROUPS: tuple[tuple[type[ResourceSubEngine], ...], ...] = {parallel_groups}

_PARALLEL_WORKERS = max(1, int(os.getenv("ANALYSIS_ENGINE_WORKERS", "6")))


def list_sub_engines() -> list[dict[str, Any]]:
    batch_components = [b["component"] for b in ANALYSIS_BATCHES]
    out: list[dict[str, Any]] = []
    for cls in SUB_ENGINE_CLASSES:
        out.append({{
            "component": cls.component,
            "bucket_keys": list(cls.bucket_keys),
            "batch_order": batch_components.index(cls.component) if cls.component in batch_components else 99,
        }})
    out.sort(key=lambda row: row["batch_order"])
    return out


def _run_one_engine(cls, engine, ctx, merged):
    sub = cls(engine, ctx)
    return list(sub.analyze(merged))


def run_sub_engines(engine, ctx, buckets, *, budgets=None):
    merged = dict(buckets)
    if budgets is not None:
        merged["budgets"] = budgets
    findings = []
    scheduled = set()
    for group in PARALLEL_ENGINE_GROUPS:
        active = [cls for cls in group if _has_bucket_data(cls.bucket_keys, merged)]
        if not active:
            continue
        scheduled.update(active)
        if len(active) == 1:
            findings.extend(_run_one_engine(active[0], engine, ctx, merged))
            continue
        with ThreadPoolExecutor(max_workers=min(_PARALLEL_WORKERS, len(active))) as pool:
            futures = [pool.submit(_run_one_engine, cls, engine, ctx, merged) for cls in active]
            for future in as_completed(futures):
                findings.extend(future.result())
    for cls in SUB_ENGINE_CLASSES:
        if cls in scheduled:
            continue
        if not _has_bucket_data(cls.bucket_keys, merged):
            continue
        findings.extend(_run_one_engine(cls, engine, ctx, merged))
    return findings


def run_sub_engine_for_component(engine, ctx, component, buckets, *, budgets=None):
    cls = SUB_ENGINES_BY_COMPONENT.get(component)
    if not cls:
        return []
    merged = dict(buckets)
    if budgets is not None:
        merged["budgets"] = budgets
    return cls(engine, ctx).analyze(merged)


def _has_bucket_data(bucket_keys, buckets):
    if bucket_keys == ("budgets",):
        return bool(buckets.get("budgets"))
    return any(buckets.get(key) for key in bucket_keys)
'''
    registry = ROOT / "app" / "optimizer" / "platform" / "sub_engine_registry.py"
    registry.write_text(content, encoding="utf-8")

    shim = ROOT / "app" / "optimizer" / "resource_engines" / "registry.py"
    write_legacy_shim(shim, "app.optimizer.platform.sub_engine_registry")


def _parallel_groups(classes: list[str]) -> str:
    # reuse grouping by prefix — simplified parallel batches
    groups = [
        ("VmSubEngine", "VmssSubEngine", "DiskSubEngine", "SnapshotSubEngine"),
        ("SqlSubEngine", "PostgresqlSubEngine", "RedisSubEngine", "CosmosSubEngine"),
        ("StorageSubEngine",),
        ("AksSubEngine", "AcrSubEngine"),
        ("AppServiceSubEngine",),
        ("PublicIpSubEngine", "NicSubEngine", "NatSubEngine", "NsgSubEngine", "LoadBalancerSubEngine", "AppGatewaySubEngine"),
        ("KeyVaultSubEngine",),
        (
            "LogAnalyticsSubEngine", "AppInsightsSubEngine",
            "ApimSubEngine", "DataFactorySubEngine", "LogicAppSubEngine",
            "EventHubSubEngine", "ServiceBusSubEngine",
            "DatabricksSubEngine", "SynapseSubEngine", "AdxSubEngine", "MlWorkspaceSubEngine",
            "BackupSubEngine", "SearchSubEngine",
        ),
        (
            "FirewallSubEngine", "CdnSubEngine", "VnetSubEngine",
            "PrivateEndpointSubEngine", "PrivateLinkServiceSubEngine", "PrivateDnsSubEngine",
        ),
        ("CommitmentsSubEngine", "CostAnomalySubEngine", "BudgetSubEngine"),
    ]
    present = set(classes)
    out = []
    for group in groups:
        active = tuple(c for c in group if c in present)
        if active:
            out.append(active)
    return repr(out)


def write_analysis_batches() -> None:
    batches = []
    for service_id, meta in sorted(SUB_ENGINE_META.items(), key=lambda x: x[1]["component"]):
        batches.append({
            "component": meta["component"],
            "buckets": list(meta["buckets"]),
            "service_id": service_id,
        })
    batches.extend([
        {"component": "Cost Anomalies", "buckets": ["cost_anomalies"], "service_id": "platform-cost-anomaly"},
        {"component": "Commitments", "buckets": ["vms"], "service_id": "platform-cost-commitments"},
        {"component": "Budgets", "buckets": ["budgets"], "service_id": "platform-cost-budget"},
    ])
    path = ROOT / "app" / "optimizer" / "platform" / "analysis_batches.py"
    path.write_text(
        "AUTO_GENERATED_ANALYSIS_BATCHES = " + repr(batches) + "\n",
        encoding="utf-8",
    )
    component_map = ROOT / "app" / "optimizer" / "component_map.py"
    text = component_map.read_text(encoding="utf-8")
    if "AUTO_GENERATED_ANALYSIS_BATCHES" not in text:
        text = text.replace(
            "ANALYSIS_BATCHES: list[dict] = [",
            "from app.optimizer.platform.analysis_batches import AUTO_GENERATED_ANALYSIS_BATCHES\n\n"
            "ANALYSIS_BATCHES: list[dict] = AUTO_GENERATED_ANALYSIS_BATCHES\n\n"
            "_LEGACY_ANALYSIS_BATCHES: list[dict] = [",
            1,
        )
        component_map.write_text(text, encoding="utf-8")


def migrate_compute_disk_extras() -> None:
    extras = ["disk_utilization.py", "disk_staleness.py"]
    for name in extras:
        src = ROOT / "app" / name
        dest = ROOT / "it_services" / "compute_disk" / name
        if src.is_file() and not dest.exists():
            shutil.copy2(src, dest)
            write_legacy_shim(src, f"it_services.compute_disk.{name[:-3]}")


def generate_all_sub_engines() -> None:
    for service_id, meta in SUB_ENGINE_META.items():
        if meta.get("dedicated_sub_engine") or service_id in DEDICATED_ENGINE_DIRS:
            pkg = service_pkg(service_id)
            legacy_rel = DEDICATED_ENGINE_DIRS.get(service_id)
            if legacy_rel:
                write_legacy_shim(
                    ROOT / "app" / "optimizer" / "resource_engines" / legacy_rel / "sub_engine.py",
                    f"it_services.{pkg}.engine.sub_engine",
                )
            continue
        pkg = service_pkg(service_id)
        dest = ROOT / "it_services" / pkg / "engine" / "sub_engine.py"
        dest.write_text(generate_sub_engine(service_id, meta), encoding="utf-8")


def write_platform_readme() -> None:
    (ROOT / "app" / "optimizer" / "platform" / "README.md").write_text(
        """# Optimization platform (resource-independent)

Shared engine runtime and cross-cutting analysis — **not** owned by a single Azure resource.

| Path | Purpose |
|------|---------|
| `runtime/` | `ResourceSubEngine`, `AnalysisContext`, resource envelope |
| `cost/` | Budgets, commitments, cost anomalies |
| `sub_engine_registry.py` | Loads per-resource sub-engines from `it_services/*/engine/` |
| `analysis_batches.py` | Generated batch order (one batch per resource service) |

Per-resource sub-engines, analysis rules, and optimization logic live in `it_services/<service_pkg>/engine/`.
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    setup_platform_runtime()
    migrate_platform_cost()
    for service_id, rel in DEDICATED_ENGINE_DIRS.items():
        migrate_dedicated(service_id, rel)
    for rel, mapping in SPLIT_ANALYSIS.items():
        migrate_split_analysis(rel, mapping)
    migrate_compute_disk_extras()
    generate_all_sub_engines()
    write_engine_catalog()
    write_platform_registry()
    write_analysis_batches()
    write_platform_readme()
    print("Engine organization complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

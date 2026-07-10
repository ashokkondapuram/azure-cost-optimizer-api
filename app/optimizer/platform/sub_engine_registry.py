"""Platform sub-engine registry — loads per-resource engines from it_services."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.optimizer.component_map import ANALYSIS_BATCHES
from app.optimizer.platform.runtime.base import ResourceSubEngine
from app.optimizer.platform.runtime.context import AnalysisContext

from it_services.analytics_adx.engine.sub_engine import AdxSubEngine
from it_services.analytics_databricks.engine.sub_engine import DatabricksSubEngine
from it_services.analytics_mlworkspace.engine.sub_engine import MlWorkspaceSubEngine
from it_services.analytics_synapse.engine.sub_engine import SynapseSubEngine
from it_services.appservice_webapp.engine.sub_engine import AppServiceSubEngine
from it_services.backup_recoveryvault.engine.sub_engine import BackupSubEngine
from it_services.compute_disk.engine.sub_engine import DiskSubEngine
from it_services.compute_snapshot.engine.sub_engine import SnapshotSubEngine
from it_services.compute_vm.engine.sub_engine import VmSubEngine
from it_services.compute_vmss.engine.sub_engine import VmssSubEngine
from it_services.containers_acr.engine.sub_engine import AcrSubEngine
from it_services.containers_aks.engine.sub_engine import AksSubEngine
from it_services.database_cosmosdb.engine.sub_engine import CosmosSubEngine
from it_services.database_postgresql.engine.sub_engine import PostgresqlSubEngine
from it_services.database_redis.engine.sub_engine import RedisSubEngine
from it_services.database_sql.engine.sub_engine import SqlSubEngine
from it_services.integration_apim.engine.sub_engine import ApimSubEngine
from it_services.integration_datafactory.engine.sub_engine import DataFactorySubEngine
from it_services.integration_logicapp.engine.sub_engine import LogicAppSubEngine
from it_services.messaging_eventhub.engine.sub_engine import EventHubSubEngine
from it_services.messaging_servicebus.engine.sub_engine import ServiceBusSubEngine
from it_services.monitoring_appinsights.engine.sub_engine import AppInsightsSubEngine
from it_services.monitoring_loganalytics.engine.sub_engine import LogAnalyticsSubEngine
from it_services.network_appgateway.engine.sub_engine import AppGatewaySubEngine
from it_services.network_cdn.engine.sub_engine import CdnSubEngine
from it_services.network_firewall.engine.sub_engine import FirewallSubEngine
from it_services.network_loadbalancer.engine.sub_engine import LoadBalancerSubEngine
from it_services.network_nat.engine.sub_engine import NatSubEngine
from it_services.network_nic.engine.sub_engine import NicSubEngine
from it_services.network_nsg.engine.sub_engine import NsgSubEngine
from it_services.network_privatedns.engine.sub_engine import PrivateDnsSubEngine
from it_services.network_privateendpoint.engine.sub_engine import PrivateEndpointSubEngine
from it_services.network_privatelinkservice.engine.sub_engine import PrivateLinkServiceSubEngine
from it_services.network_publicip.engine.sub_engine import PublicIpSubEngine
from it_services.network_vnet.engine.sub_engine import VnetSubEngine
from it_services.search_cognitivesearch.engine.sub_engine import SearchSubEngine
from it_services.security_keyvault.engine.sub_engine import KeyVaultSubEngine
from it_services.storage_account.engine.sub_engine import StorageSubEngine
from app.optimizer.platform.cost.budget.sub_engine import BudgetSubEngine
from app.optimizer.platform.cost.commitments.sub_engine import CommitmentsSubEngine
from app.optimizer.platform.cost.anomaly.sub_engine import CostAnomalySubEngine

SUB_ENGINE_CLASSES: tuple[type[ResourceSubEngine], ...] = (
    AdxSubEngine, DatabricksSubEngine, MlWorkspaceSubEngine, SynapseSubEngine, AppServiceSubEngine, BackupSubEngine, DiskSubEngine, SnapshotSubEngine, VmSubEngine, VmssSubEngine, AcrSubEngine, AksSubEngine, CosmosSubEngine, PostgresqlSubEngine, RedisSubEngine, SqlSubEngine, ApimSubEngine, DataFactorySubEngine, LogicAppSubEngine, EventHubSubEngine, ServiceBusSubEngine, AppInsightsSubEngine, LogAnalyticsSubEngine, AppGatewaySubEngine, CdnSubEngine, FirewallSubEngine, LoadBalancerSubEngine, NatSubEngine, NicSubEngine, NsgSubEngine, PrivateDnsSubEngine, PrivateEndpointSubEngine, PrivateLinkServiceSubEngine, PublicIpSubEngine, VnetSubEngine, SearchSubEngine, KeyVaultSubEngine, StorageSubEngine, BudgetSubEngine, CommitmentsSubEngine, CostAnomalySubEngine,
)

SUB_ENGINES_BY_COMPONENT: dict[str, type[ResourceSubEngine]] = {
    cls.component: cls for cls in SUB_ENGINE_CLASSES
}

_PARALLEL_GROUP_NAMES: tuple[tuple[str, ...], ...] = (
    ('VmSubEngine', 'VmssSubEngine', 'DiskSubEngine', 'SnapshotSubEngine'),
    ('SqlSubEngine', 'PostgresqlSubEngine', 'RedisSubEngine', 'CosmosSubEngine'),
    ('StorageSubEngine',),
    ('AksSubEngine', 'AcrSubEngine'),
    ('AppServiceSubEngine',),
    ('PublicIpSubEngine', 'NicSubEngine', 'NatSubEngine', 'NsgSubEngine', 'LoadBalancerSubEngine', 'AppGatewaySubEngine'),
    ('KeyVaultSubEngine',),
    ('LogAnalyticsSubEngine', 'AppInsightsSubEngine', 'ApimSubEngine', 'DataFactorySubEngine', 'LogicAppSubEngine', 'EventHubSubEngine', 'ServiceBusSubEngine', 'DatabricksSubEngine', 'SynapseSubEngine', 'AdxSubEngine', 'MlWorkspaceSubEngine', 'BackupSubEngine', 'SearchSubEngine'),
    ('FirewallSubEngine', 'CdnSubEngine', 'VnetSubEngine', 'PrivateEndpointSubEngine', 'PrivateLinkServiceSubEngine', 'PrivateDnsSubEngine'),
    ('CommitmentsSubEngine', 'CostAnomalySubEngine', 'BudgetSubEngine'),
)

_NAME_TO_CLASS: dict[str, type[ResourceSubEngine]] = {cls.__name__: cls for cls in SUB_ENGINE_CLASSES}

PARALLEL_ENGINE_GROUPS: tuple[tuple[type[ResourceSubEngine], ...], ...] = tuple(
    tuple(_NAME_TO_CLASS[name] for name in group)
    for group in _PARALLEL_GROUP_NAMES
)

_PARALLEL_WORKERS = max(1, int(os.getenv("ANALYSIS_ENGINE_WORKERS", "6")))


def list_sub_engines() -> list[dict[str, Any]]:
    batch_components = [b["component"] for b in ANALYSIS_BATCHES]
    out: list[dict[str, Any]] = []
    for cls in SUB_ENGINE_CLASSES:
        out.append({
            "component": cls.component,
            "bucket_keys": list(cls.bucket_keys),
            "batch_order": batch_components.index(cls.component) if cls.component in batch_components else 99,
        })
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

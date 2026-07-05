"""Registry and orchestration for per-resource optimization sub-engines."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.optimizer.component_map import ANALYSIS_BATCHES
from app.optimizer.resource_engines.analytics.sub_engine import AnalyticsSubEngine
from app.optimizer.resource_engines.appservice.webapp.sub_engine import AppServiceSubEngine
from app.optimizer.resource_engines.backup.sub_engine import BackupSubEngine
from app.optimizer.resource_engines.compute.disk.sub_engine import DiskSubEngine
from app.optimizer.resource_engines.compute.snapshot.sub_engine import SnapshotSubEngine
from app.optimizer.resource_engines.compute.vm.sub_engine import VmSubEngine
from app.optimizer.resource_engines.compute.vmss.sub_engine import VmssSubEngine
from app.optimizer.resource_engines.containers.acr.sub_engine import AcrSubEngine
from app.optimizer.resource_engines.containers.aks.sub_engine import AksSubEngine
from app.optimizer.resource_engines.cost.budget.sub_engine import BudgetSubEngine
from app.optimizer.resource_engines.cost.commitments.sub_engine import CommitmentsSubEngine
from app.optimizer.resource_engines.cost.anomaly.sub_engine import CostAnomalySubEngine
from app.optimizer.resource_engines.database.cosmos.sub_engine import CosmosSubEngine
from app.optimizer.resource_engines.database.postgresql.sub_engine import PostgresqlSubEngine
from app.optimizer.resource_engines.database.redis.sub_engine import RedisSubEngine
from app.optimizer.resource_engines.database.sql.sub_engine import SqlSubEngine
from app.optimizer.resource_engines.integration.sub_engine import IntegrationSubEngine
from app.optimizer.resource_engines.messaging.sub_engine import MessagingSubEngine
from app.optimizer.resource_engines.monitoring.sub_engine import MonitoringSubEngine
from app.optimizer.resource_engines.network.appgateway.sub_engine import AppGatewaySubEngine
from app.optimizer.resource_engines.network.loadbalancer.sub_engine import LoadBalancerSubEngine
from app.optimizer.resource_engines.network.nat.sub_engine import NatSubEngine
from app.optimizer.resource_engines.network.nic.sub_engine import NicSubEngine
from app.optimizer.resource_engines.network.nsg.sub_engine import NsgSubEngine
from app.optimizer.resource_engines.network.publicip.sub_engine import PublicIpSubEngine
from app.optimizer.resource_engines.networking.sub_engine import NetworkingExtendedSubEngine, NetworkingSubEngine
from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.runtime.context import AnalysisContext
from app.optimizer.resource_engines.search.sub_engine import SearchSubEngine
from app.optimizer.resource_engines.security.keyvault.sub_engine import KeyVaultSubEngine
from app.optimizer.resource_engines.storage.account.sub_engine import StorageSubEngine

SUB_ENGINE_CLASSES: tuple[type[ResourceSubEngine], ...] = (
    VmSubEngine,
    VmssSubEngine,
    DiskSubEngine,
    SnapshotSubEngine,
    AksSubEngine,
    AppServiceSubEngine,
    StorageSubEngine,
    PublicIpSubEngine,
    NicSubEngine,
    NatSubEngine,
    NsgSubEngine,
    LoadBalancerSubEngine,
    AppGatewaySubEngine,
    SqlSubEngine,
    PostgresqlSubEngine,
    CosmosSubEngine,
    RedisSubEngine,
    AcrSubEngine,
    KeyVaultSubEngine,
    MonitoringSubEngine,
    IntegrationSubEngine,
    MessagingSubEngine,
    AnalyticsSubEngine,
    BackupSubEngine,
    SearchSubEngine,
    NetworkingSubEngine,
    NetworkingExtendedSubEngine,
    CommitmentsSubEngine,
    CostAnomalySubEngine,
    BudgetSubEngine,
)

SUB_ENGINES_BY_COMPONENT: dict[str, type[ResourceSubEngine]] = {
    cls.component: cls for cls in SUB_ENGINE_CLASSES
}

# Independent engine groups — engines within a group run in parallel (1-C).
PARALLEL_ENGINE_GROUPS: tuple[tuple[type[ResourceSubEngine], ...], ...] = (
    (VmSubEngine, VmssSubEngine, DiskSubEngine, SnapshotSubEngine),
    (SqlSubEngine, PostgresqlSubEngine, RedisSubEngine, CosmosSubEngine),
    (StorageSubEngine,),
    (AksSubEngine, AcrSubEngine),
    (AppServiceSubEngine,),
    (PublicIpSubEngine, NicSubEngine, NatSubEngine, NsgSubEngine, LoadBalancerSubEngine, AppGatewaySubEngine),
    (KeyVaultSubEngine,),
    (MonitoringSubEngine, IntegrationSubEngine, MessagingSubEngine, AnalyticsSubEngine, BackupSubEngine, SearchSubEngine),
    (NetworkingSubEngine, NetworkingExtendedSubEngine),
    (CommitmentsSubEngine, CostAnomalySubEngine, BudgetSubEngine),
)

_PARALLEL_WORKERS = max(1, int(os.getenv("ANALYSIS_ENGINE_WORKERS", "6")))


def list_sub_engines() -> list[dict[str, Any]]:
    """Serialize sub-engine metadata for API / UI."""
    batch_components = [b["component"] for b in ANALYSIS_BATCHES]
    out: list[dict[str, Any]] = []
    for cls in SUB_ENGINE_CLASSES:
        out.append({
            "component": cls.component,
            "bucket_keys": list(cls.bucket_keys),
            "batch_order": batch_components.index(cls.component)
            if cls.component in batch_components else 99,
        })
    out.sort(key=lambda row: row["batch_order"])
    return out


def _run_one_engine(
    cls: type[ResourceSubEngine],
    engine: Any,
    ctx: AnalysisContext,
    merged: dict[str, list],
) -> list[Any]:
    sub = cls(engine, ctx)
    return list(sub.analyze(merged))


def run_sub_engines(
    engine: Any,
    ctx: AnalysisContext,
    buckets: dict[str, list],
    *,
    budgets: list[dict] | None = None,
) -> list[Any]:
    """Run resource sub-engines; independent groups execute in parallel."""
    merged = dict(buckets)
    if budgets is not None:
        merged["budgets"] = budgets

    findings: list[Any] = []
    scheduled: set[type[ResourceSubEngine]] = set()

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


def run_sub_engine_for_component(
    engine: Any,
    ctx: AnalysisContext,
    component: str,
    buckets: dict[str, list],
    *,
    budgets: list[dict] | None = None,
) -> list[Any]:
    """Run a single component sub-engine (used by batched analysis)."""
    cls = SUB_ENGINES_BY_COMPONENT.get(component)
    if not cls:
        return []
    merged = dict(buckets)
    if budgets is not None:
        merged["budgets"] = budgets
    return cls(engine, ctx).analyze(merged)


def _has_bucket_data(bucket_keys: tuple[str, ...], buckets: dict[str, list]) -> bool:
    if bucket_keys == ("budgets",):
        return bool(buckets.get("budgets"))
    return any(buckets.get(key) for key in bucket_keys)

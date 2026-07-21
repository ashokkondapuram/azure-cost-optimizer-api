"""Platform sub-engine registry — loads per-resource engines from it_services."""
from __future__ import annotations

import os
import structlog
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.optimizer.analysis_routing import should_run_sub_engine
from app.optimizer.component_map import ANALYSIS_BATCHES
from app.optimizer.platform.runtime.base import ResourceSubEngine
from app.optimizer.platform.runtime.context import AnalysisContext
from app.resource_type_map import internal_resource_type

log = structlog.get_logger(__name__)

# Engine bucket key → canonical resource types (subset used for scoped overrides).
_BUCKET_TO_CANONICAL: dict[str, tuple[str, ...]] = {
    "cosmosdb": ("database/cosmosdb",),
    "disks": ("compute/disk",),
    "vms": ("compute/vm",),
    "postgresql": ("database/postgresql",),
    "redis_caches": ("database/redis",),
}

SUB_ENGINE_CLASSES: tuple[type[ResourceSubEngine], ...] = ()
SUB_ENGINES_BY_COMPONENT: dict[str, type[ResourceSubEngine]] = {}
PARALLEL_ENGINE_GROUPS: tuple[tuple[type[ResourceSubEngine], ...], ...] = ()

_REGISTRY_LOADED = False


def _ensure_registry_loaded() -> None:
    global _REGISTRY_LOADED, SUB_ENGINE_CLASSES, SUB_ENGINES_BY_COMPONENT, PARALLEL_ENGINE_GROUPS
    if _REGISTRY_LOADED:
        return

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
    from it_services.network_frontdoor.engine.sub_engine import FrontDoorSubEngine
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

    sub_engine_classes: tuple[type[ResourceSubEngine], ...] = (
        AdxSubEngine, DatabricksSubEngine, MlWorkspaceSubEngine, SynapseSubEngine, AppServiceSubEngine, BackupSubEngine, DiskSubEngine, SnapshotSubEngine, VmSubEngine, VmssSubEngine, AcrSubEngine, AksSubEngine, CosmosSubEngine, PostgresqlSubEngine, RedisSubEngine, SqlSubEngine, ApimSubEngine, DataFactorySubEngine, LogicAppSubEngine, EventHubSubEngine, ServiceBusSubEngine, AppInsightsSubEngine, LogAnalyticsSubEngine, AppGatewaySubEngine, CdnSubEngine, FirewallSubEngine, FrontDoorSubEngine, LoadBalancerSubEngine, NatSubEngine, NicSubEngine, NsgSubEngine, PrivateDnsSubEngine, PrivateEndpointSubEngine, PrivateLinkServiceSubEngine, PublicIpSubEngine, VnetSubEngine, SearchSubEngine, KeyVaultSubEngine, StorageSubEngine, BudgetSubEngine, CommitmentsSubEngine, CostAnomalySubEngine,
    )
    name_to_class = {cls.__name__: cls for cls in sub_engine_classes}
    parallel_group_names: tuple[tuple[str, ...], ...] = (
        ('VmSubEngine', 'VmssSubEngine', 'DiskSubEngine', 'SnapshotSubEngine'),
        ('SqlSubEngine', 'PostgresqlSubEngine', 'RedisSubEngine', 'CosmosSubEngine'),
        ('StorageSubEngine',),
        ('AksSubEngine', 'AcrSubEngine'),
        ('AppServiceSubEngine',),
        ('PublicIpSubEngine', 'NicSubEngine', 'NatSubEngine', 'NsgSubEngine', 'LoadBalancerSubEngine', 'AppGatewaySubEngine'),
        ('KeyVaultSubEngine',),
        ('LogAnalyticsSubEngine', 'AppInsightsSubEngine', 'ApimSubEngine', 'DataFactorySubEngine', 'LogicAppSubEngine', 'EventHubSubEngine', 'ServiceBusSubEngine', 'DatabricksSubEngine', 'SynapseSubEngine', 'AdxSubEngine', 'MlWorkspaceSubEngine', 'BackupSubEngine', 'SearchSubEngine'),
        ('FirewallSubEngine', 'CdnSubEngine', 'FrontDoorSubEngine', 'VnetSubEngine', 'PrivateEndpointSubEngine', 'PrivateLinkServiceSubEngine', 'PrivateDnsSubEngine'),
        ('CommitmentsSubEngine', 'CostAnomalySubEngine', 'BudgetSubEngine'),
    )

    SUB_ENGINE_CLASSES = sub_engine_classes
    SUB_ENGINES_BY_COMPONENT = {cls.component: cls for cls in sub_engine_classes}
    PARALLEL_ENGINE_GROUPS = tuple(
        tuple(name_to_class[name] for name in group)
        for group in parallel_group_names
    )
    _REGISTRY_LOADED = True

_PARALLEL_WORKERS = max(1, int(os.getenv("ANALYSIS_ENGINE_WORKERS", "6")))


def list_sub_engines() -> list[dict[str, Any]]:
    _ensure_registry_loaded()
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


def _evaluate_bucket_assessment_findings(
    sub: ResourceSubEngine,
    raw: list[dict],
    *,
    metrics_kind: str | None = None,
) -> list[Any]:
    """Evaluate assessment JSON rules for one inventory bucket."""
    prepared = sub.prepare_resources(raw, metrics_kind=metrics_kind)
    if not prepared:
        return []
    assessment_findings = sub.evaluate_assessment_findings(prepared)
    return sub.enhance_findings(assessment_findings, prepared)


def _engine_matches_scoped_types(
    cls: type[ResourceSubEngine],
    scoped_types: set[str],
) -> bool:
    if not scoped_types:
        return False
    try:
        from app.analysis.orchestrator import BUCKET_TO_TYPES as orchestrator_map
        bucket_map = orchestrator_map
    except ImportError:
        bucket_map = _BUCKET_TO_CANONICAL
    for key in cls.bucket_keys:
        canonicals = bucket_map.get(key) or _BUCKET_TO_CANONICAL.get(key, ())
        if scoped_types.intersection({c.lower() for c in canonicals}):
            return True
    return False


def _should_run_engine(
    cls: type[ResourceSubEngine],
    scoped_types: set[str] | None = None,
) -> bool:
    if should_run_sub_engine(cls):
        return True
    return bool(scoped_types) and _engine_matches_scoped_types(cls, scoped_types)


def _canonical_type_for_resource(resource: dict[str, Any]) -> str:
    rid = (resource.get("id") or resource.get("resource_id") or "").strip()
    return (
        (resource.get("_canonical_type") or "").strip().lower()
        or internal_resource_type(rid)
        or (resource.get("type") or "").strip().lower()
    )


def _record_engine_stats(
    stats: dict[str, dict[str, int]],
    cls: type[ResourceSubEngine],
    buckets: dict[str, list],
    findings: list[Any],
) -> None:
    canonical_types: set[str] = set()
    resources_evaluated = 0
    for key in cls.bucket_keys:
        for resource in buckets.get(key) or []:
            resources_evaluated += 1
            canonical = _canonical_type_for_resource(resource)
            if canonical:
                canonical_types.add(canonical)
    if not canonical_types and cls.component:
        canonical_types.add(cls.component)
    rules_matched = len({getattr(f, "rule_id", None) or "" for f in findings if getattr(f, "rule_id", None)})
    for canonical in canonical_types or {cls.component}:
        bucket = stats.setdefault(canonical, {
            "resources_evaluated": 0,
            "rules_matched": 0,
            "findings_created": 0,
        })
        bucket["resources_evaluated"] += resources_evaluated
        bucket["rules_matched"] += rules_matched
        bucket["findings_created"] += len(findings)


def _run_one_engine(cls, engine, ctx, merged, stats: dict[str, dict[str, int]] | None = None):
    sub = cls(engine, ctx)
    findings: list[Any] = []

    for key in cls.bucket_keys:
        if key in {"budgets", "cost_anomalies"}:
            continue
        raw = merged.get(key) or []
        if not raw:
            continue
        metrics_kind = sub._metrics_kind_for_resource(raw[0]) if raw else None
        findings.extend(_evaluate_bucket_assessment_findings(sub, raw, metrics_kind=metrics_kind))

    findings.extend(sub.analyze(merged))
    if stats is not None:
        _record_engine_stats(stats, cls, merged, findings)
    return findings


def run_sub_engines(engine, ctx, buckets, *, budgets=None, db=None, scoped_canonical_types=None):
    _ensure_registry_loaded()
    merged = dict(buckets)
    if budgets is not None:
        merged["budgets"] = budgets
    scoped_types = {
        t.strip().lower() for t in (scoped_canonical_types or []) if t and str(t).strip()
    }
    findings = []
    eval_stats: dict[str, dict[str, int]] = {}
    scheduled = set()
    for group in PARALLEL_ENGINE_GROUPS:
        active = [
            cls for cls in group
            if _should_run_engine(cls, scoped_types or None) and _has_bucket_data(cls.bucket_keys, merged)
        ]
        if not active:
            continue
        scheduled.update(active)
        if len(active) == 1:
            findings.extend(_run_one_engine(active[0], engine, ctx, merged, eval_stats))
            continue
        with ThreadPoolExecutor(max_workers=min(_PARALLEL_WORKERS, len(active))) as pool:
            futures = [
                pool.submit(_run_one_engine, cls, engine, ctx, merged, eval_stats)
                for cls in active
            ]
            for future in as_completed(futures):
                findings.extend(future.result())
    for cls in SUB_ENGINE_CLASSES:
        if cls in scheduled:
            continue
        if not _should_run_engine(cls, scoped_types or None):
            continue
        if not _has_bucket_data(cls.bucket_keys, merged):
            continue
        findings.extend(_run_one_engine(cls, engine, ctx, merged, eval_stats))
    if db is not None:
        from app.assessment.recommendation_engine import run_uncovered_assessment_recommendations

        findings.extend(run_uncovered_assessment_recommendations(db, engine, ctx, merged))
    if eval_stats:
        log.info(
            "sub_engines.evaluation_summary",
            subscription_id=getattr(ctx, "subscription_id", ""),
            by_canonical_type=eval_stats,
            findings_total=len(findings),
        )
    return findings


def run_sub_engine_for_component(engine, ctx, component, buckets, *, budgets=None):
    _ensure_registry_loaded()
    cls = SUB_ENGINES_BY_COMPONENT.get(component)
    if not cls or not should_run_sub_engine(cls):
        return []
    merged = dict(buckets)
    if budgets is not None:
        merged["budgets"] = budgets
    return _run_one_engine(cls, engine, ctx, merged, stats=None)


def _has_bucket_data(bucket_keys, buckets):
    if bucket_keys == ("budgets",):
        return bool(buckets.get("budgets"))
    return any(buckets.get(key) for key in bucket_keys)

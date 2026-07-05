"""Registry and orchestration for per-resource sub-engines."""
from __future__ import annotations

from typing import Any

from app.optimizer.component_map import ANALYSIS_BATCHES

from .analyzers import (
    AcrSubEngine,
    AksSubEngine,
    AppGatewaySubEngine,
    AppServiceSubEngine,
    BudgetSubEngine,
    CosmosSubEngine,
    DiskSubEngine,
    SnapshotSubEngine,
    KeyVaultSubEngine,
    LoadBalancerSubEngine,
    NatSubEngine,
    NicSubEngine,
    NsgSubEngine,
    PostgresqlSubEngine,
    PublicIpSubEngine,
    RedisSubEngine,
    SqlSubEngine,
    StorageSubEngine,
    VmSubEngine,
    VmssSubEngine,
)
from .base import ResourceSubEngine
from .context import AnalysisContext

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
    BudgetSubEngine,
)

SUB_ENGINES_BY_COMPONENT: dict[str, type[ResourceSubEngine]] = {
    cls.component: cls for cls in SUB_ENGINE_CLASSES
}


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


def run_sub_engines(
    engine: Any,
    ctx: AnalysisContext,
    buckets: dict[str, list],
    *,
    budgets: list[dict] | None = None,
) -> list[Any]:
    """Run all resource sub-engines against the supplied bucket set."""
    merged = dict(buckets)
    if budgets is not None:
        merged["budgets"] = budgets

    findings: list[Any] = []
    for cls in SUB_ENGINE_CLASSES:
        if not _has_bucket_data(cls.bucket_keys, merged):
            continue
        sub = cls(engine, ctx)
        findings.extend(sub.analyze(merged))
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

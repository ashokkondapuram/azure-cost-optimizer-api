"""PostgreSQL optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from it_services.database_postgresql.engine.optimization_rules import (
    PostgresFindingDraft,
    evaluate_postgresql_backup_retention,
    evaluate_postgresql_burstable,
    evaluate_postgresql_connection_pool_risk,
    evaluate_postgresql_ha_required,
    evaluate_postgresql_ha_unnecessary,
    evaluate_postgresql_high_compute,
    evaluate_postgresql_iops_pressure,
    evaluate_postgresql_low_compute,
    evaluate_postgresql_memory_pressure,
    evaluate_postgresql_read_replica,
    evaluate_postgresql_stopped,
    evaluate_postgresql_storage_expansion,
    evaluate_postgresql_storage_extended,
    evaluate_postgresql_version_outdated,
)
from app.cost_utils import resource_cost
from app.postgresql_sku_catalog import parse_postgresql_arm_server


def _append_draft(
    out: list[ExtendedFinding],
    engine: Any,
    subscription_id: str,
    server: dict[str, Any],
    rule: Any,
    draft: PostgresFindingDraft | None,
) -> None:
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=server,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def analyze_postgresql(
    engine,
    subscription_id: str,
    servers: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule_ids = (
        "POSTGRESQL_STOPPED_EXTENDED",
        "POSTGRESQL_BURSTABLE_EXTENDED",
        "POSTGRESQL_LOW_COMPUTE_UTILIZATION",
        "POSTGRESQL_HIGH_COMPUTE_DEMAND",
        "POSTGRESQL_MEMORY_PRESSURE",
        "POSTGRESQL_STORAGE_EXTENDED",
        "POSTGRESQL_STORAGE_EXPANSION",
        "POSTGRESQL_IOPS_PRESSURE",
        "POSTGRESQL_CONNECTION_POOL_RISK",
        "POSTGRESQL_HA_UNNECESSARY",
        "POSTGRESQL_HA_REQUIRED",
        "POSTGRESQL_READ_REPLICA_ANALYSIS",
        "POSTGRESQL_VERSION_OUTDATED",
        "POSTGRESQL_BACKUP_RETENTION_REVIEW",
    )
    rules = {rid: engine.rules.get(rid) for rid in rule_ids}

    for server in servers:
        ctx = parse_postgresql_arm_server(server)
        monthly = resource_cost(cost_by_resource, server.get("id", ""))

        evaluators = (
            (rules["POSTGRESQL_STOPPED_EXTENDED"], evaluate_postgresql_stopped),
            (rules["POSTGRESQL_BURSTABLE_EXTENDED"], evaluate_postgresql_burstable),
            (rules["POSTGRESQL_LOW_COMPUTE_UTILIZATION"], evaluate_postgresql_low_compute),
            (rules["POSTGRESQL_HIGH_COMPUTE_DEMAND"], evaluate_postgresql_high_compute),
            (rules["POSTGRESQL_MEMORY_PRESSURE"], evaluate_postgresql_memory_pressure),
            (rules["POSTGRESQL_STORAGE_EXTENDED"], evaluate_postgresql_storage_extended),
            (rules["POSTGRESQL_STORAGE_EXPANSION"], evaluate_postgresql_storage_expansion),
            (rules["POSTGRESQL_IOPS_PRESSURE"], evaluate_postgresql_iops_pressure),
            (rules["POSTGRESQL_CONNECTION_POOL_RISK"], evaluate_postgresql_connection_pool_risk),
            (rules["POSTGRESQL_HA_UNNECESSARY"], evaluate_postgresql_ha_unnecessary),
            (rules["POSTGRESQL_HA_REQUIRED"], evaluate_postgresql_ha_required),
            (rules["POSTGRESQL_READ_REPLICA_ANALYSIS"], evaluate_postgresql_read_replica),
            (rules["POSTGRESQL_VERSION_OUTDATED"], evaluate_postgresql_version_outdated),
            (rules["POSTGRESQL_BACKUP_RETENTION_REVIEW"], evaluate_postgresql_backup_retention),
        )
        for rule, evaluator in evaluators:
            _append_draft(out, engine, subscription_id, server, rule, evaluator(server, ctx, monthly, rule))

    return out

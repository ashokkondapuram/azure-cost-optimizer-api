"""PostgreSQL Flexible Server optimization decision rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.azure_retail_pricing import estimate_postgresql_tier_savings, estimate_postgresql_ha_savings
from app.cost_utils import savings_from_factor
from app.postgresql_sku_catalog import (
    optimization_thresholds,
    parse_postgresql_arm_server,
    suggested_larger_sku,
    suggested_smaller_sku,
)
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import (
    confidence_with_monitor,
    cpu_pct,
    fact_value,
    is_low_cpu,
    make_check,
    memory_pct,
    metrics_block_rightsize,
    monitor_evidence,
    structured_evidence,
    utilization_gate,
)


@dataclass(frozen=True)
class PostgresFindingDraft:
    rule_id: str
    detail: str
    recommendation: str
    savings: float
    waste_score: int
    confidence: int
    priority: str
    impact: str
    evidence: dict[str, Any]


def _thresholds(rule: Any) -> dict[str, float]:
    defaults = optimization_thresholds()
    return {
        "cpu_high_pct": float(getattr(rule, "postgresql_cpu_high_pct", defaults.get("cpu_high_pct", 80.0))),
        "cpu_low_pct": float(getattr(rule, "postgresql_cpu_low_pct", defaults.get("cpu_low_pct", 25.0))),
        "memory_pressure_pct": float(getattr(rule, "postgresql_memory_pressure_pct", defaults.get("memory_pressure_pct", 85.0))),
        "memory_low_pct": float(getattr(rule, "postgresql_memory_low_pct", defaults.get("memory_low_pct", 40.0))),
        "storage_high_pct": float(getattr(rule, "postgresql_storage_high_pct", defaults.get("storage_high_pct", 80.0))),
        "storage_low_pct": float(getattr(rule, "postgresql_storage_low_pct", defaults.get("storage_low_pct", 40.0))),
        "iops_pressure_pct": float(getattr(rule, "postgresql_iops_pressure_pct", defaults.get("iops_pressure_pct", 80.0))),
        "connection_risk_absolute": float(getattr(rule, "postgresql_connection_risk_absolute", defaults.get("connection_risk_absolute", 3500.0))),
        "replication_lag_seconds": float(getattr(rule, "postgresql_replication_lag_seconds", defaults.get("replication_lag_seconds", 5.0))),
        "backup_retention_prod_days": float(getattr(rule, "postgresql_backup_retention_prod_days", defaults.get("backup_retention_prod_days", 14.0))),
        "backup_retention_dev_days": float(getattr(rule, "postgresql_backup_retention_dev_days", defaults.get("backup_retention_dev_days", 7.0))),
    }


def _pg_metric_evidence(server: dict[str, Any], ctx: dict[str, Any], extra: dict | None = None) -> dict[str, Any]:
    payload = {
        **ctx,
        "cpu_pct": cpu_pct(server),
        "memory_pct": memory_pct(server),
        "storage_pct": fact_value(server, "storage_pct"),
        "disk_iops_pct": fact_value(server, "disk_iops_pct"),
        "active_connections": fact_value(server, "active_connections"),
        "max_connections": fact_value(server, "max_connections"),
        "replication_lag_sec": fact_value(server, "replication_lag_sec"),
        "backup_storage_bytes": fact_value(server, "backup_storage_bytes"),
    }
    base = monitor_evidence(server, payload)
    if extra:
        base.update(extra)
    return base


def _tier_pricing_savings(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    suggested_sku: str,
) -> tuple[float, dict[str, Any]]:
    pricing = estimate_postgresql_tier_savings(
        server.get("location") or "",
        ctx.get("sku_name") or ctx.get("tier") or "",
        suggested_sku,
        actual_monthly_cost=monthly if monthly > 0 else None,
    )
    savings = savings_from_retail_or_none(pricing)
    if savings is None and monthly > 0:
        savings = savings_from_factor(monthly, 0.35)
    return float(savings or 0.0), pricing


def _passes_min_savings(rule: Any, savings: float) -> bool:
    min_savings = float(getattr(rule, "min_monthly_savings_usd", 0.0) or 0.0)
    return savings <= 0 or savings >= min_savings


def _env_tag(server: dict[str, Any], rule: Any) -> str:
    tags = server.get("tags") or {}
    return str(tags.get("environment") or tags.get("env") or "").lower()


def _is_prod(env: str, rule: Any) -> bool:
    return env in [v.lower() for v in getattr(rule, "prod_tag_values", ["prod", "production"])]


def _is_nonprod(env: str, rule: Any) -> bool:
    return env in [v.lower() for v in getattr(rule, "nonprod_tag_values", ["dev", "test", "qa", "staging", "sandbox"])]


def evaluate_postgresql_stopped(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if (ctx.get("state") or "").lower() != "stopped":
        return None
    name = server.get("name") or ""
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_STOPPED_EXTENDED",
        detail=f"PostgreSQL server '{name}' is stopped but may still incur storage and backup charges.",
        recommendation="Export data and delete the server if no longer needed, or start it during required windows only.",
        savings=savings_from_factor(monthly, 0.6) if monthly > 0 else 0.0,
        waste_score=58,
        confidence=80,
        priority="P2",
        impact="Eliminates idle database storage and backup cost",
        evidence={"state": ctx.get("state"), "storage_gb": ctx.get("storage_gb")},
    )


def evaluate_postgresql_burstable(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    env = _env_tag(server, rule)
    if not _is_nonprod(env, rule):
        return None
    tier = (ctx.get("tier") or "").lower()
    sku_name = (ctx.get("sku_name") or "").lower()
    if tier not in ("generalpurpose", "memoryoptimized") and not sku_name.startswith(("standard_d", "standard_e")):
        return None
    if metrics_block_rightsize(server):
        return None
    if not utilization_gate(server, "cpu_pct", allow_inventory_only=False):
        return None
    if is_low_cpu(server, threshold=35.0) is not True:
        return None
    cpu = cpu_pct(server)
    savings, pricing = _tier_pricing_savings(server, ctx, monthly, "Standard_B2s")
    if not _passes_min_savings(rule, savings):
        return None
    name = server.get("name") or ""
    detail = f"PostgreSQL '{name}' uses {tier or sku_name} SKU in a non-production environment."
    if cpu is not None:
        detail += f" CPU averages {cpu:.1f}% in Azure Monitor."
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_BURSTABLE_EXTENDED",
        detail=detail,
        recommendation="Move dev/test workloads to Burstable (B-series) compute to reduce baseline cost.",
        savings=savings,
        waste_score=56,
        confidence=confidence_with_monitor(74, server, boost=14),
        priority="P2",
        impact="Database compute right-sizing for non-prod",
        evidence=structured_evidence(
            server,
            determination="burstable_candidate",
            summary="Non-production PostgreSQL server shows low CPU in Azure Monitor.",
            checks=[make_check("Average CPU", cpu, "< 35%", passed=True)],
            extra={"sku": sku_name, "tier": tier, "environment": env, **pricing},
        ),
    )


def evaluate_postgresql_low_compute(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if metrics_block_rightsize(server):
        return None
    if not utilization_gate(server, "cpu_pct", allow_inventory_only=False):
        return None
    thresholds = _thresholds(rule)
    cpu = cpu_pct(server)
    mem = memory_pct(server)
    if cpu is None or cpu >= thresholds["cpu_low_pct"]:
        return None
    if mem is not None and mem >= thresholds["memory_low_pct"]:
        return None
    suggested = suggested_smaller_sku(ctx.get("sku_name") or "")
    if not suggested:
        return None
    savings, pricing = _tier_pricing_savings(server, ctx, monthly, suggested)
    if not _passes_min_savings(rule, savings):
        return None
    name = server.get("name") or ""
    detail = f"PostgreSQL '{name}' shows sustained low compute utilization"
    if cpu is not None:
        detail += f" (CPU {cpu:.1f}%"
        if mem is not None:
            detail += f", memory {mem:.1f}%"
        detail += ")."
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_LOW_COMPUTE_UTILIZATION",
        detail=detail,
        recommendation=f"Downgrade to {suggested} after validating workload trends. Consider Burstable for non-production.",
        savings=savings,
        waste_score=54,
        confidence=confidence_with_monitor(70, server, required_keys=("cpu_pct",)),
        priority="P3",
        impact="Compute tier right-sizing opportunity",
        evidence=_pg_metric_evidence(server, ctx, {**pricing, "determination": "low_compute"}),
    )


def evaluate_postgresql_high_compute(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if not utilization_gate(server, "cpu_pct", allow_inventory_only=False):
        return None
    thresholds = _thresholds(rule)
    cpu = cpu_pct(server)
    if cpu is None or cpu < thresholds["cpu_high_pct"]:
        return None
    suggested = suggested_larger_sku(ctx.get("sku_name") or "")
    name = server.get("name") or ""
    detail = f"PostgreSQL '{name}' CPU averages {cpu:.1f}% — above the {thresholds['cpu_high_pct']:.0f}% threshold."
    recommendation = (
        f"Upgrade to {suggested or 'the next vCore SKU'} to add compute headroom."
        if suggested
        else "Upgrade to the next vCore tier to add compute headroom."
    )
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_HIGH_COMPUTE_DEMAND",
        detail=detail,
        recommendation=recommendation,
        savings=0.0,
        waste_score=72,
        confidence=confidence_with_monitor(78, server, required_keys=("cpu_pct",)),
        priority="P2",
        impact="Prevents CPU saturation and query latency",
        evidence=_pg_metric_evidence(server, ctx, {"determination": "high_cpu", "suggested_sku": suggested}),
    )


def evaluate_postgresql_memory_pressure(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if not utilization_gate(server, "memory_pct", allow_inventory_only=False):
        return None
    thresholds = _thresholds(rule)
    mem = memory_pct(server)
    if mem is None or mem < thresholds["memory_pressure_pct"]:
        return None
    suggested = suggested_larger_sku(ctx.get("sku_name") or "")
    name = server.get("name") or ""
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_MEMORY_PRESSURE",
        detail=f"PostgreSQL '{name}' memory utilization is {mem:.1f}% in Azure Monitor.",
        recommendation=(
            f"Upgrade to {suggested or 'a tier with more memory'} or reduce buffer-heavy workloads."
        ),
        savings=0.0,
        waste_score=75 if mem >= 90 else 65,
        confidence=confidence_with_monitor(76, server, required_keys=("memory_pct",)),
        priority="P1" if mem >= 90 else "P2",
        impact="Reduces risk of memory pressure and degraded query performance",
        evidence=_pg_metric_evidence(server, ctx, {"determination": "memory_pressure"}),
    )


def evaluate_postgresql_storage_extended(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    storage_pct = fact_value(server, "storage_pct")
    storage_gb = int(ctx.get("storage_gb") or 0)
    thresholds = _thresholds(rule)
    over_provisioned = storage_gb >= int(thresholds.get("storage_overprovision_gb", 256))
    low_utilization = storage_pct is not None and storage_pct < thresholds["storage_low_pct"]
    if not over_provisioned and not low_utilization:
        return None
    name = server.get("name") or ""
    detail = f"PostgreSQL '{name}' has {storage_gb} GB provisioned storage."
    if low_utilization:
        detail += f" Storage utilization averages {storage_pct:.1f}% in Azure Monitor."
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_STORAGE_EXTENDED",
        detail=detail,
        recommendation="Review actual data size and enable storage auto-grow with a right-sized cap.",
        savings=savings_from_factor(monthly, 0.2) if monthly > 0 else 0.0,
        waste_score=44 if low_utilization else 40,
        confidence=confidence_with_monitor(60, server, boost=12 if low_utilization else 0),
        priority="P3",
        impact="Storage provisioning optimization",
        evidence=structured_evidence(
            server,
            determination="storage_overprovisioned",
            summary="PostgreSQL storage is over-provisioned relative to monitored utilization.",
            checks=[
                make_check("Provisioned storage (GB)", storage_gb, f"≥ {int(thresholds.get('storage_overprovision_gb', 256))}", passed=over_provisioned),
                make_check("Storage utilization", storage_pct, f"< {thresholds['storage_low_pct']}%", passed=low_utilization),
            ],
            extra={"storage_gb": storage_gb},
        ),
    )


def evaluate_postgresql_storage_expansion(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if not utilization_gate(server, "storage_pct", allow_inventory_only=False):
        return None
    thresholds = _thresholds(rule)
    storage_pct = fact_value(server, "storage_pct")
    if storage_pct is None or storage_pct < thresholds["storage_high_pct"]:
        return None
    storage_gb = int(ctx.get("storage_gb") or 0)
    name = server.get("name") or ""
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_STORAGE_EXPANSION",
        detail=f"PostgreSQL '{name}' storage is {storage_pct:.1f}% utilized ({storage_gb} GB provisioned).",
        recommendation="Expand storage capacity or archive cold data before reaching capacity limits.",
        savings=0.0,
        waste_score=70,
        confidence=confidence_with_monitor(75, server, required_keys=("storage_pct",)),
        priority="P2",
        impact="Prevents out-of-space incidents",
        evidence=_pg_metric_evidence(server, ctx, {"determination": "storage_expansion"}),
    )


def evaluate_postgresql_iops_pressure(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    iops_pct = fact_value(server, "disk_iops_pct")
    if iops_pct is None:
        return None
    thresholds = _thresholds(rule)
    if iops_pct < thresholds["iops_pressure_pct"]:
        return None
    name = server.get("name") or ""
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_IOPS_PRESSURE",
        detail=f"PostgreSQL '{name}' disk IOPS consumption is {iops_pct:.1f}% of provisioned limits.",
        recommendation="Upgrade storage tier (Premium SSD v2) or increase vCores to raise IOPS ceiling.",
        savings=0.0,
        waste_score=68,
        confidence=confidence_with_monitor(72, server, required_keys=("disk_iops_pct",)),
        priority="P2",
        impact="Prevents I/O bottlenecks under load",
        evidence=_pg_metric_evidence(server, ctx, {"determination": "iops_pressure"}),
    )


def evaluate_postgresql_connection_pool_risk(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    active = fact_value(server, "active_connections")
    max_used = fact_value(server, "max_connections")
    conn_util = fact_value(server, "connection_utilization_pct")
    connections = max(active or 0.0, max_used or 0.0)
    thresholds = _thresholds(rule)
    connection_risk_pct = float(getattr(rule, "postgresql_connection_risk_pct", thresholds.get("connection_risk_pct", 70.0)))
    high_utilization = conn_util is not None and conn_util >= connection_risk_pct
    if connections < thresholds["connection_risk_absolute"] and not high_utilization:
        return None
    name = server.get("name") or ""
    detail = f"PostgreSQL '{name}' shows {connections:,.0f} concurrent connections in Azure Monitor."
    if conn_util is not None:
        detail += f" Peak connection utilization is {conn_util:.1f}%."
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_CONNECTION_POOL_RISK",
        detail=f"PostgreSQL '{name}' shows {connections:,.0f} concurrent connections in Azure Monitor.",
        recommendation="Enable PgBouncer connection pooling on the flexible server to reduce connection pressure.",
        savings=0.0,
        waste_score=55,
        confidence=confidence_with_monitor(70, server, required_keys=("active_connections",)),
        priority="P2",
        impact="Avoids connection exhaustion without immediate compute upgrade",
        evidence=_pg_metric_evidence(server, ctx, {"determination": "connection_pool_risk"}),
    )


def evaluate_postgresql_ha_unnecessary(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if not ctx.get("ha_enabled"):
        return None
    env = _env_tag(server, rule)
    if _is_prod(env, rule):
        return None
    savings = estimate_postgresql_ha_savings(monthly, ctx.get("ha_mode"), disable=True)
    if not _passes_min_savings(rule, savings):
        return None
    name = server.get("name") or ""
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_HA_UNNECESSARY",
        detail=f"PostgreSQL '{name}' has HA mode '{ctx.get('ha_mode')}' in a non-production environment.",
        recommendation="Disable high availability for dev/test to reduce compute cost (~50% for SameZone HA).",
        savings=savings,
        waste_score=60,
        confidence=65,
        priority="P3",
        impact="HA cost reduction for non-production",
        evidence=_pg_metric_evidence(server, ctx, {"determination": "ha_unnecessary", "environment": env}),
    )


def evaluate_postgresql_ha_required(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if ctx.get("ha_enabled"):
        return None
    env = _env_tag(server, rule)
    if not _is_prod(env, rule):
        return None
    name = server.get("name") or ""
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_HA_REQUIRED",
        detail=f"PostgreSQL '{name}' is tagged production but high availability is disabled.",
        recommendation="Enable SameZone HA for failover capability (adds ~50% compute cost). Use ZoneRedundant only if zone SLA requires it.",
        savings=0.0,
        waste_score=65,
        confidence=70,
        priority="P1",
        impact="Production availability and failover readiness",
        evidence=_pg_metric_evidence(server, ctx, {"determination": "ha_required", "environment": env}),
    )


def evaluate_postgresql_read_replica(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if not ctx.get("is_read_replica"):
        return None
    lag = fact_value(server, "replication_lag_sec")
    thresholds = _thresholds(rule)
    name = server.get("name") or ""
    detail = f"PostgreSQL read replica '{name}' incurs full instance cost."
    if lag is not None:
        detail += f" Replication lag averages {lag:.1f} seconds."
    high_lag = lag is not None and lag > thresholds["replication_lag_seconds"]
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_READ_REPLICA_ANALYSIS",
        detail=detail,
        recommendation=(
            "Review whether read traffic justifies a dedicated replica; consolidate reads or remove replica if underused."
            if not high_lag
            else "Investigate replication lag — network or I/O bottlenecks may reduce replica value."
        ),
        savings=monthly if monthly > 0 else 0.0,
        waste_score=58 if not high_lag else 64,
        confidence=confidence_with_monitor(68, server, required_keys=("replication_lag_sec",)) if lag is not None else 55,
        priority="P3",
        impact="Read replica cost vs. scaling benefit",
        evidence=_pg_metric_evidence(server, ctx, {"determination": "read_replica_review"}),
    )


def evaluate_postgresql_version_outdated(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if not ctx.get("version_outdated"):
        return None
    name = server.get("name") or ""
    version = ctx.get("version") or ""
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_VERSION_OUTDATED",
        detail=f"PostgreSQL '{name}' runs version {version}, which is behind current supported releases.",
        recommendation="Plan an in-place major version upgrade during a maintenance window for support and performance improvements.",
        savings=0.0,
        waste_score=45,
        confidence=75,
        priority="P3",
        impact="Support lifecycle and performance optimization",
        evidence={"version": version, "major_version": ctx.get("major_version"), "determination": "version_outdated"},
    )


def evaluate_postgresql_backup_retention(
    server: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> PostgresFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    retention = int(ctx.get("backup_retention_days") or 0)
    if retention <= 0:
        return None
    thresholds = _thresholds(rule)
    env = _env_tag(server, rule)
    target = int(thresholds["backup_retention_prod_days"] if _is_prod(env, rule) else thresholds["backup_retention_dev_days"])
    if retention <= target:
        return None
    name = server.get("name") or ""
    savings = savings_from_factor(monthly, 0.1) if monthly > 0 else 0.0
    return PostgresFindingDraft(
        rule_id="POSTGRESQL_BACKUP_RETENTION_REVIEW",
        detail=f"PostgreSQL '{name}' retains backups for {retention} days.",
        recommendation=f"Reduce retention toward {target} days if compliance allows to lower backup storage cost.",
        savings=savings,
        waste_score=42,
        confidence=60,
        priority="P3",
        impact="Backup storage cost optimization",
        evidence={
            "backup_retention_days": retention,
            "target_retention_days": target,
            "geo_redundant_backup": ctx.get("geo_redundant_backup"),
            "determination": "backup_retention_review",
        },
    )

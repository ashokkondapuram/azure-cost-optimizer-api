"""Idle pattern detection — identifies resources that are running but unused.

Goes beyond simple CPU threshold checks by detecting:
  - Temporal idle patterns (idle outside business hours)
  - Network-silent resources (minimal/zero egress bytes)
  - DB connection drought (databases with no connections in N days)
  - Storage access drought (storage accounts not accessed in N days)
  - AKS pods-requested == 0 (node pool with nothing scheduled)
  - Logic App / Function App with zero invocations
  - Consistent zero-traffic Application Gateway

Each detector returns a list of ``IdleSignal`` objects that the orchestrator
consolidates into findings with estimated savings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()

_IDLE_CPU_THRESHOLD      = 5.0     # %  below this = idle
_IDLE_NET_BYTES_THRESHOLD = 1_024   # bytes/s — below this = network silent
_DB_CONNECTION_DROUGHT    = 7       # days with zero connections
_STORAGE_ACCESS_DROUGHT   = 30      # days since last access
_ZERO_INVOCATION_DAYS     = 14      # serverless idle threshold


@dataclass
class IdleSignal:
    resource_id: str
    resource_name: str
    resource_type: str
    idle_type: str                 # see constants below
    severity: str                  # "low" | "medium" | "high" | "critical"
    idle_days: int | None          # how long the idle pattern has persisted
    monthly_cost: float
    estimated_monthly_savings: float
    description: str
    recommended_action: str
    evidence: dict[str, Any] = field(default_factory=dict)


# Idle type constants
IDLE_TEMPORAL           = "temporal_off_hours"
IDLE_NETWORK_SILENT     = "network_silent"
IDLE_DB_NO_CONNECTIONS  = "db_no_connections"
IDLE_STORAGE_UNACCESSED = "storage_unaccessed"
IDLE_ZERO_INVOCATIONS   = "zero_invocations"
IDLE_ZERO_TRAFFIC       = "zero_traffic"
IDLE_AKS_EMPTY_POOL     = "aks_empty_pool"
IDLE_ZOMBIE_VM          = "zombie_vm"


def _norm_id(rid: str) -> str:
    return (rid or "").lower().strip()


def detect_idle_vms(
    vms: list[dict],
    vm_metrics: dict[str, dict],
    cost_by_resource: dict[str, float],
) -> list[IdleSignal]:
    """Detect VMs with consistently near-zero CPU and network activity.

    Args:
        vms: VM resource dicts from inventory.
        vm_metrics: Resource ID → metrics dict with avg_cpu_pct, avg_net_bytes_out, etc.
        cost_by_resource: Resource ID → monthly cost USD.

    Returns:
        List of IdleSignal for idle VMs.
    """
    signals: list[IdleSignal] = []
    for vm in vms:
        rid = _norm_id(vm.get("id") or "")
        metrics = vm_metrics.get(rid) or {}
        cpu = metrics.get("avg_cpu_pct")
        net = metrics.get("avg_net_bytes_out")
        monthly = cost_by_resource.get(rid, 0.0)

        if cpu is None or monthly < 5.0:
            continue

        cpu_idle = cpu < _IDLE_CPU_THRESHOLD
        net_idle = net is not None and net < _IDLE_NET_BYTES_THRESHOLD

        if not cpu_idle:
            continue

        idle_type = IDLE_ZOMBIE_VM if net_idle else IDLE_TEMPORAL
        severity = "critical" if (cpu < 1.0 and net_idle) else ("high" if net_idle else "medium")

        signals.append(IdleSignal(
            resource_id=rid,
            resource_name=vm.get("name") or rid,
            resource_type="Microsoft.Compute/virtualMachines",
            idle_type=idle_type,
            severity=severity,
            idle_days=int(metrics.get("observation_days") or 0) or None,
            monthly_cost=round(monthly, 2),
            estimated_monthly_savings=round(monthly * 0.85, 2),
            description=(
                f"VM '{vm.get('name')}': CPU {cpu:.1f}%, "
                + (f"net {net:.0f} bytes/s — zombie candidate" if net_idle else "near-zero CPU")
            ),
            recommended_action="Deallocate or delete this VM — it appears to be unused.",
            evidence={"avg_cpu_pct": cpu, "avg_net_bytes_out": net, "monthly_cost_usd": monthly},
        ))
    return signals


def detect_idle_databases(
    sql_databases: list[dict],
    postgresql_instances: list[dict],
    db_metrics: dict[str, dict],
    cost_by_resource: dict[str, float],
) -> list[IdleSignal]:
    """Detect databases with no active connections for extended periods.

    Args:
        sql_databases: SQL Database resource dicts.
        postgresql_instances: PostgreSQL flexible server dicts.
        db_metrics: Resource ID → metrics with connection_count, max_connections_7d.
        cost_by_resource: Resource ID → monthly cost USD.

    Returns:
        IdleSignal list for databases with connection drought.
    """
    signals: list[IdleSignal] = []
    all_dbs = [
        (r, "Microsoft.Sql/servers/databases") for r in sql_databases
    ] + [
        (r, "Microsoft.DBforPostgreSQL/flexibleServers") for r in postgresql_instances
    ]

    for db, arm_type in all_dbs:
        rid = _norm_id(db.get("id") or "")
        metrics = db_metrics.get(rid) or {}
        max_conn = metrics.get("max_connections_7d")
        monthly = cost_by_resource.get(rid, 0.0)

        if monthly < 5.0:
            continue

        if max_conn is not None and max_conn == 0:
            signals.append(IdleSignal(
                resource_id=rid,
                resource_name=db.get("name") or rid,
                resource_type=arm_type,
                idle_type=IDLE_DB_NO_CONNECTIONS,
                severity="high",
                idle_days=_DB_CONNECTION_DROUGHT,
                monthly_cost=round(monthly, 2),
                estimated_monthly_savings=round(monthly * 0.90, 2),
                description=(
                    f"Database '{db.get('name')}' has had 0 connections for "
                    f">={_DB_CONNECTION_DROUGHT} days — likely unused."
                ),
                recommended_action=(
                    "Verify with the owning team and delete or pause the database if confirmed unused."
                ),
                evidence={"max_connections_7d": max_conn, "monthly_cost_usd": monthly},
            ))
    return signals


def detect_idle_storage(
    storage_accounts: list[dict],
    storage_metrics: dict[str, dict],
    cost_by_resource: dict[str, float],
) -> list[IdleSignal]:
    """Detect storage accounts with no read/write operations recently.

    Args:
        storage_accounts: Storage account dicts from inventory.
        storage_metrics: Resource ID → metrics with transactions_7d, last_access_days.
        cost_by_resource: Resource ID → monthly cost USD.

    Returns:
        IdleSignal list for unaccessed storage accounts.
    """
    signals: list[IdleSignal] = []
    for sa in storage_accounts:
        rid = _norm_id(sa.get("id") or "")
        metrics = storage_metrics.get(rid) or {}
        transactions = metrics.get("transactions_7d")
        last_access = metrics.get("last_access_days")  # days since last access
        monthly = cost_by_resource.get(rid, 0.0)

        if monthly < 2.0:
            continue

        is_idle = (
            (transactions is not None and transactions == 0) or
            (last_access is not None and last_access >= _STORAGE_ACCESS_DROUGHT)
        )
        if not is_idle:
            continue

        signals.append(IdleSignal(
            resource_id=rid,
            resource_name=sa.get("name") or rid,
            resource_type="Microsoft.Storage/storageAccounts",
            idle_type=IDLE_STORAGE_UNACCESSED,
            severity="medium",
            idle_days=last_access,
            monthly_cost=round(monthly, 2),
            estimated_monthly_savings=round(monthly * 0.80, 2),
            description=(
                f"Storage account '{sa.get('name')}': "
                + (f"0 transactions in 7 days" if transactions == 0 else f"{last_access} days since last access")
            ),
            recommended_action=(
                "Move to Cool/Archive tier or delete if confirmed empty and unused."
            ),
            evidence={"transactions_7d": transactions, "last_access_days": last_access},
        ))
    return signals


def detect_idle_serverless(
    logic_apps: list[dict],
    cost_by_resource: dict[str, float],
    invocation_metrics: dict[str, dict],
) -> list[IdleSignal]:
    """Detect Logic Apps / Function Apps with zero invocations.

    Args:
        logic_apps: Logic App resource dicts.
        cost_by_resource: Resource ID → monthly cost.
        invocation_metrics: Resource ID → metrics with runs_30d.

    Returns:
        IdleSignal list for zero-invocation serverless resources.
    """
    signals: list[IdleSignal] = []
    for app in logic_apps:
        rid = _norm_id(app.get("id") or "")
        metrics = invocation_metrics.get(rid) or {}
        runs = metrics.get("runs_30d")
        monthly = cost_by_resource.get(rid, 0.0)

        if monthly < 1.0 or runs is None:
            continue

        if runs == 0:
            signals.append(IdleSignal(
                resource_id=rid,
                resource_name=app.get("name") or rid,
                resource_type="Microsoft.Logic/workflows",
                idle_type=IDLE_ZERO_INVOCATIONS,
                severity="medium",
                idle_days=_ZERO_INVOCATION_DAYS,
                monthly_cost=round(monthly, 2),
                estimated_monthly_savings=round(monthly * 0.95, 2),
                description=(
                    f"Logic App '{app.get('name')}' had 0 runs in the last 30 days."
                ),
                recommended_action="Disable or delete the Logic App if no longer needed.",
                evidence={"runs_30d": runs, "monthly_cost_usd": monthly},
            ))
    return signals


def detect_idle_aks_pools(
    aks_clusters: list[dict],
    node_metrics: dict[str, dict],
    cost_by_resource: dict[str, float],
) -> list[IdleSignal]:
    """Detect AKS node pools with zero scheduled pods.

    Args:
        aks_clusters: AKS cluster resource dicts.
        node_metrics: Node pool ID → metrics with pods_running, pods_requested.
        cost_by_resource: Resource ID → monthly cost.

    Returns:
        IdleSignal list for empty AKS node pools.
    """
    signals: list[IdleSignal] = []
    for cluster in aks_clusters:
        cluster_id = _norm_id(cluster.get("id") or "")
        pools = (cluster.get("properties") or {}).get("agentPoolProfiles") or []
        for pool in pools:
            pool_name = (pool.get("name") or "").lower()
            pool_id = f"{cluster_id}/agentpools/{pool_name}"
            metrics = node_metrics.get(pool_id) or {}
            pods = metrics.get("pods_requested", metrics.get("pods_running"))
            node_count = pool.get("count") or 0
            monthly = cost_by_resource.get(pool_id, 0.0)

            if pods is None or monthly < 10.0 or node_count == 0:
                continue

            if pods == 0 and node_count > 0:
                signals.append(IdleSignal(
                    resource_id=pool_id,
                    resource_name=f"{cluster.get('name')}/{pool_name}",
                    resource_type="Microsoft.ContainerService/managedClusters/agentPools",
                    idle_type=IDLE_AKS_EMPTY_POOL,
                    severity="high",
                    idle_days=None,
                    monthly_cost=round(monthly, 2),
                    estimated_monthly_savings=round(monthly * 0.90, 2),
                    description=(
                        f"AKS node pool '{pool_name}' has {node_count} nodes but 0 scheduled pods."
                    ),
                    recommended_action="Scale node pool to 0 or enable cluster autoscaler.",
                    evidence={"node_count": node_count, "pods_requested": pods},
                ))
    return signals


def run_idle_pattern_scan(
    buckets: dict[str, list],
    cost_by_resource: dict[str, float],
    vm_metrics: dict[str, dict] | None = None,
    resource_metrics: dict[str, dict] | None = None,
    node_metrics: dict[str, dict] | None = None,
) -> list[IdleSignal]:
    """Run all idle detectors across the full inventory.

    Args:
        buckets: Full resource inventory bucket dict.
        cost_by_resource: Resource ID → monthly cost USD.
        vm_metrics: VM-level metrics dict.
        resource_metrics: General resource metrics dict (used for DB, storage).
        node_metrics: AKS node-level metrics dict.

    Returns:
        Combined list of IdleSignal sorted by estimated_monthly_savings descending.
    """
    vm_metrics       = vm_metrics or {}
    resource_metrics = resource_metrics or {}
    node_metrics     = node_metrics or {}

    all_signals: list[IdleSignal] = []

    all_signals.extend(detect_idle_vms(
        buckets.get("vms") or [], vm_metrics, cost_by_resource
    ))
    all_signals.extend(detect_idle_databases(
        buckets.get("sql_databases") or [],
        buckets.get("postgresql") or [],
        resource_metrics,
        cost_by_resource,
    ))
    all_signals.extend(detect_idle_storage(
        buckets.get("storage") or [], resource_metrics, cost_by_resource
    ))
    all_signals.extend(detect_idle_serverless(
        buckets.get("logic_apps") or [], cost_by_resource, resource_metrics
    ))
    all_signals.extend(detect_idle_aks_pools(
        buckets.get("aks_clusters") or [], node_metrics, cost_by_resource
    ))

    all_signals.sort(key=lambda s: s.estimated_monthly_savings, reverse=True)
    log.info(
        "idle_pattern_scan.done",
        total_signals=len(all_signals),
        zombie_vms=sum(1 for s in all_signals if s.idle_type == IDLE_ZOMBIE_VM),
        idle_dbs=sum(1 for s in all_signals if s.idle_type == IDLE_DB_NO_CONNECTIONS),
        unaccessed_storage=sum(1 for s in all_signals if s.idle_type == IDLE_STORAGE_UNACCESSED),
    )
    return all_signals

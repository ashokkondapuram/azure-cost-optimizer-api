"""Load Azure Monitor and K8s agent metrics for DB-first analysis."""

from __future__ import annotations

import json
import os
import re
import structlog
from collections import defaultdict
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import K8sUtilization, OptimizationFinding, OptimizationRun
from app.monitor_metrics import load_azure_monitor_metrics
from app.resource_type_map import internal_resource_type
from app.resource_utilization import MONITOR_FACT_KEYS
from app.focus_mapping import normalize_arm_id

log = structlog.get_logger(__name__)

_FETCH_MONITOR_DEFAULT = os.getenv("ANALYSIS_FETCH_MONITOR_METRICS", os.getenv("ANALYSIS_FETCH_VM_METRICS", "true")).lower() not in {"0", "false", "no"}
_K8S_METRICS_ROW_LIMIT = max(50, int(os.getenv("ANALYSIS_K8S_METRICS_LIMIT", "500")))

_CACHED_FACT_KEYS = MONITOR_FACT_KEYS | frozenset({
    "disk_iops_utilization_pct",
    "disk_throughput_utilization_pct",
    "disk_combined_iops",
    "provisioned_iops",
    "provisioned_mbps",
    "max_cpu_pct",
    "max_memory_pct",
    "max_disk_read_iops",
    "max_disk_write_iops",
    "max_disk_iops_utilization_pct",
})


def _parse_usage_value(raw: str | None) -> float | None:
    """Parse CPU/memory usage strings from the K8s agent (percent, millicores, bytes)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("%"):
        try:
            return float(text[:-1])
        except ValueError:
            return None
    if text.endswith("m"):
        try:
            return float(text[:-1]) / 10.0
        except ValueError:
            return None
    try:
        val = float(text)
        if 0 < val <= 1:
            return val * 100
        return val
    except ValueError:
        return None


def _monitor_payload(cpu: float | None, mem: float | None) -> dict[str, Any]:
    """Shape metrics like Azure Monitor responses for engine helpers."""
    value: list[dict[str, Any]] = []
    if cpu is not None:
        value.append({
            "name": {"value": "cpuUsage"},
            "timeseries": [{"data": [{"average": cpu}]}],
        })
    if mem is not None:
        value.append({
            "name": {"value": "memUsage"},
            "timeseries": [{"data": [{"average": mem}]}],
        })
    return {"value": value}


def group_resources_by_canonical_type(buckets: dict[str, list]) -> dict[str, list[dict]]:
    """Map engine inventory buckets to canonical resource types for monitor fetch."""
    from app.analysis import BUCKET_TO_TYPES

    grouped: dict[str, list[dict]] = defaultdict(list)
    for bucket_key, items in (buckets or {}).items():
        if bucket_key in {"budgets"} or not items:
            continue
        fallback_types = BUCKET_TO_TYPES.get(bucket_key, [])
        for item in items:
            rid = item.get("id") or ""
            canonical = internal_resource_type(rid) or (fallback_types[0] if len(fallback_types) == 1 else "")
            if not canonical and fallback_types:
                canonical = fallback_types[0]
            if canonical:
                grouped[canonical].append(item)
    return dict(grouped)


def analysis_inventory_buckets(**kwargs: list) -> dict[str, list]:
    """Normalize engine bucket keys for monitor fetch and optimization analysis."""
    keys = (
        "vms", "vmss", "disks", "snapshots", "aks_clusters", "container_registries",
        "storage", "public_ips", "load_balancers", "app_gateways", "nat_gateways",
        "sql_servers", "sql_databases", "cosmosdb", "postgresql", "redis_caches",
        "app_services", "app_service_plans", "keyvaults", "network_interfaces", "nsgs",
        "log_analytics_workspaces", "app_insights_components", "apim_services",
        "data_factories", "logic_apps", "event_hubs", "service_bus_namespaces",
        "databricks_workspaces", "synapse_workspaces", "adx_clusters", "ml_workspaces",
        "recovery_vaults", "cognitive_search_services", "firewalls", "cdn_profiles",
    )
    return {key: list(kwargs.get(key) or []) for key in keys}


def load_k8s_node_metrics(db: Session, aks_clusters: list[dict] | None = None) -> dict[str, dict]:
    """
    Build node_metrics dict from latest K8sUtilization rows.
    Keys are lower-case node names (matched by AKS pool prefix in the engine).
    """
    cluster_filter: set[str] | None = None
    if aks_clusters:
        cluster_filter = {(c.get("name") or "").lower() for c in aks_clusters if c.get("name")}

    rows = (
        db.query(K8sUtilization)
        .order_by(K8sUtilization.recorded_at.desc())
        .limit(_K8S_METRICS_ROW_LIMIT)
        .all()
    )
    seen_nodes: set[str] = set()
    out: dict[str, dict] = {}

    for row in rows:
        cluster = (row.cluster_name or "").lower()
        node = (row.node_name or "").strip()
        if not node:
            continue
        if cluster_filter is not None and cluster not in cluster_filter:
            continue
        node_key = node.lower()
        if node_key in seen_nodes:
            continue
        cpu = _parse_usage_value(row.cpu_usage)
        mem = _parse_usage_value(row.memory_usage)
        if cpu is None and mem is None:
            continue
        seen_nodes.add(node_key)
        payload = _monitor_payload(cpu, mem)
        out[node_key] = payload
        short = re.sub(r"[^a-z0-9-]", "", node_key)
        if short != node_key:
            out[short] = payload

    if out:
        log.info("metrics_loader.k8s_nodes_loaded", count=len(out))
    return out


def load_analysis_metrics(
    db: Session,
    *,
    buckets: dict[str, list],
    cost_by_resource: dict[str, Any],
    fetch_monitor_metrics: bool = _FETCH_MONITOR_DEFAULT,
) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict], dict[str, dict[str, float]], dict[str, Any]]:
    """
    Return (vm_metrics, node_metrics, resource_metrics, resource_facts).

    vm_metrics is a compatibility view for VM rules (subset of resource_metrics).
    resource_facts maps ARM id → extracted monitor fact keys from technical_fetch_specs.
    """
    from concurrent.futures import ThreadPoolExecutor

    node_metrics: dict[str, dict] = {}
    resource_metrics: dict[str, dict] = {}
    resource_facts: dict[str, dict[str, float]] = {}
    monitor_stats: dict[str, Any] = {}

    def _load_k8s() -> dict[str, dict]:
        try:
            return load_k8s_node_metrics(db, buckets.get("aks_clusters") or [])
        except Exception as exc:
            log.warning("metrics_loader.k8s_failed", error=str(exc))
            return {}

    def _load_monitor() -> tuple[dict[str, dict], dict[str, dict[str, float]], dict[str, Any]]:
        if not fetch_monitor_metrics:
            return {}, {}, {}
        try:
            grouped = group_resources_by_canonical_type(buckets)
            metrics, facts, stats = load_azure_monitor_metrics(
                grouped,
                cost_by_resource,
                db=db,
            )
            return metrics, facts, stats
        except Exception as exc:
            log.warning("metrics_loader.monitor_failed", error=str(exc))
            return {}, {}, {"errors": [str(exc)]}

    with ThreadPoolExecutor(max_workers=2) as pool:
        k8s_future = pool.submit(_load_k8s)
        monitor_future = pool.submit(_load_monitor)
        node_metrics = k8s_future.result()
        resource_metrics, resource_facts, monitor_stats = monitor_future.result()

    vm_metrics = {
        rid: payload
        for rid, payload in resource_metrics.items()
        if "/virtualmachines/" in rid or "/virtualmachinescalesets/" in rid
    }

    return vm_metrics, node_metrics, resource_metrics, resource_facts, monitor_stats


def _merge_cached_facts_from_evidence(
    out: dict[str, dict[str, float]],
    resource_id: str,
    evidence: dict[str, Any],
) -> None:
    rid = normalize_arm_id(resource_id or "").lower()
    if not rid or not evidence:
        return
    bucket = out.setdefault(rid, {})
    for key in _CACHED_FACT_KEYS:
        val = evidence.get(key)
        if val is None:
            continue
        try:
            bucket[key] = float(val)
        except (TypeError, ValueError):
            continue


def load_cached_resource_facts(db: Session, subscription_id: str) -> dict[str, dict[str, float]]:
    """
    Reuse monitor utilization facts from prior analysis runs (no Azure fetch).

    Sources: open findings evidence, then the latest optimization run snapshot.
    """
    sub = subscription_id.lower()
    out: dict[str, dict[str, float]] = {}

    open_rows = (
        db.query(OptimizationFinding)
        .filter(
            func.lower(OptimizationFinding.subscription_id) == sub,
            OptimizationFinding.status == "open",
        )
        .all()
    )
    for row in open_rows:
        try:
            evidence = json.loads(row.evidence_json or "{}")
        except Exception:
            evidence = {}
        _merge_cached_facts_from_evidence(out, row.resource_id or "", evidence)

    last_run = (
        db.query(OptimizationRun)
        .filter(func.lower(OptimizationRun.subscription_id) == sub)
        .order_by(OptimizationRun.analyzed_at.desc())
        .first()
    )
    if last_run and last_run.findings_json:
        try:
            findings = json.loads(last_run.findings_json or "[]")
        except Exception:
            findings = []
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            evidence = finding.get("evidence") or {}
            if isinstance(evidence, str):
                try:
                    evidence = json.loads(evidence)
                except Exception:
                    evidence = {}
            _merge_cached_facts_from_evidence(out, finding.get("resource_id") or "", evidence)

    if out:
        log.info("metrics_loader.cached_facts_loaded", subscription_id=sub, resources=len(out))
    return out


def analysis_metrics_summary(
    vm_metrics: dict[str, dict],
    node_metrics: dict[str, dict],
    resource_metrics: dict[str, dict] | None = None,
    resource_facts: dict[str, dict[str, float]] | None = None,
    monitor_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact metadata for API responses and run history."""
    monitor_count = len(resource_metrics or vm_metrics)
    summary: dict[str, Any] = {
        "vm_metrics_count": len(vm_metrics),
        "node_metrics_count": len(node_metrics),
        "monitor_metrics_count": monitor_count,
        "monitor_facts_count": len(resource_facts or {}),
        "sources": [
            s for s, ok in (
                ("azure_monitor", bool(monitor_count)),
                ("k8s_agent", bool(node_metrics)),
            ) if ok
        ],
    }
    if monitor_stats:
        summary["monitor_fetch"] = {
            k: monitor_stats[k]
            for k in ("requested", "loaded", "empty", "failed", "auth_failed", "timed_out", "errors", "source")
            if k in monitor_stats
        }
    return summary

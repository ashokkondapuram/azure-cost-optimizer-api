"""VMSS instance listing and per-node metrics for AKS agent pools."""

from __future__ import annotations

import os
from concurrent import futures
from typing import Any

import structlog

from app.monitor_metrics import (
    build_metrics_detail,
    enrich_derived_monitor_facts,
    extract_monitor_facts_from_profile,
    monitor_interval_for_timespan,
    parse_vmss_arm_id,
)
from app.resources.registry import get_monitor_profile
from it_services.containers_aks.vmss_match import vmss_id_for_pool

log = structlog.get_logger()


def _instance_id_from_vm(instance: dict[str, Any]) -> str:
    props = instance.get("properties") or {}
    for key in ("instanceId", "instance_id"):
        val = instance.get(key) or props.get(key)
        if val not in (None, ""):
            return str(val)
    name = str(instance.get("name") or "").strip()
    if name and "_" in name:
        return name.rsplit("_", 1)[-1]
    return name


def _computer_name(instance: dict[str, Any]) -> str:
    props = instance.get("properties") or {}
    os_profile = props.get("osProfile") or {}
    return str(
        os_profile.get("computerName")
        or instance.get("name")
        or ""
    ).strip()


def vmss_instance_power_state(instance: dict[str, Any]) -> str | None:
    """Power state from instanceView statuses when present."""
    props = instance.get("properties") or {}
    iv = props.get("instanceView") or instance.get("instanceView") or {}
    for status in iv.get("statuses") or []:
        code = str(status.get("code") or "")
        if code.startswith("PowerState/"):
            return code.split("/", 1)[1]
    prov = str(props.get("provisioningState") or "").strip()
    if prov and prov.lower() not in ("", "succeeded"):
        return prov
    return None


def _basic_instance_row(instance: dict[str, Any]) -> dict[str, Any]:
    inst_id = _instance_id_from_vm(instance)
    rid = str(instance.get("id") or "").strip()
    name = str(instance.get("name") or inst_id).strip()
    return {
        "id": rid,
        "name": name,
        "instance_id": inst_id,
        "power_state": vmss_instance_power_state(instance),
        "computer_name": _computer_name(instance),
    }


def _resolve_instance_rows(
    client: Any,
    subscription_id: str,
    vmss_id: str,
    cached_instances: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Prefer live Azure inventory; fall back to synced cache when list fails."""
    live = list_vmss_instances_basic(client, subscription_id, vmss_id)
    if live:
        return live
    return list(cached_instances or [])


def list_vmss_instances_basic(
    client: Any,
    subscription_id: str,
    vmss_id: str,
) -> list[dict[str, Any]]:
    """List VMSS VMs without metrics (sync / inventory)."""
    parsed = parse_vmss_arm_id(vmss_id)
    if not parsed:
        return []
    sub_id, resource_group, vmss_name = parsed
    try:
        raw = client.list_vm_scale_set_vms(sub_id or subscription_id, resource_group, vmss_name)
    except Exception as exc:
        log.debug("aks.pool_instances.list_failed", vmss_id=vmss_id, error=str(exc)[:120])
        return []
    rows = [_basic_instance_row(inst) for inst in (raw or []) if isinstance(inst, dict)]
    rows.sort(key=lambda row: str(row.get("instance_id") or row.get("name") or ""))
    return rows


def _metrics_from_detail(metrics_detail: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    cpu = mem = None
    for row in metrics_detail or []:
        key = row.get("fact_key")
        stats = row.get("stats") or {}
        val = stats.get("average")
        if val is None:
            val = stats.get("maximum")
        if val is None:
            continue
        if key in {"node_cpu_pct", "avg_cpu_pct"}:
            cpu = round(float(val), 2)
        elif key in {"node_mem_pct", "avg_memory_pct"}:
            mem = round(float(val), 2)
    return cpu, mem


def _match_k8s_instance(
    k8s_instances: list[dict[str, Any]],
    *,
    pool_name: str,
    computer_name: str,
    instance_name: str,
) -> dict[str, Any] | None:
    computer_lower = computer_name.lower()
    inst_lower = instance_name.lower()
    for row in k8s_instances or []:
        if row.get("pool_name") and row["pool_name"] != pool_name:
            continue
        node_key = str(row.get("name") or row.get("instance_id") or "").lower()
        if not node_key:
            continue
        if node_key == computer_lower or node_key == inst_lower:
            return row
        if computer_lower and (node_key in computer_lower or computer_lower in node_key):
            return row
        if inst_lower and (node_key in inst_lower or inst_lower in node_key):
            return row
    return None


def _fetch_vm_monitor_metrics(
    client: Any,
    instance_rid: str,
    *,
    vm_size: str | None,
    timespan: str,
    db: Any | None,
) -> tuple[float | None, float | None]:
    profile = get_monitor_profile(instance_rid)
    if profile is None or not profile.metrics:
        return None, None
    names = list(profile.metric_names())
    if not names:
        return None, None
    try:
        payload = client.get_resource_metrics(
            instance_rid,
            metric_names=names,
            timespan=timespan,
            interval=monitor_interval_for_timespan(timespan),
            aggregation=profile.aggregations(),
            db=db,
        )
    except Exception as exc:
        log.debug(
            "aks.pool_instance.metrics_failed",
            resource_id=instance_rid,
            error=str(exc)[:120],
        )
        return None, None
    facts = extract_monitor_facts_from_profile(payload or {}, profile)
    resource = {
        "id": instance_rid,
        "properties": {"hardwareProfile": {"vmSize": vm_size}} if vm_size else {},
    }
    facts = enrich_derived_monitor_facts(
        resource, profile.canonical_type, facts, payload,
    )
    cpu = facts.get("avg_cpu_pct")
    mem = facts.get("avg_memory_pct")
    return (
        round(float(cpu), 2) if cpu is not None else None,
        round(float(mem), 2) if mem is not None else None,
    )


def enrich_pool_vmss_instances(
    client: Any,
    subscription_id: str,
    pool_name: str,
    vmss_id: str,
    *,
    cluster_name: str = "",
    vm_size: str | None = None,
    k8s_instances: list[dict[str, Any]] | None = None,
    cached_instances: list[dict[str, Any]] | None = None,
    timespan: str = "P7D",
    db: Any | None = None,
) -> list[dict[str, Any]]:
    """Return VMSS instance rows with CPU/memory (K8s agent preferred, else Azure Monitor)."""
    base_rows = _resolve_instance_rows(client, subscription_id, vmss_id, cached_instances)
    if not base_rows:
        return []

    max_workers = max(1, min(4, int(os.getenv("AKS_POOL_INSTANCE_METRICS_WORKERS", "2"))))
    k8s_instances = k8s_instances or []

    def _enrich_one(row: dict[str, Any]) -> dict[str, Any]:
        out = {
            "id": row.get("id"),
            "name": row.get("name"),
            "instance_id": row.get("instance_id"),
            "power_state": row.get("power_state"),
        }
        k8s = _match_k8s_instance(
            k8s_instances,
            pool_name=pool_name,
            computer_name=str(row.get("computer_name") or row.get("name") or ""),
            instance_name=str(row.get("name") or ""),
        )
        if k8s:
            cpu, mem = _metrics_from_detail(k8s.get("metrics_detail") or [])
            if cpu is not None or mem is not None:
                out["cpu_pct"] = cpu
                out["mem_pct"] = mem
                out["source"] = "k8s_agent"
                return out

        rid = str(row.get("id") or "").strip()
        if rid:
            cpu, mem = _fetch_vm_monitor_metrics(
                client, rid, vm_size=vm_size, timespan=timespan, db=db,
            )
            if cpu is not None:
                out["cpu_pct"] = cpu
            if mem is not None:
                out["mem_pct"] = mem
            if cpu is not None or mem is not None:
                out["source"] = "azure_monitor"
        return out

    if len(base_rows) <= 1:
        enriched = [_enrich_one(row) for row in base_rows]
    else:
        with futures.ThreadPoolExecutor(max_workers=min(max_workers, len(base_rows))) as pool:
            enriched = list(pool.map(_enrich_one, base_rows))
    enriched.sort(key=lambda row: str(row.get("instance_id") or row.get("name") or ""))
    return enriched


def attach_vmss_instances_to_pools(
    client: Any,
    subscription_id: str,
    pools: list[dict[str, Any]],
    *,
    vmss_by_pool: dict[str, Any] | None = None,
    node_resource_group: str = "",
    vmss_list: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attach basic vmssInstances arrays to agent pool profiles during sync."""
    if not pools:
        return pools
    enriched: list[dict[str, Any]] = []
    for pool in pools:
        if not isinstance(pool, dict):
            continue
        next_pool = dict(pool)
        vmss_id = vmss_id_for_pool(
            pool,
            vmss_by_pool=vmss_by_pool,
            node_resource_group=node_resource_group,
            vmss_list=vmss_list,
        )
        if vmss_id:
            instances = list_vmss_instances_basic(client, subscription_id, vmss_id)
            if instances:
                next_pool["vmssInstances"] = [
                    {k: row[k] for k in ("id", "name", "instance_id", "power_state") if row.get(k) is not None}
                    for row in instances
                ]
        enriched.append(next_pool)
    return enriched


def fetch_aks_pool_instances(
    client: Any,
    subscription_id: str,
    *,
    cluster_name: str,
    pools: list[dict[str, Any]],
    pool_name: str | None = None,
    k8s_instances: list[dict[str, Any]] | None = None,
    timespan: str = "P7D",
    db: Any | None = None,
    vmss_by_pool: dict[str, Any] | None = None,
    node_resource_group: str = "",
    vmss_list: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Lazy-load VMSS instances (with metrics) for one or all agent pools."""
    out: dict[str, list[dict[str, Any]]] = {}
    for pool in pools or []:
        name = str(pool.get("name") or "").strip()
        if not name or (pool_name and name != pool_name):
            continue
        vmss_id = vmss_id_for_pool(
            pool,
            vmss_by_pool=vmss_by_pool,
            node_resource_group=node_resource_group,
            vmss_list=vmss_list,
        )
        if not vmss_id:
            out[name] = []
            continue
        cached = pool.get("vmssInstances")
        vm_size = str(pool.get("vmSize") or (pool.get("properties") or {}).get("vmSize") or "").strip() or None
        out[name] = enrich_pool_vmss_instances(
            client,
            subscription_id,
            name,
            vmss_id,
            cluster_name=cluster_name,
            vm_size=vm_size,
            k8s_instances=k8s_instances,
            cached_instances=cached,
            timespan=timespan,
            db=db,
        )
    return out

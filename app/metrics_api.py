"""API helpers — Azure Monitor metrics per resource type (profile-driven)."""

from __future__ import annotations

import os
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.azure_monitor_aggregations import azure_metrics_doc_url
from app.cost_db import resource_cost_map_from_db
from app.focus_mapping import normalize_arm_id
from app.metrics_catalog import (
    build_derived_metric_rows,
    build_unified_metric_row,
    cost_export_metrics_for_resource,
    list_full_catalog,
    sql_server_metrics_unavailable,
)
from app.metrics_loader import group_resources_by_canonical_type, load_k8s_node_metrics
from app.metrics_triggers import triggers_for_metrics
from app.monitor_metrics import (
    build_metrics_detail,
    extract_monitor_facts_from_profile,
    full_monitor_aggregations,
    load_azure_monitor_metrics,
    fetch_vmss_instance_metrics,
    monitor_interval_for_timespan,
)
from app.resource_store import apply_costs_to_resources, get_resources_db, list_all_resources_db, rows_to_list
from app.resources.extraction import extract_technical_facts
from app.resources.registry import get_monitor_profile, get_technical_fetch_spec, list_monitor_profiles
from app.resources.types import format_fact_display_value, infer_metric_metadata

log = structlog.get_logger(__name__)

_INVENTORY_META_KEYS = frozenset({
    "data_source",
    "arm_resource_type",
    "canonical_resource_type",
})


def _humanize_fact_key(fact_key: str) -> str:
    return (fact_key or "").replace("_", " ").strip().capitalize()


def _is_arm_resource_id(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    rid = value.strip().lower()
    return "/subscriptions/" in rid and "/providers/" in rid and "/resourcegroups/" in rid


def _short_arm_resource_label(resource_id: str) -> str:
    parts = resource_id.rstrip("/").split("/")
    return parts[-1] if parts else resource_id


def _format_inventory_value(value: Any, *, fact_key: str = "") -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, str) and _is_arm_resource_id(value):
        return _short_arm_resource_label(value)
    if isinstance(value, (int, float)) and fact_key:
        return format_fact_display_value(fact_key, value)
    if isinstance(value, (list, dict)):
        import json
        text = json.dumps(value, default=str)
        return text if len(text) <= 120 else f"{text[:117]}…"
    if isinstance(value, (int, float)):
        return format_fact_display_value(fact_key, value) if fact_key else f"{value:,}"
    return str(value)


def _load_inventory_row(db: Session | None, resource_id: str) -> dict[str, Any] | None:
    if db is None:
        return None
    from sqlalchemy import func

    from app.models import ResourceSnapshot

    rid = normalize_arm_id(resource_id)
    row = (
        db.query(ResourceSnapshot)
        .filter(
            func.lower(ResourceSnapshot.resource_id) == rid,
            ResourceSnapshot.is_active.is_(True),
        )
        .first()
    )
    if not row:
        return None
    items = rows_to_list([row])
    if not items:
        return None
    item = items[0]
    sub = (row.subscription_id or "").strip().lower()
    if sub:
        from app.resource_store import enrich_resource_row_costs

        item = enrich_resource_row_costs(item, db, sub)
    return item


def _inventory_properties_from_facts(
    facts: dict[str, Any],
    canonical_type: str,
) -> list[dict[str, Any]]:
    spec = get_technical_fetch_spec((canonical_type or "").strip().lower())
    label_by_key = {f.fact_key: f.label for f in (spec.fields if spec else ())}
    properties: list[dict[str, Any]] = []
    for key in sorted(facts):
        if key in _INVENTORY_META_KEYS:
            continue
        value = facts[key]
        if value is None or value == "":
            continue
        properties.append({
            "fact_key": key,
            "label": label_by_key.get(key) or _humanize_fact_key(key),
            "value": value,
            "unit": infer_metric_metadata(key, "Average")["unit"],
            "formatted": _format_inventory_value(value, fact_key=key),
        })
    return properties


def _resolve_canonical_type(resource_id: str, profile, inv_row: dict[str, Any] | None) -> str:
    if profile and profile.canonical_type:
        return profile.canonical_type
    if inv_row and inv_row.get("type"):
        return str(inv_row["type"]).strip().lower()
    from app.resource_type_map import internal_resource_type
    return internal_resource_type(resource_id) or ""


def _inventory_baseline_response(
    db: Session | None,
    resource_id: str,
    *,
    timespan: str = "P7D",
    profile=None,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    """Return synced inventory properties and cost context when live Monitor metrics are unavailable."""
    rid = _normalize_rid(resource_id)
    inv_row = _load_inventory_row(db, rid)
    ctype = _resolve_canonical_type(rid, profile, inv_row)
    if not profile and ctype:
        profile = get_monitor_profile(rid, ctype)

    facts: dict[str, Any] = {}
    if inv_row:
        facts = extract_technical_facts(inv_row, canonical_type=ctype or None)
        from app.cost_utils import monthly_cost_amounts_from_row

        billing, usd = monthly_cost_amounts_from_row(inv_row)
        monthly = billing if billing > 0 else usd
        if monthly > 0:
            facts.setdefault("monthly_cost_usd", monthly)

    inventory_properties = _inventory_properties_from_facts(facts, ctype)
    extra_metrics: list[dict[str, Any]] = []
    data_quality = "inventory"

    if db and ctype:
        proxy = cost_export_metrics_for_resource(db, rid, ctype)
        if proxy:
            extra_metrics = list(proxy.get("metrics") or [])
            data_quality = "inventory+cost_export" if inventory_properties else "cost_export_only"

    mapping = _cost_driver_mapping_for_response(
        rid,
        (profile.canonical_type if profile else None) or ctype or None,
    )
    has_content = bool(
        inventory_properties
        or extra_metrics
        or mapping.get("cost_drivers")
    )

    if not has_content:
        return {
            "ok": False,
            "resource_id": rid,
            "canonical_type": ctype or None,
            "error": unavailable_reason or "No inventory or metrics available for this resource.",
            "data_quality": "unavailable",
            "unavailable_reason": unavailable_reason,
            "inventory_properties": [],
            "cost_driver_mapping": mapping,
            "metrics": [],
            "derived": [],
        }

    if unavailable_reason and inventory_properties:
        data_quality = "inventory"

    return _shape_unified_response(
        ok=True,
        resource_id=rid,
        profile=profile,
        timespan=timespan,
        facts=facts,
        metrics_detail=[],
        instances=[],
        data_quality=data_quality,
        unavailable_reason=unavailable_reason,
        extra_metrics=extra_metrics or None,
        inventory_properties=inventory_properties,
    )


def _normalize_rid(resource_id: str) -> str:
    rid = (resource_id or "").strip()
    if not rid:
        return ""
    if not rid.startswith("/"):
        rid = f"/{rid}"
    return rid


def _profile_metric_map(profile) -> dict[str, Any]:
    return {m.fact_key: m for m in (profile.metrics if profile else ())}


def _fetch_aks_node_instances(
    db: Session,
    cluster_name: str,
    pools: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build per-node metric rows from K8s agent DB data."""
    if not cluster_name:
        return []
    node_metrics = load_k8s_node_metrics(db, [{"name": cluster_name}])
    if not node_metrics:
        return []
    instances: list[dict[str, Any]] = []
    prefix = cluster_name.lower()
    seen: set[str] = set()
    for node_key, payload in node_metrics.items():
        if node_key in seen:
            continue
        if not node_key.startswith(prefix) and prefix not in node_key:
            continue
        seen.add(node_key)
        cpu = None
        mem = None
        for series in payload.get("value", []):
            name = (series.get("name") or {}).get("value", "")
            for ts in series.get("timeseries", []):
                for point in ts.get("data", []):
                    val = point.get("average") or point.get("maximum")
                    if val is None:
                        continue
                    if name == "cpuUsage":
                        cpu = float(val)
                    elif name == "memUsage":
                        mem = float(val)
        metrics_detail: list[dict[str, Any]] = []
        if cpu is not None:
            metrics_detail.append({
                "metric_name": "node_cpu_usage",
                "fact_key": "node_cpu_pct",
                "label": "Node CPU utilization",
                "primary_aggregation": "Average",
                "unit": "percent",
                "stats": {"average": cpu, "maximum": cpu, "minimum": cpu},
            })
        if mem is not None:
            metrics_detail.append({
                "metric_name": "node_memory_usage",
                "fact_key": "node_mem_pct",
                "label": "Node memory utilization",
                "primary_aggregation": "Average",
                "unit": "percent",
                "stats": {"average": mem, "maximum": mem, "minimum": mem},
            })
        if not metrics_detail:
            continue
        pool_name = _match_aks_node_to_pool(node_key, cluster_name, pools or [])
        instances.append({
            "instance_id": node_key,
            "name": node_key,
            "resource_id": node_key,
            "pool_name": pool_name,
            "metrics_detail": metrics_detail,
            "source": "k8s_agent",
        })
    instances.sort(key=lambda r: str(r.get("name") or ""))
    return instances


def _cluster_name_from_rid(rid: str) -> str:
    return (rid.split("/")[-1] or "").strip()


def _aks_pools_from_inventory(inv_row: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not inv_row:
        return []
    props = inv_row.get("properties") or {}
    pools = props.get("agentPoolProfiles") or []
    return [p for p in pools if isinstance(p, dict) and p.get("name")]


def _match_aks_node_to_pool(node_key: str, cluster_name: str, pools: list[dict[str, Any]]) -> str | None:
    """Map a K8s node metric key to an agent pool name."""
    node_lower = (node_key or "").lower()
    if not node_lower or not pools:
        return None

    cluster_hint = ""
    node_name = node_lower
    if "/" in node_lower:
        cluster_hint, node_name = node_lower.split("/", 1)

    cname = cluster_name.lower()
    prefixes: list[tuple[str, str]] = []
    pool_names: list[str] = []
    for pool in pools:
        pname = pool.get("name") or ""
        if not pname:
            continue
        pool_names.append(pname.lower())
        prefixes.append((pname, f"{cname}-{pname.lower()}"))

    for pname, prefix in sorted(prefixes, key=lambda item: len(item[1]), reverse=True):
        if cluster_hint and cname != cluster_hint:
            continue
        if prefix in node_name or prefix in node_lower:
            return pname
    for pname in sorted(pool_names, key=len, reverse=True):
        if cluster_hint and cname != cluster_hint:
            continue
        if f"aks-{pname}" in node_name:
            return pname
    return None


def _aggregate_aks_pool_metrics(
    cluster_name: str,
    pools: list[dict[str, Any]],
    instances: list[dict[str, Any]],
    facts: dict[str, Any] | None = None,
    *,
    vmss_fallback: dict[str, dict[str, Any]] | None = None,
    vmss_by_pool: dict[str, Any] | None = None,
    node_resource_group: str = "",
) -> list[dict[str, Any]]:
    """Average per-node CPU/memory into agent pool utilization rows."""
    if not pools:
        return []

    from it_services.containers_aks.vmss_match import vmss_id_for_pool

    buckets: dict[str, dict[str, list[float] | int]] = {
        str(pool.get("name")): {"cpus": [], "mems": [], "nodes_with_metrics": 0}
        for pool in pools
        if pool.get("name")
    }
    for instance in instances or []:
        pool_name = instance.get("pool_name") or _match_aks_node_to_pool(
            str(instance.get("name") or instance.get("instance_id") or ""),
            cluster_name,
            pools,
        )
        if not pool_name or pool_name not in buckets:
            continue
        bucket = buckets[pool_name]
        cpu = mem = None
        for row in instance.get("metrics_detail") or []:
            key = row.get("fact_key")
            stats = row.get("stats") or {}
            val = stats.get("average")
            if val is None:
                val = stats.get("maximum")
            if val is None:
                continue
            if key == "node_cpu_pct":
                cpu = float(val)
            elif key == "node_mem_pct":
                mem = float(val)
        if cpu is not None:
            bucket["cpus"].append(cpu)  # type: ignore[union-attr]
        if mem is not None:
            bucket["mems"].append(mem)  # type: ignore[union-attr]
        if cpu is not None or mem is not None:
            bucket["nodes_with_metrics"] = int(bucket["nodes_with_metrics"]) + 1  # type: ignore[operator]

    def _avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    facts = facts or {}
    has_per_pool = any(int(b.get("nodes_with_metrics") or 0) > 0 for b in buckets.values())
    cluster_cpu = facts.get("cluster_cpu_pct")
    cluster_mem = facts.get("cluster_mem_pct")
    out: list[dict[str, Any]] = []
    for pool in pools:
        name = pool.get("name")
        if not name:
            continue
        bucket = buckets.get(name) or {"cpus": [], "mems": [], "nodes_with_metrics": 0}
        cpu_pct = _avg(bucket["cpus"])  # type: ignore[arg-type]
        mem_pct = _avg(bucket["mems"])  # type: ignore[arg-type]
        source = "node" if int(bucket.get("nodes_with_metrics") or 0) > 0 else None
        if cpu_pct is None and not has_per_pool and cluster_cpu is not None:
            cpu_pct = round(float(cluster_cpu), 2)
            source = source or "cluster"
        if mem_pct is None and not has_per_pool and cluster_mem is not None:
            mem_pct = round(float(cluster_mem), 2)
            source = source or "cluster"
        vmss_row = (vmss_fallback or {}).get(name) or {}
        if cpu_pct is None and vmss_row.get("cpu_pct") is not None:
            cpu_pct = round(float(vmss_row["cpu_pct"]), 2)
            source = source or "vmss"
        if mem_pct is None and vmss_row.get("mem_pct") is not None:
            mem_pct = round(float(vmss_row["mem_pct"]), 2)
            source = source or "vmss"
        out.append({
            "name": name,
            "cpu_pct": cpu_pct,
            "mem_pct": mem_pct,
            "nodes_with_metrics": int(bucket.get("nodes_with_metrics") or 0),
            "source": source,
            "vmss_id": vmss_row.get("vmss_id") or vmss_id_for_pool(
                pool,
                vmss_by_pool=vmss_by_pool,
                node_resource_group=node_resource_group,
            ) or None,
            "vmss_instance_count": vmss_row.get("instance_count"),
        })
    return out


def _enrich_pool_metrics_with_vmss_instances(
    client: Any,
    subscription_id: str,
    *,
    cluster_name: str,
    pools: list[dict[str, Any]],
    pool_metrics: list[dict[str, Any]],
    k8s_instances: list[dict[str, Any]],
    timespan: str,
    db: Session | None,
    vmss_by_pool: dict[str, Any] | None = None,
    node_resource_group: str = "",
) -> list[dict[str, Any]]:
    """Attach per-VMSS-instance CPU/memory rows to each pool_metrics entry."""
    if not pool_metrics or not pools:
        return pool_metrics

    from it_services.containers_aks.pool_instances import enrich_pool_vmss_instances
    from it_services.containers_aks.vmss_match import vmss_id_for_pool

    pools_by_name = {
        str(pool.get("name")): pool
        for pool in pools
        if pool.get("name")
    }
    enriched: list[dict[str, Any]] = []
    for row in pool_metrics:
        next_row = dict(row)
        pool_name = str(row.get("name") or "")
        pool = pools_by_name.get(pool_name) or {}
        vmss_id = str(row.get("vmss_id") or "").strip()
        if not vmss_id:
            vmss_id = vmss_id_for_pool(
                pool,
                vmss_by_pool=vmss_by_pool,
                node_resource_group=node_resource_group,
            )
        if not vmss_id:
            enriched.append(next_row)
            continue
        vm_size = str(pool.get("vmSize") or "").strip() or None
        cached = pool.get("vmssInstances")
        try:
            instances = enrich_pool_vmss_instances(
                client,
                subscription_id,
                pool_name,
                vmss_id,
                cluster_name=cluster_name,
                vm_size=vm_size,
                k8s_instances=k8s_instances,
                cached_instances=cached,
                timespan=timespan,
                db=db,
            )
        except Exception as exc:
            log.debug("aks_pool_vmss_instances_failed", pool=pool_name, error=str(exc)[:120])
            instances = []
        if instances:
            next_row["vmss_instances"] = instances
            next_row["vmss_instance_count"] = len(instances)
        enriched.append(next_row)
    return enriched


def _fetch_vmss_utilization_facts(
    client: Any,
    vmss_id: str,
    *,
    timespan: str,
    db: Session | None,
) -> dict[str, float]:
    from app.monitor_metrics import enrich_derived_monitor_facts

    profile = get_monitor_profile(vmss_id, "compute/vmss")
    if profile is None or not profile.metrics:
        return {}
    names = list(profile.metric_names())
    if not names:
        return {}
    payload = client.get_resource_metrics(
        vmss_id,
        metric_names=names,
        timespan=timespan,
        interval=monitor_interval_for_timespan(timespan),
        aggregation=profile.aggregations(),
        db=db,
    )
    facts = extract_monitor_facts_from_profile(payload or {}, profile)
    inv_row = _load_inventory_row(db, vmss_id) if db is not None else None
    resource = inv_row or {"id": vmss_id, "properties": {}}
    return enrich_derived_monitor_facts(resource, "compute/vmss", facts, payload)


def _embedded_vmss_instance_count(pool: dict[str, Any]) -> int | None:
    vmss_ref = pool.get("virtualMachineScaleSet")
    if isinstance(vmss_ref, dict):
        capacity = vmss_ref.get("capacity")
        if capacity is not None:
            try:
                return int(capacity)
            except (TypeError, ValueError):
                pass
    count = pool.get("count")
    if count is not None:
        try:
            return int(count)
        except (TypeError, ValueError):
            pass
    return None


def _aks_vmss_pool_fallback(
    db: Session | None,
    client: Any,
    *,
    subscription_id: str,
    pools: list[dict[str, Any]],
    inv_props: dict[str, Any] | None,
    timespan: str,
    pool_metrics: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Load VMSS Monitor utilization for pools that lack K8s or cluster metrics."""
    if db is None or not pools:
        return {}

    needs_fallback = {
        row["name"]
        for row in (pool_metrics or [])
        if row.get("name") and row.get("cpu_pct") is None and row.get("mem_pct") is None
    }
    if not needs_fallback:
        return {}

    from it_services.containers_aks.vmss_match import vmss_id_for_pool

    node_rg = str((inv_props or {}).get("nodeResourceGroup") or "").strip()
    vmss_by_pool = (inv_props or {}).get("_vmssByPool") or {}
    fallback: dict[str, dict[str, Any]] = {}
    for pool in pools:
        name = pool.get("name")
        if not name or name not in needs_fallback:
            continue
        vmss_id = vmss_id_for_pool(
            pool,
            vmss_by_pool=vmss_by_pool,
            node_resource_group=node_rg,
        )
        if not vmss_id:
            continue
        try:
            vmss_facts = _fetch_vmss_utilization_facts(
                client,
                vmss_id,
                timespan=timespan,
                db=db,
            )
        except Exception as exc:
            log.debug("aks_vmss_pool_metrics_failed", vmss_id=vmss_id, error=str(exc))
            continue
        cpu = vmss_facts.get("avg_cpu_pct")
        mem = vmss_facts.get("avg_memory_pct")
        if cpu is None and mem is None:
            continue
        inv_row = _load_inventory_row(db, vmss_id) or {}
        props = inv_row.get("properties") or {}
        fallback[name] = {
            "vmss_id": vmss_id,
            "cpu_pct": cpu,
            "mem_pct": mem,
            "instance_count": (
                _embedded_vmss_instance_count(pool)
                or props.get("instance_count")
                or props.get("vmss_instance_count")
            ),
        }
    return fallback


def _enrich_storage_facts_from_inventory(
    db: Session | None,
    rid: str,
    facts: dict[str, float],
) -> dict[str, float]:
    if not db or facts.get("storage_pct") is not None:
        return facts
    from app.models import ResourceSnapshot

    row = (
        db.query(ResourceSnapshot)
        .filter(ResourceSnapshot.resource_id == normalize_arm_id(rid))
        .first()
    )
    if not row:
        return facts
    try:
        import json
        props = json.loads(row.properties_json or "{}")
    except Exception:
        props = {}
    cap = props.get("capacity_bytes") or props.get("primaryEndpoints")
    used = facts.get("used_capacity_bytes")
    if used is not None and isinstance(cap, (int, float)) and float(cap) > 0:
        out = dict(facts)
        out["capacity_bytes"] = float(cap)
        out["storage_pct"] = round((float(used) / float(cap)) * 100.0, 4)
        return out
    return facts


def _shape_unified_response(
    *,
    ok: bool,
    resource_id: str,
    profile,
    timespan: str,
    facts: dict[str, Any],
    metrics_detail: list[dict[str, Any]],
    instances: list[dict[str, Any]] | None = None,
    data_quality: str = "azure_monitor",
    unavailable_reason: str | None = None,
    raw_payload: dict | None = None,
    extra_metrics: list[dict[str, Any]] | None = None,
    inventory_properties: list[dict[str, Any]] | None = None,
    pool_metrics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    mapping = _cost_driver_mapping_for_response(
        resource_id,
        profile.canonical_type if profile else None,
    )
    canonical_type = profile.canonical_type if profile else (mapping.get("canonical_type") or "")
    metric_map = _profile_metric_map(profile) if profile else {}
    unified = [
        build_unified_metric_row(row, metric_map.get(row.get("fact_key") or ""), facts)
        for row in metrics_detail
    ]
    if extra_metrics:
        unified.extend(extra_metrics)
    unified = triggers_for_metrics(unified)
    derived = build_derived_metric_rows(facts, canonical_type=canonical_type)
    derived = triggers_for_metrics(derived)

    metric_fact_keys = {
        str(row.get("fact_key") or "")
        for row in [*unified, *derived]
        if row.get("fact_key")
    }
    if inventory_properties and metric_fact_keys:
        inventory_properties = [
            row for row in inventory_properties
            if row.get("fact_key") not in metric_fact_keys
        ]

    # Backward-compatible fields
    metrics_summary = [
        {
            "fact_key": row["fact_key"],
            "label": row["label"],
            "metric_name": row.get("metric_name"),
            "aggregation": row.get("primary_stat"),
            "value": row.get("value"),
            "stats": row.get("stats"),
            "unit": row.get("unit"),
        }
        for row in unified
    ]

    display_name = profile.display_name if profile else mapping.get("display_name")

    return {
        "ok": ok,
        "source": "azure" if data_quality == "azure_monitor" else data_quality,
        "resource_id": resource_id,
        "canonical_type": canonical_type or None,
        "monitor_arm_type": profile.monitor_arm_type if profile else mapping.get("arm_type"),
        "display_name": display_name,
        "doc_ref": profile.doc_ref if profile else None,
        "doc_url": azure_metrics_doc_url(profile.doc_ref) if profile and profile.doc_ref else None,
        "timespan": timespan,
        "data_quality": data_quality,
        "unavailable_reason": unavailable_reason,
        "metric_names": list(profile.metric_names()) if profile and profile.metrics else [],
        "aggregations": (
            profile.aggregations().split(",")
            if profile and profile.metrics
            else full_monitor_aggregations().split(",")
        ),
        "facts": facts,
        "metrics": unified,
        "derived": derived,
        "metrics_summary": metrics_summary,
        "metrics_detail": metrics_detail,
        "instances": instances or [],
        "pool_metrics": pool_metrics or [],
        "metrics_raw": raw_payload,
        "cost_driver_mapping": mapping,
        "inventory_properties": inventory_properties or [],
    }


def _cost_driver_mapping_for_response(
    resource_id: str,
    canonical_type: str | None,
) -> dict[str, Any]:
    from app.resource_cost_mapping import cost_drivers_for_resource

    try:
        return cost_drivers_for_resource(resource_id, canonical_type)
    except Exception as exc:
        log.debug("cost_driver_mapping.failed", error=str(exc)[:120])
        return {"cost_drivers": [], "properties": [], "metrics": []}


def plan_for_resource(resource_id: str) -> dict[str, Any]:
    """Metric names and fact keys that apply to one ARM resource."""
    rid = _normalize_rid(resource_id)
    if not rid:
        return {"ok": False, "error": "resource_id is required"}

    unavailable = sql_server_metrics_unavailable(rid)
    if unavailable:
        return {"ok": False, "resource_id": rid, **unavailable}

    profile = get_monitor_profile(rid)
    if not profile:
        return {
            "ok": False,
            "resource_id": rid,
            "error": "No Azure Monitor profile for this resource type.",
            "data_quality": "unavailable",
            "hint": "See GET /resources/monitor-plan for supported types.",
        }

    if not profile.metrics:
        return {
            "ok": True,
            "resource_id": rid,
            "canonical_type": profile.canonical_type,
            "monitor_arm_type": profile.monitor_arm_type,
            "display_name": profile.display_name,
            "data_quality": "cost_export_only",
            "metrics": [],
            "hint": "This resource type uses cost data instead of Azure Monitor metrics.",
        }

    return {
        "ok": True,
        "resource_id": rid,
        "canonical_type": profile.canonical_type,
        "monitor_arm_type": profile.monitor_arm_type,
        "display_name": profile.display_name,
        "doc_ref": profile.doc_ref,
        "doc_url": azure_metrics_doc_url(profile.doc_ref),
        "timespan": profile.metrics[0].timespan if profile.metrics else "P7D",
        "data_quality": "azure_monitor",
        "metrics": [
            {
                "metric_name": m.metric_name,
                "fact_key": m.fact_key,
                "aggregation": m.aggregation,
                "description": m.description,
                "label": m.description,
                "unit": m.unit,
                "primary_stat": m.primary_stat,
                "display_stats": list(m.display_stats),
                "supported_aggregations": list(m.supported_aggregations),
                "impact": m.impact,
                "rules": list(m.rules),
            }
            for m in profile.metrics
        ],
    }


def fetch_metrics_for_resource(
    resource_id: str,
    *,
    timespan: str | None = None,
    db: Session | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Fetch Azure Monitor metrics using the profile for this resource's ARM type."""
    from app.azure_resources import AzureResourcesClient
    from app.auth import arm_auth_context, get_token
    from app.http_client import AzureAPIError
    from app.validators import coerce_metric_timespan

    timespan = coerce_metric_timespan(timespan)
    rid = _normalize_rid(resource_id)
    if not rid:
        return {"ok": False, "error": "resource_id is required", "data_quality": "unavailable"}

    if db is not None and not refresh:
        from app.resource_enrichment import load_metrics_payload_from_enrichment

        try:
            cached = load_metrics_payload_from_enrichment(db, rid)
            if cached:
                return cached
        except Exception as exc:
            import structlog
            structlog.get_logger().warning(
                "metrics_enrichment_cache_read_failed",
                resource_id=rid,
                error=str(exc)[:200],
            )

    unavailable = sql_server_metrics_unavailable(rid)
    if unavailable:
        return {"ok": False, "resource_id": rid, **unavailable}

    profile = get_monitor_profile(rid)
    if profile and profile.canonical_type == "compute/vmss":
        from app.inventory_standalone import is_standalone_inventory_type

        if not is_standalone_inventory_type(profile.canonical_type):
            return {
                "ok": False,
                "resource_id": rid,
                "canonical_type": profile.canonical_type,
                "data_quality": "unavailable",
                "error": (
                    "VM scale set metrics are available through the parent AKS cluster. "
                    "Open the cluster resource to view node pool utilization."
                ),
                "unavailable_reason": (
                    "Virtual machine scale sets backing AKS node pools are not queried directly."
                ),
                "cost_driver_mapping": _cost_driver_mapping_for_response(rid, profile.canonical_type),
                "inventory_properties": [],
            }

    if not profile:
        return _inventory_baseline_response(db, rid, timespan=timespan)

    if not profile.metrics:
        if db is not None:
            proxy = cost_export_metrics_for_resource(db, rid, profile.canonical_type)
            inv_row = _load_inventory_row(db, rid)
            inv_facts = (
                extract_technical_facts(inv_row, canonical_type=profile.canonical_type)
                if inv_row else {}
            )
            inv_props = _inventory_properties_from_facts(inv_facts, profile.canonical_type)
            if proxy:
                return _shape_unified_response(
                    ok=True,
                    resource_id=rid,
                    profile=profile,
                    timespan=timespan,
                    facts=inv_facts or {"monthly_cost_usd": proxy["metrics"][0]["value"]},
                    metrics_detail=[],
                    extra_metrics=proxy["metrics"],
                    data_quality=proxy["data_quality"],
                    inventory_properties=inv_props,
                )
        return _inventory_baseline_response(
            db, rid, timespan=timespan, profile=profile,
            unavailable_reason="No Azure Monitor metrics are configured for this resource type.",
        )

    names = list(profile.metric_names())
    ts = timespan
    agg = profile.aggregations()
    instances: list[dict[str, Any]] = []
    aks_pools: list[dict[str, Any]] = []
    if profile.canonical_type == "containers/aks" and db is not None:
        inv_row = _load_inventory_row(db, rid)
        aks_pools = _aks_pools_from_inventory(inv_row)

    client = AzureResourcesClient(db=db)
    try:
        with arm_auth_context(db=db, token=get_token(db) if db is not None else None):
            payload = client.get_resource_metrics(
                rid,
                metric_names=names,
                timespan=ts,
                interval=monitor_interval_for_timespan(ts),
                aggregation=agg,
                db=db,
            )
            if profile.canonical_type == "compute/vmss":
                instances = fetch_vmss_instance_metrics(
                    client,
                    rid,
                    profile,
                    timespan=ts,
                    db=db,
                )
            elif profile.canonical_type == "containers/aks" and db is not None:
                instances = _fetch_aks_node_instances(
                    db,
                    _cluster_name_from_rid(rid),
                    aks_pools,
                )
    except AzureAPIError as exc:
        if exc.status == 404 and db is not None:
            from app.db_sync import deactivate_inventory_resources_not_found

            if deactivate_inventory_resources_not_found(db, {rid}, source="metrics_api"):
                db.commit()
        baseline = _inventory_baseline_response(
            db,
            rid,
            timespan=ts,
            profile=profile,
            unavailable_reason=exc.message,
        )
        if baseline.get("ok"):
            return baseline
        return {
            "ok": False,
            "resource_id": rid,
            "canonical_type": profile.canonical_type,
            "data_quality": "unavailable",
            "status": exc.status,
            "code": exc.code,
            "error": exc.message,
            "unavailable_reason": exc.message,
            "cost_driver_mapping": _cost_driver_mapping_for_response(rid, profile.canonical_type),
            "inventory_properties": [],
        }
    except Exception as exc:
        log.warning(
            "metrics_resource_fetch_failed",
            resource_id=rid,
            canonical_type=profile.canonical_type,
            error=str(exc)[:300],
        )
        return {
            "ok": False,
            "resource_id": rid,
            "canonical_type": profile.canonical_type,
            "data_quality": "unavailable",
            "error": "Failed to fetch Azure Monitor metrics for this resource.",
            "unavailable_reason": str(exc)[:300],
            "cost_driver_mapping": _cost_driver_mapping_for_response(rid, profile.canonical_type),
            "inventory_properties": [],
        }

    facts = extract_monitor_facts_from_profile(payload or {}, profile)
    from app.monitor_metrics import enrich_derived_monitor_facts

    facts = enrich_derived_monitor_facts(
        {"id": rid, "properties": {}},
        profile.canonical_type,
        facts,
        payload,
    )
    if profile.canonical_type == "storage/account" and db is not None:
        facts = _enrich_storage_facts_from_inventory(db, rid, facts)

    metrics_detail = build_metrics_detail(payload or {}, profile)
    data_quality = "azure_monitor"
    if profile.canonical_type == "containers/aks" and instances:
        data_quality = "azure_monitor+k8s_agent"

    extra_metrics: list[dict[str, Any]] = []
    if db is not None:
        inv_row = _load_inventory_row(db, rid)
        if inv_row:
            from app.cost_utils import monthly_cost_amounts_from_row

            billing, usd = monthly_cost_amounts_from_row(inv_row)
            monthly = billing if billing > 0 else usd
            if monthly > 0:
                facts.setdefault("monthly_cost_usd", monthly)
        proxy = cost_export_metrics_for_resource(db, rid, profile.canonical_type)
        if proxy and proxy.get("metrics"):
            existing = {row.get("fact_key") for row in extra_metrics}
            for metric in proxy["metrics"]:
                if metric.get("fact_key") not in facts and metric.get("fact_key") not in existing:
                    extra_metrics.append(metric)

    pool_metrics: list[dict[str, Any]] = []
    if profile.canonical_type == "containers/aks":
        try:
            aks_inv = _load_inventory_row(db, rid) if db is not None else None
            inv_props = (aks_inv or {}).get("properties") or {}
            vmss_by_pool = inv_props.get("_vmssByPool") or {}
            node_resource_group = str(inv_props.get("nodeResourceGroup") or "").strip()
            pool_metrics = _aggregate_aks_pool_metrics(
                _cluster_name_from_rid(rid),
                aks_pools,
                instances,
                facts,
                vmss_by_pool=vmss_by_pool,
                node_resource_group=node_resource_group,
            )
            if db is not None and aks_pools:
                subscription_id = str((aks_inv or {}).get("subscription_id") or "").strip()
                vmss_fallback = _aks_vmss_pool_fallback(
                    db,
                    client,
                    subscription_id=subscription_id,
                    pools=aks_pools,
                    inv_props=inv_props,
                    timespan=ts,
                    pool_metrics=pool_metrics,
                )
                if vmss_fallback:
                    pool_metrics = _aggregate_aks_pool_metrics(
                        _cluster_name_from_rid(rid),
                        aks_pools,
                        instances,
                        facts,
                        vmss_fallback=vmss_fallback,
                        vmss_by_pool=vmss_by_pool,
                        node_resource_group=node_resource_group,
                    )
                pool_metrics = _enrich_pool_metrics_with_vmss_instances(
                    client,
                    subscription_id,
                    cluster_name=_cluster_name_from_rid(rid),
                    pools=aks_pools,
                    pool_metrics=pool_metrics,
                    k8s_instances=instances,
                    timespan=ts,
                    db=db,
                    vmss_by_pool=vmss_by_pool,
                    node_resource_group=node_resource_group,
                )
        except Exception as exc:
            log.warning(
                "aks_pool_metrics_enrichment_failed",
                resource_id=rid,
                error=str(exc)[:300],
            )
            pool_metrics = pool_metrics or []

    response = _shape_unified_response(
        ok=True,
        resource_id=rid,
        profile=profile,
        timespan=ts,
        facts=facts,
        metrics_detail=metrics_detail,
        instances=instances,
        data_quality=data_quality,
        raw_payload=payload,
        extra_metrics=extra_metrics or None,
        pool_metrics=pool_metrics or None,
    )
    if db is not None:
        _persist_metrics_enrichment_safe(db, rid, response, monitor_raw=payload)
    return response


def _persist_metrics_enrichment_safe(
    db: Session,
    resource_id: str,
    response: dict[str, Any],
    *,
    monitor_raw: dict[str, Any] | None = None,
) -> None:
    """Best-effort persistence; never fail the metrics API response."""
    if not response.get("ok"):
        return
    try:
        from app.assessment.normalizer import resource_row_to_dict
        from app.models import ResourceSnapshot
        from app.resource_enrichment import persist_metrics_enrichment

        rid = normalize_arm_id(resource_id)
        row = (
            db.query(ResourceSnapshot)
            .filter(ResourceSnapshot.resource_id == rid, ResourceSnapshot.is_active.is_(True))
            .first()
        )
        if not row:
            return
        row_dict = resource_row_to_dict(row)
        persist_metrics_enrichment(
            db,
            subscription_id=row.subscription_id,
            row_dict=row_dict,
            metrics_payload=response,
            facts=response.get("facts"),
            monitor_raw=monitor_raw or response.get("metrics_raw"),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        import structlog
        structlog.get_logger().warning(
            "metrics_enrichment_persist_failed",
            resource_id=resource_id,
            error=str(exc)[:300],
        )


def _persist_batch_metrics_enrichment(
    db: Session,
    subscription_id: str,
    resources: list[dict[str, Any]],
    resource_facts: dict[str, dict[str, Any]],
    *,
    timespan: str | None,
    resource_metrics: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Persist monitor facts from batch fetch into enrichment rows."""
    from app.resource_enrichment import persist_monitor_batch_results

    try:
        persist_monitor_batch_results(
            db,
            subscription_id,
            resources,
            resource_facts,
            timespan=timespan,
            resource_metrics=resource_metrics,
        )
        db.commit()
    except Exception:
        db.rollback()


def fetch_metrics_by_canonical_type(
    db: Session,
    subscription_id: str,
    canonical_type: str,
    *,
    timespan: str | None = None,
    limit_per_type: int = 0,
) -> dict[str, Any]:
    """Fetch monitor metrics for all DB resources of one canonical type."""
    sub = subscription_id.strip().lower()
    ctype = canonical_type.strip().lower()
    resources = get_resources_db(
        db, sub, ctype,
        include_properties=True,
        unpaginated=True,
    )
    if not resources:
        return {
            "ok": True,
            "subscription_id": sub,
            "canonical_type": ctype,
            "count": 0,
            "resources": [],
            "stats": {"requested": 0, "loaded": 0},
        }

    cost_map = resource_cost_map_from_db(db, sub)
    grouped = {ctype: resources}
    resource_metrics, resource_facts, stats = load_azure_monitor_metrics(
        grouped,
        cost_map,
        limit_per_type=limit_per_type,
        timespan=timespan,
        db=db,
    )

    _persist_batch_metrics_enrichment(
        db, sub, resources, resource_facts,
        timespan=timespan,
        resource_metrics=resource_metrics,
    )

    items = []
    for resource in resources:
        rid = (resource.get("id") or "").lower()
        if not rid:
            continue
        profile = get_monitor_profile(resource.get("id") or "", ctype)
        items.append({
            "resource_id": resource.get("id"),
            "name": resource.get("name"),
            "resource_group": resource.get("resourceGroup") or resource.get("resource_group"),
            "canonical_type": ctype,
            "display_name": profile.display_name if profile else ctype,
            "facts": resource_facts.get(rid, {}),
            "metrics": resource_metrics.get(rid),
            "has_metrics": rid in resource_metrics,
        })

    return {
        "ok": True,
        "source": "azure",
        "subscription_id": sub,
        "canonical_type": ctype,
        "count": len(items),
        "loaded": stats.get("loaded", 0),
        "stats": stats,
        "resources": items,
    }


def fetch_metrics_for_subscription(
    db: Session,
    subscription_id: str,
    *,
    canonical_type: str | None = None,
    timespan: str | None = None,
    limit_per_type: int = 0,
) -> dict[str, Any]:
    """Fetch monitor metrics for synced inventory (all types or one canonical type)."""
    sub = subscription_id.strip().lower()
    if canonical_type:
        return fetch_metrics_by_canonical_type(
            db, sub, canonical_type,
            timespan=timespan,
            limit_per_type=limit_per_type,
        )

    all_resources = list_all_resources_db(db, sub)
    buckets: dict[str, list] = {}
    for row in all_resources:
        ctype = (row.get("type") or row.get("canonical_type") or "").strip().lower()
        if not ctype:
            continue
        buckets.setdefault(ctype, []).append(row)

    cost_map = resource_cost_map_from_db(db, sub)
    grouped = group_resources_by_canonical_type({
        "vms": buckets.get("compute/vm", []),
        "disks": buckets.get("compute/disk", []),
        "vmss": buckets.get("compute/vmss", []),
        "aks_clusters": buckets.get("containers/aks", []),
        "container_registries": buckets.get("containers/acr", []),
        "storage": buckets.get("storage/account", []),
        "load_balancers": buckets.get("network/loadbalancer", []),
        "app_gateways": buckets.get("network/appgateway", []),
        "nat_gateways": buckets.get("network/nat", []),
        "sql_databases": buckets.get("database/sql", []),
        "cosmosdb": buckets.get("database/cosmosdb", []),
        "postgresql": buckets.get("database/postgresql", []),
        "redis_caches": buckets.get("database/redis", []),
        "app_services": buckets.get("appservice/webapp", []),
        "app_service_plans": buckets.get("appservice/plan", []),
        "keyvaults": buckets.get("security/keyvault", []),
        "public_ips": buckets.get("network/publicip", []),
        "nics": buckets.get("network/nic", []),
        "nsgs": buckets.get("network/nsg", []),
    })
    for ctype, rows in buckets.items():
        if ctype not in grouped and rows:
            grouped[ctype] = rows

    resource_metrics, resource_facts, stats = load_azure_monitor_metrics(
        grouped,
        cost_map,
        limit_per_type=limit_per_type,
        timespan=timespan,
        db=db,
    )

    all_resources: list[dict[str, Any]] = []
    for rows in grouped.values():
        all_resources.extend(rows)
    _persist_batch_metrics_enrichment(
        db, sub, all_resources, resource_facts,
        timespan=timespan,
        resource_metrics=resource_metrics,
    )

    by_type: dict[str, list] = {}
    for ctype, rows in grouped.items():
        for resource in rows:
            rid = (resource.get("id") or "").lower()
            if not rid:
                continue
            profile = get_monitor_profile(resource.get("id") or "", ctype)
            entry = {
                "resource_id": resource.get("id"),
                "name": resource.get("name"),
                "canonical_type": ctype,
                "display_name": profile.display_name if profile else ctype,
                "facts": resource_facts.get(rid, {}),
                "has_metrics": rid in resource_metrics,
            }
            if rid in resource_metrics:
                entry["metrics"] = resource_metrics[rid]
            by_type.setdefault(ctype, []).append(entry)

    return {
        "ok": True,
        "source": "azure",
        "subscription_id": sub,
        "types": len(by_type),
        "resource_count": sum(len(v) for v in by_type.values()),
        "loaded": stats.get("loaded", 0),
        "stats": stats,
        "by_type": by_type,
    }


def monitor_profiles_catalog() -> dict[str, Any]:
    catalog = list_full_catalog()
    return {
        "count": len(catalog),
        "profiles": catalog,
        # Backward compatible flat list
        "legacy_profiles": list_monitor_profiles(),
    }


def triggers_catalog() -> dict[str, Any]:
    from app.metrics_triggers import METRIC_TRIGGERS

    return {
        "count": len(METRIC_TRIGGERS),
        "triggers": {
            key: {
                "fact_key": t.fact_key,
                "direction": t.direction,
                "threshold": t.threshold,
                "effect_cost": t.effect_cost,
                "effect_performance": t.effect_performance,
                "rules": list(t.rules),
                "safety_gate": t.safety_gate or None,
            }
            for key, t in METRIC_TRIGGERS.items()
        },
    }


def resource_cost_mapping_catalog(
    canonical_type: str | None = None,
    *,
    resource_id: str | None = None,
) -> dict[str, Any]:
    from app.resource_cost_mapping import cost_drivers_for_resource, resource_cost_mapping

    if resource_id:
        return cost_drivers_for_resource(resource_id, canonical_type)
    return resource_cost_mapping(canonical_type)

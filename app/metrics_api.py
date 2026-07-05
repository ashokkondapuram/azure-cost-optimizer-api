"""API helpers — Azure Monitor metrics per resource type (profile-driven)."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.azure_monitor_aggregations import azure_metrics_doc_url
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
)
from app.resource_store import apply_costs_to_resources, get_resources_db, list_all_resources_db, rows_to_list
from app.resources.extraction import extract_technical_facts
from app.resources.registry import get_monitor_profile, get_technical_fetch_spec, list_monitor_profiles

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


def _format_inventory_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, str) and _is_arm_resource_id(value):
        return _short_arm_resource_label(value)
    if isinstance(value, (list, dict)):
        import json
        text = json.dumps(value, default=str)
        return text if len(text) <= 120 else f"{text[:117]}…"
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
        from app.cost_db import resource_cost_map_from_db

        cost_map = resource_cost_map_from_db(db, sub)
        item = apply_costs_to_resources([item], cost_map)[0]
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
            "formatted": _format_inventory_value(value),
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


def _fetch_aks_node_instances(db: Session, cluster_name: str) -> list[dict[str, Any]]:
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
        instances.append({
            "instance_id": node_key,
            "name": node_key,
            "resource_id": node_key,
            "metrics_detail": metrics_detail,
            "source": "k8s_agent",
        })
    instances.sort(key=lambda r: str(r.get("name") or ""))
    return instances


def _cluster_name_from_rid(rid: str) -> str:
    return (rid.split("/")[-1] or "").strip()


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
) -> dict[str, Any]:
    """Fetch Azure Monitor metrics using the profile for this resource's ARM type."""
    from app.azure_resources import AzureResourcesClient
    from app.auth import arm_auth_context, get_token
    from app.http_client import AzureAPIError

    rid = _normalize_rid(resource_id)
    if not rid:
        return {"ok": False, "error": "resource_id is required", "data_quality": "unavailable"}

    unavailable = sql_server_metrics_unavailable(rid)
    if unavailable:
        return {"ok": False, "resource_id": rid, **unavailable}

    profile = get_monitor_profile(rid)
    if not profile:
        return _inventory_baseline_response(db, rid, timespan=timespan or "P7D")

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
                    timespan=timespan or "P7D",
                    facts=inv_facts or {"monthly_cost_usd": proxy["metrics"][0]["value"]},
                    metrics_detail=[],
                    extra_metrics=proxy["metrics"],
                    data_quality=proxy["data_quality"],
                    inventory_properties=inv_props,
                )
        return _inventory_baseline_response(
            db, rid, timespan=timespan or "P7D", profile=profile,
            unavailable_reason="No Azure Monitor metrics are configured for this resource type.",
        )

    names = list(profile.metric_names())
    ts = timespan or profile.metrics[0].timespan or "P7D"
    agg = profile.aggregations()
    instances: list[dict[str, Any]] = []

    client = AzureResourcesClient(db=db)
    try:
        with arm_auth_context(db=db, token=get_token(db) if db is not None else None):
            payload = client.get_resource_metrics(
                rid,
                metric_names=names,
                timespan=ts,
                interval="PT1H",
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
                instances = _fetch_aks_node_instances(db, _cluster_name_from_rid(rid))
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

    return _shape_unified_response(
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
    )


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

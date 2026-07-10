"""Azure Monitor metrics — spec-driven fetch and fact extraction for all resource types."""

from __future__ import annotations

import os
import re
import structlog
from concurrent import futures
from typing import Any

from app.resources import (
    RESOURCE_MONITOR_PROFILES,
    TECHNICAL_FETCH_SPECS,
    ResourceMonitorProfile,
    TechnicalFetchSpec,
    UsageMetricDef,
    get_monitor_profile,
    get_technical_fetch_spec,
    monitor_arm_type,
    to_usage_metric_defs,
)
from app.resources.types import filter_stats_for_display

log = structlog.get_logger(__name__)

_MONITOR_TIMESPAN = os.getenv("ANALYSIS_MONITOR_METRICS_TIMESPAN", os.getenv("ANALYSIS_VM_METRICS_TIMESPAN", "P7D"))
_LIMIT_PER_TYPE = int(os.getenv("ANALYSIS_MONITOR_METRICS_LIMIT_PER_TYPE", os.getenv("ANALYSIS_VM_METRICS_LIMIT", "0")))
_TIMEOUT_SEC = max(5, int(os.getenv("ANALYSIS_MONITOR_METRICS_TIMEOUT_SEC", os.getenv("ANALYSIS_VM_METRICS_TIMEOUT_SEC", "120"))))
_MAX_WORKERS = max(1, min(8, int(os.getenv("ANALYSIS_MONITOR_METRICS_WORKERS", "6"))))

STANDARD_AGGREGATIONS: tuple[str, ...] = ("Average", "Minimum", "Maximum", "Total", "Count")
SERIES_AGG_KEYS: tuple[str, ...] = ("average", "minimum", "maximum", "total", "count")

_VMSS_ARM_RE = re.compile(
    r"/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/Microsoft\.Compute/virtualMachineScaleSets/([^/]+)$",
    re.IGNORECASE,
)


def full_monitor_aggregations() -> str:
    """Comma-separated aggregations requested from Azure Monitor."""
    return ",".join(STANDARD_AGGREGATIONS)


def _series_values(
    metrics: dict[str, Any] | None,
    metric_name: str,
    agg_key: str,
) -> list[float]:
    if not metrics:
        return []
    vals: list[float] = []
    for item in metrics.get("value", []):
        if (item.get("name") or {}).get("value") != metric_name:
            continue
        for ts in item.get("timeseries", []):
            for point in ts.get("data", []):
                val = point.get(agg_key)
                if val is None and agg_key == "average":
                    val = point.get("total")
                if val is not None:
                    try:
                        vals.append(float(val))
                    except (TypeError, ValueError):
                        continue
    return vals


def metric_statistics_from_payload(
    metrics: dict[str, Any] | None,
    metric_name: str,
    *,
    stat_keys: tuple[str, ...] | None = None,
) -> dict[str, float | None]:
    """Aggregate Azure Monitor series stats for one metric over the timespan."""
    keys = stat_keys or SERIES_AGG_KEYS
    stats: dict[str, float | None] = {k: None for k in keys}

    if "average" in keys:
        averages = _series_values(metrics, metric_name, "average")
        if averages:
            stats["average"] = round(sum(averages) / len(averages), 4)
    if "minimum" in keys:
        mins = _series_values(metrics, metric_name, "minimum")
        if mins:
            stats["minimum"] = round(min(mins), 4)
    if "maximum" in keys:
        maxs = _series_values(metrics, metric_name, "maximum")
        if maxs:
            stats["maximum"] = round(max(maxs), 4)
    if "total" in keys:
        totals = _series_values(metrics, metric_name, "total")
        if totals:
            stats["total"] = round(sum(totals), 4)
    if "count" in keys:
        counts = _series_values(metrics, metric_name, "count")
        if counts:
            stats["count"] = round(sum(counts), 4)
    return stats


def build_metrics_detail(
    metrics: dict[str, Any] | None,
    profile: ResourceMonitorProfile | None,
) -> list[dict[str, Any]]:
    """Per-metric Azure Monitor stats for API responses."""
    if not metrics or not profile:
        return []
    detail: list[dict[str, Any]] = []
    for metric_def in profile.metrics:
        raw_stats = metric_statistics_from_payload(
            metrics,
            metric_def.metric_name,
            stat_keys=metric_def.display_stats,
        )
        stats = filter_stats_for_display(raw_stats, metric_def.display_stats)
        if not any(v is not None for v in stats.values()):
            continue
        detail.append({
            "metric_name": metric_def.metric_name,
            "fact_key": metric_def.fact_key,
            "label": metric_def.description,
            "primary_aggregation": metric_def.aggregation,
            "unit": metric_def.unit,
            "primary_stat": metric_def.primary_stat,
            "display_stats": list(metric_def.display_stats),
            "supported_aggregations": list(metric_def.supported_aggregations),
            "impact": metric_def.impact,
            "stats": stats,
        })
    return detail


def parse_vmss_arm_id(resource_id: str) -> tuple[str, str, str] | None:
    """Return (subscription_id, resource_group, vmss_name) for a scale set ARM ID."""
    rid = _normalize_monitor_resource_id(resource_id)
    match = _VMSS_ARM_RE.search(rid)
    if not match:
        return None
    return match.group(1).lower(), match.group(2), match.group(3)


def fetch_vmss_instance_metrics(
    client: Any,
    vmss_resource_id: str,
    profile: ResourceMonitorProfile,
    *,
    timespan: str,
    db: Any | None = None,
) -> list[dict[str, Any]]:
    """Fetch per-instance metrics for every VM in a scale set."""
    parsed = parse_vmss_arm_id(vmss_resource_id)
    if not parsed or not profile.metrics:
        return []
    subscription_id, resource_group, vmss_name = parsed
    from app.http_client import arm_fetch_workers, arm_patient_active

    max_instances = max(1, int(os.getenv("VMSS_INSTANCE_METRICS_MAX", "50")))
    workers = max(1, min(8, int(os.getenv("VMSS_INSTANCE_METRICS_WORKERS", "2"))))
    if arm_patient_active():
        workers = 1
    else:
        workers = min(workers, arm_fetch_workers())

    try:
        instances = client.list_vm_scale_set_vms(subscription_id, resource_group, vmss_name)
    except Exception as exc:
        log.warning("vmss.instance_metrics.list_failed", vmss=vmss_name, error=str(exc))
        return []

    if not instances:
        return []

    instances = instances[:max_instances]
    names = list(profile.metric_names())
    agg = profile.aggregations()

    def _fetch_one(instance: dict[str, Any]) -> dict[str, Any] | None:
        inst_rid = (instance.get("id") or "").strip()
        if not inst_rid:
            return None
        try:
            payload = client.get_resource_metrics(
                inst_rid,
                metric_names=names,
                timespan=timespan,
                interval="PT1H",
                aggregation=agg,
                db=db,
            )
        except Exception as exc:
            log.debug(
                "vmss.instance_metrics.fetch_failed",
                vmss=vmss_name,
                instance=instance.get("name"),
                error=str(exc)[:120],
            )
            return None
        detail = build_metrics_detail(payload or {}, profile)
        if not detail:
            return None
        instance_id = str(instance.get("instanceId") or instance.get("name") or "")
        return {
            "instance_id": instance_id,
            "name": instance.get("name") or instance_id,
            "resource_id": inst_rid,
            "metrics_detail": detail,
        }

    results: list[dict[str, Any]] = []
    with futures.ThreadPoolExecutor(max_workers=min(workers, len(instances))) as pool:
        for row in pool.map(_fetch_one, instances):
            if row:
                results.append(row)
    results.sort(key=lambda r: str(r.get("instance_id") or r.get("name") or ""))
    return results


def metric_value_from_monitor_payload(
    metrics: dict[str, Any] | None,
    metric_name: str,
    *,
    aggregation: str = "Average",
) -> float | None:
    """Return a numeric value for one Azure Monitor metric series."""
    if not metrics:
        return None
    preferred = [aggregation, "Total", "Average", "Maximum", "Minimum", "Count"]
    seen: set[str] = set()
    order: list[str] = []
    for agg in preferred:
        key = (agg or "").lower()
        if key and key not in seen:
            seen.add(key)
            order.append(key)

    for item in metrics.get("value", []):
        if (item.get("name") or {}).get("value") != metric_name:
            continue
        for agg_key in order:
            vals: list[float] = []
            for ts in item.get("timeseries", []):
                for point in ts.get("data", []):
                    val = point.get(agg_key)
                    if val is None and agg_key == "average":
                        val = point.get("total")
                    if val is not None:
                        vals.append(float(val))
            if vals:
                if agg_key in {"total", "count"}:
                    return sum(vals)
                if agg_key == "maximum":
                    return max(vals)
                if agg_key == "minimum":
                    return min(vals)
                return sum(vals) / len(vals)
    return None


def average_from_monitor_payload(metrics: dict[str, Any] | None, metric_name: str) -> float | None:
    """Return the average value for one Azure Monitor metric series."""
    return metric_value_from_monitor_payload(metrics, metric_name, aggregation="Average")


def extract_monitor_facts_from_profile(
    metrics: dict[str, Any] | None,
    profile: ResourceMonitorProfile | None,
) -> dict[str, float]:
    """Map a Monitor payload to fact_key values using a resource monitor profile."""
    if not metrics or not profile:
        return {}
    out: dict[str, float] = {}
    for metric_def in profile.metrics:
        value = metric_value_from_monitor_payload(
            metrics,
            metric_def.metric_name,
            aggregation=metric_def.aggregation,
        )
        if value is None:
            continue
        out[metric_def.fact_key] = round(value, 4)
    return out


def _vm_sku_from_resource(resource: dict[str, Any]) -> str:
    props = resource.get("properties") or {}
    return (
        ((props.get("hardwareProfile") or {}).get("vmSize"))
        or ((props.get("virtualMachineProfile") or {}).get("hardwareProfile") or {}).get("vmSize")
        or resource.get("sku")
        or ""
    )


def enrich_derived_monitor_facts(
    resource: dict[str, Any],
    canonical: str,
    facts: dict[str, float],
    metrics: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Derive utilization percentages and other computed facts from raw monitor signals."""
    if not facts and not metrics:
        return facts

    out = dict(facts)
    if canonical in {"compute/vm", "compute/vmss"}:
        from app.vm_sizing import extract_vm_utilization

        sku = _vm_sku_from_resource(resource)
        util = extract_vm_utilization(metrics or {}, sku=sku if sku else None)
        if util.avg_cpu_pct is not None:
            out.setdefault("avg_cpu_pct", round(util.avg_cpu_pct, 4))
        if util.avg_memory_pct is not None:
            out["avg_memory_pct"] = round(util.avg_memory_pct, 4)
        if util.avg_available_memory_bytes is not None:
            out.setdefault("avg_available_memory_bytes", util.avg_available_memory_bytes)
        if metrics:
            max_cpu = metric_value_from_monitor_payload(metrics, "Percentage CPU", aggregation="Maximum")
            if max_cpu is not None:
                out["max_cpu_pct"] = round(max_cpu, 4)
            mem_gb_total = util.memory_gb_total
            if mem_gb_total and mem_gb_total > 0:
                min_avail = metric_value_from_monitor_payload(
                    metrics, "Available Memory Bytes", aggregation="Minimum",
                )
                if min_avail is not None:
                    total_bytes = mem_gb_total * (1024**3)
                    max_mem_pct = max(0.0, min(100.0, (1.0 - (min_avail / total_bytes)) * 100.0))
                    out["max_memory_pct"] = round(max_mem_pct, 4)
    elif canonical == "storage/account":
        used = out.get("storage_used_bytes") or out.get("used_capacity_bytes")
        cap = out.get("capacity_bytes")
        if used is not None and cap and float(cap) > 0:
            out["storage_pct"] = round((float(used) / float(cap)) * 100.0, 4)
    elif canonical == "compute/disk":
        from app.disk_utilization import (
            disk_iops_utilization_pct,
            disk_throughput_utilization_pct,
        )

        iops_util = disk_iops_utilization_pct({"_technical_facts": out}, resource)
        if iops_util is not None:
            out["disk_iops_utilization_pct"] = iops_util
        throughput_util = disk_throughput_utilization_pct({"_technical_facts": out}, resource)
        if throughput_util is not None:
            out["disk_throughput_utilization_pct"] = throughput_util
        if metrics:
            for metric_name, fact_key in (
                ("Composite Disk Read Operations/sec", "max_disk_read_iops"),
                ("Composite Disk Write Operations/sec", "max_disk_write_iops"),
            ):
                peak = metric_value_from_monitor_payload(metrics, metric_name, aggregation="Maximum")
                if peak is not None:
                    out[fact_key] = round(peak, 4)
            from app.disk_utilization import peak_disk_iops_utilization_pct

            peak_util = peak_disk_iops_utilization_pct({"_technical_facts": out}, resource)
            if peak_util is not None:
                out["max_disk_iops_utilization_pct"] = peak_util
    elif canonical == "database/redis":
        hits = out.get("cache_hits")
        misses = out.get("cache_misses")
        if hits is not None or misses is not None:
            total = float(hits or 0.0) + float(misses or 0.0)
            if total > 0:
                out["cache_hit_rate"] = round(float(hits or 0.0) / total * 100.0, 2)
        miss_rate = out.get("cache_miss_rate_pct")
        if miss_rate is not None and "cache_hit_rate" not in out:
            out["cache_hit_rate"] = round(max(0.0, min(100.0, 100.0 - float(miss_rate))), 2)
    elif canonical == "database/postgresql":
        active = out.get("active_connections")
        peak = out.get("max_connections")
        if active is not None and peak is not None and float(peak) > 0:
            out["connection_utilization_pct"] = round(float(active) / float(peak) * 100.0, 2)
    elif canonical == "database/cosmosdb":
        avg_ru = out.get("normalized_ru_pct")
        peak_ru = out.get("normalized_ru_peak_pct")
        if avg_ru is not None and peak_ru is not None and float(avg_ru) > 0:
            out["ru_skew_ratio"] = round(float(peak_ru) / float(avg_ru), 2)
        data_bytes = out.get("data_usage_bytes")
        doc_count = out.get("document_count")
        if data_bytes is not None and doc_count is not None and float(doc_count) > 0:
            out["avg_item_bytes"] = round(float(data_bytes) / float(doc_count), 2)
        index_bytes = out.get("index_usage_bytes")
        if index_bytes is not None and data_bytes is not None and float(data_bytes) > 0:
            out["index_to_data_ratio"] = round(float(index_bytes) / float(data_bytes), 2)
    elif canonical == "network/nat":
        from app.nat_gateway_catalog import snat_capacity_for_gateway

        snat_count = out.get("snat_connection_count")
        if snat_count is not None:
            capacity = snat_capacity_for_gateway(resource)
            if capacity > 0:
                out["snat_utilization_pct"] = round(float(snat_count) / capacity * 100.0, 2)
    elif canonical == "network/loadbalancer":
        used = out.get("used_snat_ports")
        allocated = out.get("allocated_snat_ports")
        if used is not None and allocated is not None and float(allocated) > 0:
            out["snat_port_usage_pct"] = round(float(used) / float(allocated) * 100.0, 2)
    elif canonical == "network/privateendpoint":
        inbound = out.get("pe_bytes_in")
        outbound = out.get("pe_bytes_out")
        if inbound is not None or outbound is not None:
            out["pe_bytes_total"] = round(float(inbound or 0.0) + float(outbound or 0.0), 2)
    elif canonical == "network/privatelinkservice":
        used = out.get("pls_nat_ports_used")
        allocated = out.get("pls_nat_ports_allocated")
        if used is not None and allocated is not None and float(allocated) > 0:
            out["pls_nat_port_usage_pct"] = round(float(used) / float(allocated) * 100.0, 2)
    elif canonical == "network/appgateway":
        avg_cu = out.get("billed_capacity_units")
        sku = resource.get("sku") or {}
        capacity = int(sku.get("capacity") or 1)
        if avg_cu is not None and capacity > 0:
            from app.app_gateway_catalog import tier_spec
            tier = sku.get("tier") or sku.get("name") or "Standard_v2"
            cu_per_unit = float(tier_spec(tier).get("cu_per_capacity_unit") or 100)
            provisioned = capacity * cu_per_unit
            if provisioned > 0:
                out["cu_utilization_pct"] = round(float(avg_cu) / provisioned * 100.0, 2)
    return out


def extract_monitor_facts(
    metrics: dict[str, Any] | None,
    spec: TechnicalFetchSpec | None,
    *,
    resource_id: str | None = None,
    canonical_type: str | None = None,
) -> dict[str, float]:
    """Map a Monitor payload to fact_key → numeric value using technical fetch specs."""
    if resource_id:
        profile = get_monitor_profile(resource_id, canonical_type or (spec.canonical_type if spec else None))
        if profile:
            return extract_monitor_facts_from_profile(metrics, profile)

    if not metrics or not spec:
        return {}
    out: dict[str, float] = {}
    for metric_def in spec.usage_metrics:
        if metric_def.source != "azure_monitor":
            continue
        value = metric_value_from_monitor_payload(
            metrics,
            metric_def.metric_name,
            aggregation=metric_def.aggregation,
        )
        if value is None:
            continue
        if metric_def.metric_name == "Available Memory Bytes" and metric_def.fact_key == "avg_mem_pct":
            continue
        out[metric_def.fact_key] = round(value, 4)
    return out


def monitor_metric_defs_for_type(canonical_type: str) -> tuple[UsageMetricDef, ...]:
    spec = get_technical_fetch_spec(canonical_type)
    if not spec:
        return ()
    return tuple(m for m in spec.usage_metrics if m.source == "azure_monitor")


def monitor_fetch_plan() -> dict[str, dict[str, Any]]:
    """canonical_type → {timespan, metrics, monitor_arm_types}."""
    plan: dict[str, dict[str, Any]] = {}
    for arm_type, profile in RESOURCE_MONITOR_PROFILES.items():
        if not profile.metrics:
            continue
        metric_defs = to_usage_metric_defs(profile)
        entry = plan.setdefault(profile.canonical_type, {
            "timespan": profile.metrics[0].timespan or _MONITOR_TIMESPAN,
            "metrics": [],
            "monitor_arm_types": [],
            "aggregations": "Average,Total",
        })
        entry["monitor_arm_types"].append(arm_type)
        seen = {(m["name"], m["fact_key"]) for m in entry["metrics"]}
        for m in metric_defs:
            item = {
                "name": m.metric_name,
                "fact_key": m.fact_key,
                "aggregation": m.aggregation,
                "monitor_arm_type": arm_type,
            }
            key = (item["name"], item["fact_key"])
            if key not in seen:
                seen.add(key)
                entry["metrics"].append(item)
        entry["aggregations"] = _aggregations_for_defs(list(metric_defs))
    return plan


def _aggregations_for_defs(monitor_defs: list[UsageMetricDef]) -> str:
    return full_monitor_aggregations()


def _cost_usd(cost_by_resource: dict[str, Any], rid: str) -> float:
    entry = cost_by_resource.get(rid) or cost_by_resource.get(rid.lower()) or {}
    if isinstance(entry, dict):
        return float(entry.get("usd") or entry.get("pretax") or 0)
    return float(entry or 0)


def _rank_by_cost(resources: list[dict], cost_by_resource: dict[str, Any]) -> list[dict]:
    return sorted(
        resources,
        key=lambda r: _cost_usd(cost_by_resource, (r.get("id") or "").lower()),
        reverse=True,
    )


def _normalize_monitor_resource_id(resource_id: str) -> str:
    rid = (resource_id or "").strip()
    if not rid:
        return ""
    if not rid.startswith("/"):
        rid = f"/{rid}"
    return rid


def _payload_has_series(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    for item in payload.get("value") or []:
        for ts in item.get("timeseries") or []:
            for point in ts.get("data") or []:
                if any(point.get(k) is not None for k in ("average", "total", "maximum", "minimum")):
                    return True
    return False


def load_azure_monitor_metrics(
    resources_by_type: dict[str, list[dict]],
    cost_by_resource: dict[str, Any],
    *,
    limit_per_type: int | None = None,
    timespan: str | None = None,
    db: Any | None = None,
) -> tuple[dict[str, dict], dict[str, dict[str, float]], dict[str, Any]]:
    """
    Fetch Azure Monitor metrics for all synced resources that have monitor specs.

    Returns:
        resource_metrics — lower-case ARM id → raw Monitor API payload
        resource_facts — lower-case ARM id → {fact_key: value}
    """
    limit = _LIMIT_PER_TYPE if limit_per_type is None else limit_per_type
    stats: dict[str, Any] = {
        "requested": 0,
        "loaded": 0,
        "empty": 0,
        "failed": 0,
        "auth_failed": 0,
        "timed_out": 0,
        "skipped_no_profile": 0,
        "not_found": 0,
        "deactivated": 0,
        "errors": [],
    }
    if not RESOURCE_MONITOR_PROFILES:
        return {}, {}, stats

    try:
        from app.azure_resources import AzureResourcesClient
        from app.auth import arm_auth_context, get_token
        from app.http_client import AzureAPIError
        client = AzureResourcesClient(db=db)
    except Exception as exc:
        log.warning("monitor_metrics.client_unavailable", error=str(exc))
        stats["errors"].append(str(exc))
        return {}, {}, stats

    jobs: list[tuple[str, str, str, tuple[str, ...], str, str]] = []
    for canonical, resources in resources_by_type.items():
        if not resources:
            continue
        ranked = _rank_by_cost([r for r in resources if r.get("id")], cost_by_resource)
        if limit and limit > 0:
            ranked = ranked[:limit]
        for resource in ranked:
            rid = _normalize_monitor_resource_id(resource.get("id") or "")
            if not rid:
                continue
            profile = get_monitor_profile(rid, canonical)
            if not profile or not profile.metrics:
                stats["skipped_no_profile"] += 1
                continue
            ts = timespan or profile.metrics[0].timespan or _MONITOR_TIMESPAN
            jobs.append((
                rid.lower(),
                rid,
                ts,
                profile.metric_names(),
                profile.aggregations(),
                canonical,
            ))

    if not jobs:
        return {}, {}, stats

    resource_metrics: dict[str, dict] = {}
    resource_facts: dict[str, dict[str, float]] = {}
    stats["requested"] = len(jobs)
    not_found_ids: set[str] = set()

    def _fetch(job: tuple[str, str, str, tuple[str, ...], str, str]) -> tuple[str, dict, str | None]:
        key, rid, ts, names, agg_param, _canonical = job
        try:
            payload = client.get_resource_metrics(
                rid,
                metric_names=list(names),
                timespan=ts,
                interval="PT1H",
                aggregation=agg_param,
                db=db,
            )
            payload = payload or {}
            if not _payload_has_series(payload):
                return key, {}, "empty"
            return key, payload, None
        except AzureAPIError as exc:
            if exc.status == 404:
                log.info(
                    "monitor_metrics.not_found",
                    resource_id=rid,
                    code=exc.code,
                )
            else:
                log.warning(
                    "monitor_metrics.fetch_failed",
                    resource_id=rid,
                    status=exc.status,
                    code=exc.code,
                    message=exc.message[:200],
                )
            return key, {}, f"{exc.status}:{exc.code}"
        except Exception as exc:
            log.warning("monitor_metrics.fetch_failed", resource_id=rid, error=str(exc)[:200])
            return key, {}, str(exc)[:120]

    workers = min(_MAX_WORKERS, len(jobs))
    with arm_auth_context(db=db, token=get_token(db) if db is not None else None):
        with futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_fetch, job) for job in jobs]
            done, not_done = futures.wait(futs, timeout=_TIMEOUT_SEC)
            for fut in done:
                try:
                    key, payload, err = fut.result()
                    if payload:
                        resource_metrics[key] = payload
                        stats["loaded"] += 1
                    elif err == "empty":
                        stats["empty"] += 1
                    elif err:
                        stats["failed"] += 1
                        if err.startswith("404:"):
                            stats["not_found"] += 1
                            not_found_ids.add(key)
                        if err.startswith("403:"):
                            stats["auth_failed"] += 1
                        if len(stats["errors"]) < 5:
                            stats["errors"].append(f"{key}: {err}")
                except Exception as exc:
                    stats["failed"] += 1
                    if len(stats["errors"]) < 5:
                        stats["errors"].append(str(exc)[:120])
            if not_done:
                timed_out = len(not_done)
                stats["timed_out"] = timed_out
                stats["failed"] += timed_out
                log.warning("monitor_metrics.timeout", pending=timed_out)
                if len(stats["errors"]) < 5:
                    stats["errors"].append(f"timed_out:{timed_out}")
                for fut in not_done:
                    fut.cancel()

    if not_found_ids and db is not None:
        try:
            from app.db_sync import deactivate_inventory_resources_not_found

            removed = deactivate_inventory_resources_not_found(
                db,
                not_found_ids,
                source="monitor_metrics",
            )
            stats["deactivated"] = removed
            if removed:
                db.commit()
        except Exception as exc:
            log.warning("monitor_metrics.deactivate_failed", error=str(exc)[:200])
            try:
                db.rollback()
            except Exception:
                pass

    resource_index: dict[str, tuple[dict, str]] = {}
    for canonical, resources in resources_by_type.items():
        for resource in resources:
            rid = (resource.get("id") or "").lower()
            if rid:
                resource_index[rid] = (resource, canonical)

    profile_cache: dict[tuple[str, str | None], ResourceMonitorProfile | None] = {}

    def _profile_for(resource: dict, canonical: str) -> ResourceMonitorProfile | None:
        arm_id = resource.get("id") or ""
        key = (monitor_arm_type(arm_id), canonical)
        if key not in profile_cache:
            profile_cache[key] = get_monitor_profile(arm_id, canonical)
        return profile_cache[key]

    for rid, payload in resource_metrics.items():
        entry = resource_index.get(rid)
        if not entry:
            continue
        resource, canonical = entry
        profile = _profile_for(resource, canonical)
        facts = extract_monitor_facts_from_profile(payload, profile)
        facts = enrich_derived_monitor_facts(resource, canonical, facts, payload)
        if facts:
            resource_facts[rid] = facts

    if resource_metrics:
        log.info(
            "monitor_metrics.loaded",
            resources=len(resource_metrics),
            types=len({canonical for canonical, items in resources_by_type.items() if items}),
            requested=stats["requested"],
            failed=stats["failed"],
            empty=stats["empty"],
            auth_failed=stats["auth_failed"],
            timed_out=stats.get("timed_out", 0),
        )
    elif stats["requested"]:
        log.warning(
            "monitor_metrics.none_loaded",
            requested=stats["requested"],
            failed=stats["failed"],
            empty=stats["empty"],
            auth_failed=stats["auth_failed"],
            timed_out=stats.get("timed_out", 0),
        )
    return resource_metrics, resource_facts, stats


def probe_monitor_metrics(
    resource_id: str,
    metric_names: list[str] | None = None,
    *,
    timespan: str = "P7D",
    db: Any | None = None,
) -> dict[str, Any]:
    """Test Azure Monitor access for one resource (permissions + metric names)."""
    from app.azure_resources import AzureResourcesClient
    from app.auth import arm_auth_context, get_token
    from app.http_client import AzureAPIError

    rid = _normalize_monitor_resource_id(resource_id)
    if not rid:
        return {"ok": False, "error": "resource_id is required"}

    names = metric_names
    if not names:
        profile = get_monitor_profile(rid)
        names = list(profile.metric_names()) if profile else ["Percentage CPU"]
    client = AzureResourcesClient(db=db)
    try:
        with arm_auth_context(db=db, token=get_token(db) if db is not None else None):
            payload = client.get_resource_metrics(
                rid,
                metric_names=names,
                timespan=timespan,
                interval="PT1H",
                aggregation="Average",
                db=db,
            )
        has_data = _payload_has_series(payload)
        return {
            "ok": True,
            "resource_id": rid,
            "metric_names": names,
            "has_data": has_data,
            "series_count": len((payload or {}).get("value") or []),
            "message": "Metrics returned data." if has_data else "Authorized, but no data points in the time range.",
        }
    except AzureAPIError as exc:
        hint = "Assign Monitoring Reader at subscription scope to the app identity."
        if exc.status == 403:
            hint = (
                "Monitoring Reader (or Reader) is required on the subscription for the app identity. "
                "Role assignments can take several minutes to apply."
            )
        return {
            "ok": False,
            "resource_id": rid,
            "status": exc.status,
            "code": exc.code,
            "error": exc.message,
            "hint": hint,
        }
    except Exception as exc:
        return {"ok": False, "resource_id": rid, "error": str(exc)}

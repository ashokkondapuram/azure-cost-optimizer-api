"""AKS optimization analysis rules."""
from __future__ import annotations

import json
import math
import structlog
from typing import Any

from app.aks_versions import is_minor_version_supported, normalize_k8s_minor
from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import aks_pool_cost_share
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from app.azure_retail_pricing import estimate_aks_spot_savings
from app.pricing.savings_calculator import savings_from_retail_or_none
from it_services.containers_aks.engine.helpers import aks_supported_minors, aks_version_catalog
from it_services.containers_aks.engine.optimization_rules import (
    evaluate_aks_node_memory_pressure,
    evaluate_aks_pod_density,
)
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import cpu_pct
from app.resource_utilization import fact_value
from app.resource_utilization import memory_pct
from app.resource_utilization import structured_evidence

log = structlog.get_logger()


def _append_metrics_draft(out, engine, subscription_id, resource, rule, draft):
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=resource,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def _pool_node_memory_gb(vm_size: str) -> float:
    """Approximate node memory from common AKS VM SKUs (fallback 8 GB)."""
    size = (vm_size or "").upper()
    if "_D" in size:
        return 8.0
    if "_E" in size:
        return 16.0
    return 8.0


def _consolidation_score(
    pool: dict,
    cluster: dict,
    *,
    node_hourly_cost: float = 0.15,
) -> dict[str, Any]:
    node_count = int(pool.get("count") or pool.get("nodeCount") or 0)
    vm_sku = pool.get("vmSize") or ""
    avg_cpu = cpu_pct(cluster) or fact_value(cluster, "node_cpu_pct") or 0.0
    avg_mem = memory_pct(cluster) or fact_value(cluster, "node_mem_pct") or 0.0
    node_vcpu = 2.0
    try:
        sku_json = pool.get("sku_json") or cluster.get("sku_json") or {}
        if isinstance(sku_json, str):
            sku_json = json.loads(sku_json or "{}")
        caps = (sku_json.get("capabilities") or {}) if isinstance(sku_json, dict) else {}
        node_vcpu = float(caps.get("vCPUs") or caps.get("vcpus") or 2.0)
    except (TypeError, ValueError, json.JSONDecodeError):
        node_vcpu = 2.0
    node_memory_gb = _pool_node_memory_gb(vm_sku)
    total_used_vcpu = node_count * node_vcpu * (avg_cpu / 100.0)
    total_used_mem = node_count * node_memory_gb * (avg_mem / 100.0)
    min_nodes_cpu = math.ceil(total_used_vcpu / node_vcpu / 0.8) if node_vcpu > 0 else node_count
    min_nodes_mem = math.ceil(total_used_mem / node_memory_gb / 0.8) if node_memory_gb > 0 else node_count
    recommended_nodes = max(min_nodes_cpu, min_nodes_mem, 2)
    removable = max(0, node_count - recommended_nodes)
    monthly_savings = round(removable * node_hourly_cost * 730, 2)
    return {
        "current_nodes": node_count,
        "recommended_nodes": recommended_nodes,
        "cpu_utilization_pct": round(avg_cpu, 2),
        "memory_utilization_pct": round(avg_mem, 2),
        "node_vcpu": node_vcpu,
        "node_memory_gb": node_memory_gb,
        "estimated_monthly_savings_usd": monthly_savings,
    }


def _pool_idle_nodes(
    engine,
    cluster: dict,
    pool: dict,
    node_metrics: dict[str, dict],
    idle_cpu_threshold: float,
) -> tuple[int, bool]:
    """Return (idle_node_count, cluster_level_idle) using envelope facts first."""
    count = int(pool.get("count") or pool.get("nodeCount") or 0)
    cluster_cpu = cpu_pct(cluster)
    cluster_mem = memory_pct(cluster)
    cluster_idle = (
        cluster_cpu is not None and cluster_cpu < idle_cpu_threshold
    ) or (
        cluster_mem is not None and cluster_mem < idle_cpu_threshold
    )

    node_cpu = fact_value(cluster, "node_cpu_pct")
    if node_cpu is not None and count > 0:
        return (count if node_cpu < idle_cpu_threshold else 0, cluster_idle)

    idle_nodes = 0
    cname = (cluster.get("name") or "").lower()
    prefix = f"{cname}-{pool.get('name', '')}".lower()
    for key, metric in node_metrics.items():
        if prefix and prefix in key.lower():
            cpu = engine._generic_metric_average(metric)
            if cpu is not None and cpu < idle_cpu_threshold:
                idle_nodes += 1
    return idle_nodes, cluster_idle


def analyze_aks(engine, subscription_id: str, clusters: list[dict], aks_node_pools: dict[str, list], node_metrics: dict[str, dict], cost_by_resource: dict[str, float]) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    idle_rule = engine.rules["AKS_IDLE_POOL_EXTENDED"]
    nonprod_rule = engine.rules["AKS_NONPROD_SCHEDULING"]
    reliability_rule = engine.rules["AKS_SYSTEM_POOL_RELIABILITY"]
    version_rule = engine.rules.get("AKS_OLD_VERSION_EXTENDED")
    autoscale_rule = engine.rules.get("AKS_NO_AUTOSCALER_EXTENDED")
    spot_rule = engine.rules.get("AKS_NO_SPOT_EXTENDED")
    single_pool_rule = engine.rules.get("AKS_SINGLE_NODE_POOL_EXTENDED")
    consolidation_rule = engine.rules.get("AKS_POOL_CONSOLIDATION")
    for cluster in clusters:
        cid = cluster.get("id") or ""
        cname = cluster.get("name") or ""
        tags = cluster.get("tags") or {}
        env = str(tags.get("environment") or tags.get("env") or "").lower()
        props = cluster.get("properties") or {}
        pools = aks_node_pools.get(cid) or aks_node_pools.get(cid.lower()) or (props.get("agentPoolProfiles") or [])
        cluster_cost = resource_cost(cost_by_resource, cid)
        total_nodes = sum(
            int(p.get("count") or p.get("nodeCount") or 0)
            for p in pools
        )
        cluster_cpu = cpu_pct(cluster)
        cluster_mem = memory_pct(cluster)

        k8s_ver = props.get("kubernetesVersion", "")
        minor = normalize_k8s_minor(k8s_ver)
        loc = (cluster.get("location") or "").strip()
        supported = aks_supported_minors(engine, subscription_id, loc) if loc else set()
        version_catalog = aks_version_catalog(engine, subscription_id, loc) if loc else {}
        supported_list = sorted(supported) if supported else version_catalog.get("supported_minors") or []
        version_supported = is_minor_version_supported(k8s_ver, supported)

        if version_rule and version_rule.enabled and minor and version_supported is False:
            default_ver = version_catalog.get("default_version")
            rec = f"Upgrade to a supported version for region '{loc}'"
            if default_ver:
                rec += f" (default: {default_ver})"
            rec += "."
            out.append(engine._finding(
                rule=version_rule,
                subscription_id=subscription_id,
                resource=cluster,
                detail=f"AKS cluster '{cname}' runs Kubernetes {k8s_ver}, which is not supported in {loc}.",
                recommendation=rec,
                savings=0,
                waste_score=50,
                confidence=90 if supported else 70,
                priority="P2",
                impact="Security and support compliance",
                evidence={
                    "kubernetes_version": k8s_ver,
                    "kubernetes_minor": minor,
                    "location": loc,
                    "supported_versions": supported_list,
                    "default_version": default_ver,
                    "version_source": "azure_arm",
                },
            ))
        elif version_rule and version_rule.enabled and minor and version_supported is None and loc:
            log.debug(
                "aks_version_check_skipped",
                cluster=cname,
                location=loc,
                reason="supported_versions_unavailable",
            )

        if single_pool_rule and single_pool_rule.enabled and len(pools) == 1:
            out.append(engine._finding(
                rule=single_pool_rule,
                subscription_id=subscription_id,
                resource=cluster,
                detail=f"AKS cluster '{cname}' has only one node pool — all workloads share the same nodes.",
                recommendation="Add a separate user node pool for workloads; keep the system pool lean.",
                savings=0,
                waste_score=30,
                confidence=85,
                priority="P3",
                impact="Improves workload isolation and scaling flexibility",
                evidence={"pool_count": len(pools)},
            ))

        if nonprod_rule.enabled and env in nonprod_rule.nonprod_tag_values:
            shutdown_savings = savings_from_factor(cluster_cost, nonprod_rule.nonprod_shutdown_hours_per_day / 24)
            out.append(engine._finding(
                rule=nonprod_rule,
                subscription_id=subscription_id,
                resource=cluster,
                detail=f"AKS cluster '{cname}' appears non-production (env={env}) and should use cost-aware runtime scheduling.",
                recommendation=f"Apply nightly shutdown or aggressive autoscaling to save up to {nonprod_rule.nonprod_shutdown_hours_per_day} hours/day of idle runtime.",
                savings=shutdown_savings,
                waste_score=58,
                confidence=76,
                priority="P2",
                impact="Substantial non-prod cluster savings",
                evidence={"environment": env, "pool_count": len(pools)},
            ))
        for pool in pools:
            mode = str(pool.get("mode") or "User")
            count = int(pool.get("count") or pool.get("nodeCount") or 0)
            pname = pool.get("name") or ""
            vm_sku = pool.get("vmSize") or ""
            asc = pool.get("enableAutoScaling") or pool.get("autoscaleEnabled")
            pool_cost = aks_pool_cost_share(cluster_cost, count, total_nodes)

            if consolidation_rule and consolidation_rule.enabled and count >= 3:
                score = _consolidation_score(pool, cluster, node_hourly_cost=pool_cost / max(count * 730, 1))
                if score["recommended_nodes"] < count:
                    out.append(engine._finding(
                        rule=consolidation_rule,
                        subscription_id=subscription_id,
                        resource=cluster,
                        detail=(
                            f"AKS pool '{pname}' on '{cname}' can consolidate from {count} to "
                            f"{score['recommended_nodes']} nodes based on CPU/memory headroom."
                        ),
                        recommendation=(
                            f"Scale the pool to {score['recommended_nodes']} nodes and enable cluster autoscaler "
                            "with an 80% utilization target."
                        ),
                        savings=score["estimated_monthly_savings_usd"],
                        waste_score=66,
                        confidence=confidence_with_monitor(74, cluster, boost=8),
                        priority="P2",
                        impact="Reduce persistent AKS node waste with a concrete target count",
                        evidence=structured_evidence(
                            cluster,
                            determination="pool_consolidation",
                            summary="AKS node pool has aggregate headroom for fewer nodes.",
                            extra={
                                "pool_name": pname,
                                **score,
                            },
                        ),
                    ))

            if autoscale_rule and autoscale_rule.enabled and not asc and count > autoscale_rule.node_count_min:
                out.append(engine._finding(
                    rule=autoscale_rule,
                    subscription_id=subscription_id,
                    resource=cluster,
                    detail=f"AKS pool '{pname}' on cluster '{cname}' has {count} nodes with autoscaler disabled.",
                    recommendation=f"Enable cluster autoscaler with min-count 1 and max-count {count}.",
                    savings=savings_from_factor(pool_cost, 0.30),
                    waste_score=75,
                    confidence=82,
                    priority="P1",
                    impact="Reduces over-provisioned node pool cost",
                    evidence={
                        "pool_name": pname,
                        "node_count": count,
                        "autoscaler_enabled": bool(asc),
                        "monthly_cost_usd": pool_cost,
                    },
                ))

            if spot_rule and spot_rule.enabled and mode.lower() != "system":
                spot_mode = str(pool.get("scaleSetPriority") or "").lower()
                if spot_mode != "spot" and env in spot_rule.spot_allowed_envs:
                    pricing = estimate_aks_spot_savings(
                        loc,
                        vm_sku,
                        count,
                        actual_monthly_cost=pool_cost if pool_cost > 0 else None,
                    )
                    savings = savings_from_retail_or_none(pricing)
                    if savings is None:
                        savings = savings_from_factor(pool_cost, 0.80) if pool_cost > 0 else 0
                    out.append(engine._finding(
                        rule=spot_rule,
                        subscription_id=subscription_id,
                        resource=cluster,
                        detail=f"AKS pool '{pname}' ({vm_sku} x{count}) on cluster '{cname}' uses on-demand nodes.",
                        recommendation="Use Spot node pool for interruptible workloads in non-production environments.",
                        savings=savings,
                        waste_score=65,
                        confidence=74,
                        priority="P2",
                        impact="Spot vs on-demand node pool savings from Azure retail pricing",
                        evidence={
                            "pool_name": pname,
                            "scale_set_priority": spot_mode or "regular",
                            "node_count": count,
                            "environment": env,
                            "monthly_cost_usd": pool_cost,
                            **pricing,
                        },
                    ))

            if reliability_rule.enabled and mode.lower() == "system" and env in reliability_rule.prod_tag_values and count < reliability_rule.aks_min_system_nodes:
                out.append(engine._finding(
                    rule=reliability_rule,
                    subscription_id=subscription_id,
                    resource=cluster,
                    detail=f"Production AKS cluster '{cname}' has only {count} system nodes.",
                    recommendation=f"Maintain at least {reliability_rule.aks_min_system_nodes} system nodes for resilient control-plane dependent workloads.",
                    savings=0,
                    waste_score=20,
                    confidence=90,
                    priority="P1",
                    impact="Reliability safeguard; avoid availability incidents",
                    evidence={"system_pool_count": count},
                ))
            if count > 0 and idle_rule.enabled:
                idle_nodes, cluster_idle = _pool_idle_nodes(
                    engine, cluster, pool, node_metrics, idle_rule.node_cpu_idle_pct,
                )
                has_utilization = cluster_cpu is not None or cluster_mem is not None or bool(node_metrics)
                pool_idle = (
                    idle_nodes and (idle_nodes / max(count, 1)) >= idle_rule.aks_max_idle_node_ratio
                ) or (cluster_idle and has_utilization)
                if pool_idle:
                    pool_cost = aks_pool_cost_share(cluster_cost, count, total_nodes)
                    idle_ratio = (idle_nodes / max(count, 1)) if idle_nodes else (1.0 if cluster_idle else 0.0)
                    idle_savings = round(idle_ratio * pool_cost, 2) if pool_cost > 0 else 0.0
                    idle_label = idle_nodes or (count if cluster_idle else 0)
                    out.append(engine._finding(
                        rule=idle_rule,
                        subscription_id=subscription_id,
                        resource=cluster,
                        detail=f"AKS pool '{pool.get('name')}' on cluster '{cname}' has {idle_label}/{count} idle nodes based on utilization metrics.",
                        recommendation="Lower max node count, enable autoscaler, and split noisy workloads into distinct pools.",
                        savings=idle_savings,
                        waste_score=74,
                        confidence=confidence_with_monitor(72 if has_utilization else 62, cluster, boost=10 if cluster_idle else 0),
                        priority="P1",
                        impact="Reduces persistent AKS node waste",
                        evidence=structured_evidence(
                            cluster,
                            determination="idle_node_pool",
                            summary="AKS node pool shows sustained low CPU or memory utilization.",
                            extra={
                                "idle_nodes": idle_nodes,
                                "node_count": count,
                                "cluster_cpu_pct": cluster_cpu,
                                "cluster_mem_pct": cluster_mem,
                                "pool_name": pool.get("name"),
                            },
                        ),
                    ))

        memory_rule = engine.rules.get("AKS_NODE_MEMORY_PRESSURE_EXTENDED")
        pod_rule = engine.rules.get("AKS_POD_DENSITY_EXTENDED")
        _append_metrics_draft(out, engine, subscription_id, cluster, memory_rule, evaluate_aks_node_memory_pressure(cluster, cluster_cost, memory_rule))
        _append_metrics_draft(out, engine, subscription_id, cluster, pod_rule, evaluate_aks_pod_density(cluster, cluster_cost, pod_rule))
    return out

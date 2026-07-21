"""Optimization Engine — analyses 500+ clusters and 1000+ resources.

Design:
  - Fully async-ready (sync wrappers for FastAPI background tasks)
  - Processes all resource types in parallel using ThreadPoolExecutor
  - Scoring: every finding gets a 0-100 waste_score + estimated_monthly_savings_usd
  - All thresholds overridable via EngineConfig (DB) or API payload
  - Zero Azure SDK calls here — pure analysis of already-fetched data
"""
from __future__ import annotations
import concurrent.futures
import structlog
from datetime import datetime, timezone, timedelta
from typing import Any
from app.optimizer.rules import Rule, Severity, Category
from app.appgateway_utils import http_listener_count
from app.cost_utils import resource_cost, savings_from_factor, aks_pool_cost_share
from app.azure_retail_pricing import estimate_vm_sku_savings, vm_os_type
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.disk_staleness import augment_disk_evidence, evaluate_unattached_disk, staleness_evidence
from app.vm_sizing import extract_vm_utilization, recommend_vm_sku, suggest_smaller_sku
from app.optimizer.resource_engines.compute.vm.helpers import idle_vm_action_text, sizing_action_label
from app.optimizer.standard_finding import Finding, extract_resource_group, extract_subscription_id
from app.optimizer.engine_runtime import build_standard_rules, filter_resources
from app.optimizer.engine_filters import should_skip_resource
from app.optimizer.post_analysis import run_post_analysis

from app.aks_versions import is_minor_version_supported, normalize_k8s_minor, supported_minors_for_location
from it_services.containers_aks.engine.helpers import is_node_auto_provisioning_enabled

log = structlog.get_logger()

_SYNC_BATCH_SIZE = 500


def _aks_pool_prefixes(clusters: list, node_pools: dict) -> list[str]:
    """Collect '{cluster}-{pool}' prefixes for AKS node metric indexing."""
    prefixes: list[str] = []
    for cluster in clusters:
        cname = cluster.get("name", "")
        if not cname:
            continue
        cid = cluster.get("id", "")
        pools = node_pools.get(cid, node_pools.get(cid.lower(), []))
        if not pools:
            pools = (cluster.get("properties") or {}).get("agentPoolProfiles", [])
        for pool in pools:
            pname = pool.get("name", "")
            if pname:
                prefixes.append(f"{cname}-{pname}".lower())
    return prefixes


def _index_aks_node_metrics(
    node_metrics: dict,
    clusters: list,
    node_pools: dict,
) -> dict[str, list[tuple[str, dict]]]:
    """Map '{cluster}-{pool}' prefix -> node metrics using per-cluster pool lists."""
    index: dict[str, list[tuple[str, dict]]] = {}
    cluster_prefixes: list[tuple[str, list[str], list[str]]] = []

    for cluster in clusters:
        cname = cluster.get("name", "")
        if not cname:
            continue
        cid = cluster.get("id", "")
        pools = node_pools.get(cid, node_pools.get(cid.lower(), []))
        if not pools:
            pools = (cluster.get("properties") or {}).get("agentPoolProfiles", [])
        prefixes: list[str] = []
        pool_names: list[str] = []
        for pool in pools:
            pname = pool.get("name", "")
            if pname:
                pool_names.append(pname.lower())
                prefix = f"{cname}-{pname}".lower()
                prefixes.append(prefix)
                index.setdefault(prefix, [])
        if prefixes:
            cluster_prefixes.append((
                cname.lower(),
                sorted(prefixes, key=len, reverse=True),
                sorted(pool_names, key=len, reverse=True),
            ))

    if not node_metrics or not cluster_prefixes:
        return index

    for key, nm in node_metrics.items():
        node_lower = key.lower()
        cluster_hint = ""
        node_name = node_lower
        if "/" in node_lower:
            cluster_hint, node_name = node_lower.split("/", 1)

        matched: str | None = None
        for cname, prefixes, pool_names in cluster_prefixes:
            if cluster_hint and cname != cluster_hint:
                continue
            for prefix in prefixes:
                if prefix in node_name or prefix in node_lower:
                    matched = prefix
                    break
            if matched:
                break
            for pname in pool_names:
                token = f"aks-{pname}"
                if token in node_name:
                    matched = f"{cname}-{pname}"
                    break
            if matched:
                break
        if matched:
            index.setdefault(matched, []).append((key, nm))

    return index


def _extract_sub(resource_id: str) -> str:
    return extract_subscription_id(resource_id)


def _extract_rg(resource_id: str) -> str:
    return extract_resource_group(resource_id)


def _passes_savings_gate(finding: Finding, rules: dict[str, Rule]) -> bool:
    """C5 — drop findings below per-rule min_monthly_savings_usd when savings > 0."""
    rule = rules.get(finding.rule_id)
    if not rule:
        return True
    min_savings = float(getattr(rule, "min_monthly_savings_usd", 0.0) or 0.0)
    if finding.estimated_savings_usd <= 0:
        return True
    return finding.estimated_savings_usd >= min_savings


# ─── Engine ───────────────────────────────────────────────────────────────────
class OptimizationEngine:
    """Main engine. Instantiate once, call .analyze() per subscription/scope."""

    def __init__(self, rule_overrides: dict[str, dict] | None = None, global_config: dict | None = None):
        """
        rule_overrides: per-rule threshold overrides, e.g.:
          { "VM_IDLE": {"cpu_idle_pct": 3.0, "enabled": False} }
        global_config: tag/RG/type filters under __global__ profile key.
        """
        from app.optimizer.engine_runtime import split_rule_overrides

        rule_only, inline_global = split_rule_overrides(rule_overrides)
        self.global_config = {**(global_config or {}), **inline_global}
        self.rules = build_standard_rules(rule_only)

    # ─── Public entry point ───────────────────────────────────────────────
    def analyze(
        self,
        *,
        vms:           list[dict] | None = None,
        disks:         list[dict] | None = None,
        snapshots:     list[dict] | None = None,
        aks_clusters:  list[dict] | None = None,
        aks_node_pools: dict[str, list] | None = None,  # cluster_id -> [node_pools]
        storage:       list[dict] | None = None,
        public_ips:    list[dict] | None = None,
        load_balancers: list[dict] | None = None,
        app_gateways:  list[dict] | None = None,
        app_services:  list[dict] | None = None,
        app_service_plans: list[dict] | None = None,
        network_interfaces: list[dict] | None = None,
        nat_gateways:  list[dict] | None = None,
        redis_caches:  list[dict] | None = None,
        sql_servers:   list[dict] | None = None,
        sql_databases: list[dict] | None = None,
        cosmosdb:      list[dict] | None = None,
        keyvaults:     list[dict] | None = None,
        vm_metrics:    dict[str, dict] | None = None,  # resource_id -> metrics
        node_metrics:  dict[str, dict] | None = None,  # node_name -> metrics
        cost_by_resource: dict | None = None,           # resourceId -> cost_usd
        budgets:       list[dict] | None = None,
        subscription_spend_usd: float = 0.0,
        expressroute_circuits: list[dict] | None = None,
        traffic_managers: list[dict] | None = None,
        front_doors: list[dict] | None = None,
        cdn_profiles: list[dict] | None = None,
        max_workers:   int = 4,
    ) -> dict:
        """Run all rule checks in parallel. Returns structured report."""
        log.info("engine.analyze.start",
                 vms=len(vms or []), aks=len(aks_clusters or []),
                 disks=len(disks or []), storage=len(storage or []))

        findings: list[Finding] = []
        gc = self.global_config

        tasks = [
            (self._check_vms,        (filter_resources(vms, gc), vm_metrics or {}, cost_by_resource or {})),
            (self._check_disks,      (filter_resources(disks, gc), cost_by_resource or {})),
            (self._check_snapshots,  (filter_resources(snapshots, gc), cost_by_resource or {})),
            (self._check_aks,        (filter_resources(aks_clusters, gc), aks_node_pools or {}, node_metrics or {}, cost_by_resource or {})),
            (self._check_storage,    (filter_resources(storage, gc),)),
            (self._check_network,    (filter_resources(public_ips, gc), filter_resources(load_balancers, gc), filter_resources(app_gateways, gc), filter_resources(network_interfaces, gc), filter_resources(nat_gateways, gc), cost_by_resource or {})),
            (self._check_app_services, (filter_resources(app_services, gc), filter_resources(app_service_plans, gc), cost_by_resource or {})),
            (self._check_redis,      (filter_resources(redis_caches, gc), cost_by_resource or {})),
            (self._check_databases,  (filter_resources(sql_servers, gc), filter_resources(sql_databases, gc), filter_resources(cosmosdb, gc))),
            (self._check_security,   (filter_resources(keyvaults, gc),)),
            (self._check_cost,       (budgets or [], subscription_spend_usd)),
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(fn, *args): fn.__name__ for fn, args in tasks}
            for fut in concurrent.futures.as_completed(futures):
                name = futures[fut]
                try:
                    findings.extend(fut.result())
                except Exception as exc:
                    log.error("engine.task.failed", task=name, error=str(exc))

        sub_id = _subscription_id_from(
            vms, sql_databases, public_ips, app_services, aks_clusters, storage,
        )
        costs = cost_by_resource or {}
        buckets = {
            "vms": vms or [],
            "disks": disks or [],
            "storage": storage or [],
            "public_ips": public_ips or [],
            "sql_databases": sql_databases or [],
            "app_services": app_services or [],
            "load_balancers": load_balancers or [],
            "aks_clusters": aks_clusters or [],
            "traffic_managers": traffic_managers or [],
            "front_doors": front_doors or [],
            "expressroute_circuits": expressroute_circuits or [],
            "cdn_profiles": cdn_profiles or [],
        }
        findings.extend(run_post_analysis(self, buckets=buckets, cost_by_resource=costs, subscription_id=sub_id))
        findings = [f for f in findings if _passes_savings_gate(f, self.rules)]
        findings.sort(key=lambda f: _severity_rank(f.severity))

        total_savings = sum(f.estimated_savings_usd for f in findings)
        summary = _build_summary(findings, total_savings)

        log.info("engine.analyze.done", findings=len(findings), total_savings=total_savings)
        return {
            "summary": summary,
            "findings": [f.to_dict() for f in findings],
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

    # ─── COMPUTE: VMs ─────────────────────────────────────────────────────
    def _check_vms(self, vms: list, metrics: dict, costs: dict) -> list[Finding]:
        out = []
        rule_idle     = self.rules["VM_IDLE"]
        rule_over     = self.rules["VM_OVERSIZE"]
        rule_stopped  = self.rules["VM_STOPPED_DEALLOCATED"]
        rule_ri       = self.rules["VM_NO_RESERVED"]
        rule_spot     = self.rules["SPOT_OPPORTUNITY"]

        for vm in vms:
            if should_skip_resource(vm, self.global_config):
                continue
            if not rule_idle.enabled and not rule_over.enabled:
                continue
            rid  = vm.get("id", "")
            name = vm.get("name", "")
            props = vm.get("properties", {})
            hw    = props.get("hardwareProfile", {})
            sku   = hw.get("vmSize", "")
            cost  = resource_cost(costs, rid)

            # Power state from instanceView
            iv = props.get("instanceView", {})
            statuses = iv.get("statuses", [])
            power = next((s.get("code", "") for s in statuses
                          if s.get("code", "").startswith("PowerState")), "")

            # Stopped (not deallocated) — still billed
            if rule_stopped.enabled and power == "PowerState/stopped":
                out.append(Finding(
                    rule_stopped, vm,
                    detail=f"VM '{name}' is stopped (not deallocated) — still billed for compute.",
                    recommendation="Run: az vm deallocate --name {name} --resource-group <rg>",
                    savings=cost, score=90,
                    evidence={
                        "power_state": power.replace("PowerState/", ""),
                        "vm_size": sku,
                        "monthly_cost_usd": cost,
                    },
                ))
                continue

            # CPU metrics-based checks
            m = metrics.get(rid.lower()) or metrics.get(rid)
            avg_cpu = _avg_metric(m, "Percentage CPU") if m else None
            util = extract_vm_utilization(m, sku=sku) if m else None
            avg_mem = util.avg_memory_pct if util else None

            if avg_cpu is not None:
                if rule_idle.enabled and avg_cpu < rule_idle.cpu_idle_pct:
                    idle_rec = (
                        recommend_vm_sku(
                            current_sku=sku,
                            utilization=util,
                            cpu_down_pct=rule_idle.cpu_idle_pct,
                            memory_down_pct=rule_idle.mem_idle_pct,
                        )
                        if util and sku
                        else None
                    )
                    idle_sku = (
                        idle_rec.suggested_sku
                        if idle_rec and idle_rec.suggested_sku and idle_rec.action in {"downgrade", "cross_family"}
                        else None
                    )
                    idle_action = idle_vm_action_text(idle_rec)
                    out.append(Finding(
                        rule_idle, vm,
                        detail=f"VM '{name}' avg CPU {avg_cpu:.1f}% over 7d (threshold {rule_idle.cpu_idle_pct}%). SKU: {sku}.",
                        recommendation=f"Deallocate if unused. {idle_action}",
                        savings=savings_from_factor(cost, 0.90), score=85,
                        evidence={
                            "avg_cpu_pct": round(avg_cpu, 2),
                            "avg_memory_pct": round(avg_mem, 2) if avg_mem is not None else None,
                            "cpu_threshold_pct": rule_idle.cpu_idle_pct,
                            "vm_size": sku,
                            "suggested_sku": idle_sku,
                            "sizing_action": idle_rec.action if idle_rec else None,
                            "monthly_cost_usd": cost,
                            "power_state": power.replace("PowerState/", "") if power else "unknown",
                        },
                    ))
                elif rule_over.enabled and util and (util.has_cpu or util.has_memory):
                    rec = recommend_vm_sku(
                        current_sku=sku,
                        utilization=util,
                        cpu_down_pct=rule_over.cpu_oversize_pct,
                        memory_down_pct=rule_over.mem_idle_pct,
                    )
                    if rec and rec.suggested_sku and rec.action in {"downgrade", "cross_family"}:
                        target_sku = rec.suggested_sku
                        pricing = estimate_vm_sku_savings(
                            vm.get("location") or "",
                            sku,
                            target_sku,
                            os_type=vm_os_type(vm),
                            actual_monthly_cost=cost if cost > 0 else None,
                        )
                        savings = savings_from_retail_or_none(pricing)
                        if savings is None:
                            savings = 0.0
                        current_retail = pricing.get("current_sku_monthly_usd")
                        suggested_retail = pricing.get("suggested_sku_monthly_usd")
                        price_note = ""
                        if current_retail is not None and suggested_retail is not None:
                            price_note = (
                                f" Azure retail pricing: {sku} ~${current_retail:,.2f}/mo → "
                                f"{target_sku} ~${suggested_retail:,.2f}/mo "
                                f"(est. savings ${savings:,.2f}/mo)."
                            )
                        verb = sizing_action_label(rec.action)
                        out.append(Finding(
                            rule_over, vm,
                            detail=(
                                f"VM '{name}' averages {avg_cpu:.1f}% CPU"
                                + (f" and {avg_mem:.1f}% memory" if avg_mem is not None else "")
                                + f" (threshold {rule_over.cpu_oversize_pct}%). SKU: {sku}."
                            ),
                            recommendation=f"{verb} {sku} → {target_sku}.{price_note}",
                            savings=savings,
                            score=60,
                            evidence={
                                "avg_cpu_pct": round(avg_cpu, 2),
                                "avg_memory_pct": round(avg_mem, 2) if avg_mem is not None else None,
                                "cpu_oversize_threshold_pct": rule_over.cpu_oversize_pct,
                                "vm_size": sku,
                                "suggested_sku": target_sku,
                                "sizing_action": rec.action,
                                "monthly_cost_usd": cost,
                                **pricing,
                            },
                        ))

            # Reserved Instance check — on-demand VMs running >7d
            if rule_ri.enabled and power == "PowerState/running":
                out.append(Finding(
                    rule_ri, vm,
                    detail=f"VM '{name}' ({sku}) running on pay-as-you-go.",
                    recommendation="Purchase 1-yr Reserved Instance for ~40% savings.",
                    savings=savings_from_factor(cost, 0.40), score=40,
                    evidence={
                        "power_state": "running",
                        "pricing_model": "on_demand",
                        "vm_size": sku,
                        "monthly_cost_usd": cost,
                    },
                ))

            if rule_spot.enabled:
                tags = vm.get("tags") or {}
                env  = tags.get("environment", tags.get("env", "")).lower()
                if any(w in env for w in rule_spot.spot_eligible_workloads):
                    out.append(Finding(
                        rule_spot, vm,
                        detail=f"VM '{name}' tagged env='{env}' running on on-demand.",
                        recommendation="Switch to Azure Spot VMs for up to 90% savings on interruptible workloads.",
                        savings=savings_from_factor(cost, 0.85), score=55,
                        evidence={
                            "environment": env,
                            "pricing_model": "on_demand",
                            "vm_size": sku,
                            "monthly_cost_usd": cost,
                        },
                    ))
        return out

    # ─── COMPUTE: Disks & Snapshots ───────────────────────────────────────
    def _check_disks(self, disks: list, costs: dict) -> list[Finding]:
        out = []
        rule_ua  = self.rules["DISK_UNATTACHED"]
        rule_ov  = self.rules["DISK_OVERSIZE"]

        for disk in disks:
            props  = disk.get("properties", {})
            state  = props.get("diskState", "")
            sku_t  = disk.get("sku", {}).get("name", "")
            size_gb = props.get("diskSizeGB", 0)
            monthly_cost = resource_cost(costs, disk.get("id", ""))

            if rule_ua.enabled and state == "Unattached":
                stale_ctx = evaluate_unattached_disk(disk, max_days=14)
                if not stale_ctx.is_stale:
                    continue
                detail = (
                    f"Disk '{disk.get('name')}' ({size_gb} GB, {sku_t}) has been unattached "
                    f"for {stale_ctx.age_days} days."
                )
                if stale_ctx.last_owner_name:
                    detail += f" Last attached to '{stale_ctx.last_owner_name}'."
                out.append(Finding(
                    rule_ua, disk,
                    detail=detail,
                    recommendation="Delete the disk or snapshot it first: az disk delete --ids <id>",
                    savings=monthly_cost, score=88,
                    evidence=augment_disk_evidence({
                        "disk_state": state,
                        "size_gb": size_gb,
                        "sku": sku_t,
                        "monthly_cost_usd": monthly_cost,
                        **staleness_evidence(stale_ctx),
                    }, props, disk_resource=disk),
                ))
            elif rule_ov.enabled and state == "Unattached" and "Premium" in sku_t:
                stale_ctx = evaluate_unattached_disk(disk, max_days=14)
                if not stale_ctx.is_stale:
                    continue
                out.append(Finding(
                    rule_ov, disk,
                    detail=f"Premium disk '{disk.get('name')}' is unattached. Downgrade to Standard SSD.",
                    recommendation="az disk update --sku StandardSSD_LRS --ids <id>",
                    savings=savings_from_factor(monthly_cost, 0.70), score=55,
                    evidence={
                        "disk_state": state,
                        "sku": sku_t,
                        "size_gb": size_gb,
                        "monthly_cost_usd": monthly_cost,
                    },
                ))

        return out

    def _check_snapshots(self, snapshots: list, costs: dict) -> list[Finding]:
        from app.optimizer.resource_engines.compute.snapshot.analysis import (
            snapshot_created_at,
            snapshot_size_gb,
        )
        from app.snapshot_retention import (
            is_stale_snapshot,
            meets_snapshot_savings_gate,
            meets_snapshot_size_gate,
            snapshot_age_days,
            snapshot_threshold_evidence,
        )

        out = []
        rule_snp = self.rules["SNAPSHOT_OLD"]

        for snap in snapshots:
            if not rule_snp.enabled:
                break
            created = snapshot_created_at(snap)
            if not created:
                continue
            if not is_stale_snapshot(snap, retention_days=rule_snp.snapshot_retention_days):
                continue
            if not meets_snapshot_size_gate(snap, min_size_gb=rule_snp.snapshot_min_size_gb):
                continue
            age_days = snapshot_age_days(snap) or 0
            size_gb = snapshot_size_gb(snap)
            monthly_cost = resource_cost(costs, snap.get("id", ""))
            if not meets_snapshot_savings_gate(monthly_cost, min_monthly_savings_usd=0.0):
                continue
            out.append(Finding(
                rule_snp, snap,
                detail=(
                    f"Snapshot '{snap.get('name')}' is {age_days} days old ({size_gb:g} GB) — "
                    f"exceeds the {rule_snp.snapshot_retention_days}-day retention threshold."
                ),
                recommendation=(
                    f"Delete snapshots older than {rule_snp.snapshot_retention_days} days "
                    "if the source disk is healthy."
                ),
                savings=monthly_cost, score=40,
                evidence={
                    "age_days": age_days,
                    "size_gb": size_gb,
                    "time_created": created.isoformat(),
                    "monthly_cost_usd": monthly_cost,
                    **snapshot_threshold_evidence(rule_snp),
                },
            ))
        return out

    # ─── KUBERNETES ───────────────────────────────────────────────────────
    def _check_aks(self, clusters: list, node_pools: dict, node_metrics: dict, costs: dict) -> list[Finding]:
        out = []
        rule_idle   = self.rules["AKS_NODE_IDLE"]
        rule_over   = self.rules["AKS_OVERPROVISIONED"]
        rule_dev    = self.rules["AKS_DEV_RUNNING_NIGHTS"]
        rule_spot   = self.rules["AKS_NO_SPOT"]
        rule_ver    = self.rules["AKS_OLD_VERSION"]
        rule_asc    = self.rules["AKS_NO_AUTOSCALER"]
        rule_split  = self.rules["AKS_SINGLE_NODE_POOL"]
        supported_by_region: dict[tuple[str, str], set[str]] = {}
        node_index = _index_aks_node_metrics(node_metrics, clusters, node_pools)

        for cluster in clusters:
            cid   = cluster.get("id", "")
            cname = cluster.get("name", "")
            props = cluster.get("properties", {})
            tags  = cluster.get("tags") or {}
            env   = tags.get("environment", tags.get("env", "prod")).lower()
            nap_enabled = is_node_auto_provisioning_enabled(props)

            # k8s version check — supported versions from Azure ARM per region
            k8s_ver = props.get("kubernetesVersion", "")
            minor = normalize_k8s_minor(k8s_ver)
            sub_id = _extract_sub(cid)
            loc = (cluster.get("location") or "").strip()
            region_key = (sub_id, loc.lower())
            if region_key not in supported_by_region and sub_id and loc:
                supported_by_region[region_key] = supported_minors_for_location(sub_id, loc)
            supported = supported_by_region.get(region_key, set())
            version_supported = is_minor_version_supported(k8s_ver, supported)
            if rule_ver.enabled and minor and version_supported is False:
                out.append(Finding(
                    rule_ver, cluster,
                    detail=(
                        f"Cluster '{cname}' is on k8s {k8s_ver}, which is not supported in region '{loc}'. "
                        f"Supported: {', '.join(sorted(supported))}."
                    ),
                    recommendation="Upgrade the cluster to a supported Kubernetes version for this region.",
                    savings=0, score=50,
                    evidence={
                        "kubernetes_version": k8s_ver,
                        "kubernetes_minor": minor,
                        "location": loc,
                        "supported_versions": sorted(supported),
                        "version_source": "azure_arm",
                    },
                ))

            pools = node_pools.get(cid, node_pools.get(cid.lower(), []))
            if not pools:
                pools = props.get("agentPoolProfiles", [])

            cluster_cost = resource_cost(costs, cid)
            total_nodes = sum(
                int(p.get("count") or p.get("nodeCount") or p.get("vmCount") or 0)
                for p in pools
            )

            # Single pool check
            if rule_split.enabled and len(pools) == 1:
                out.append(Finding(
                    rule_split, cluster,
                    detail=f"Cluster '{cname}' has only 1 node pool. All workloads share the same nodes.",
                    recommendation="Add a separate user node pool for workloads; keep system pool lean (Standard_D2s_v3 x2).",
                    savings=0, score=30,
                    evidence={"pool_count": len(pools)},
                ))

            for pool in pools:
                pname  = pool.get("name", "")
                mode   = pool.get("mode", "User").lower()
                count  = pool.get("count") or pool.get("nodeCount") or pool.get("vmCount") or 0
                vm_sku = pool.get("vmSize", "")
                asc    = pool.get("enableAutoScaling") or pool.get("autoscaleEnabled")

                pool_cost = aks_pool_cost_share(cluster_cost, count, total_nodes)
                node_monthly = pool_cost / count if count > 0 else 0.0

                # Autoscaler disabled
                if rule_asc.enabled and not nap_enabled and not asc and count > rule_asc.node_count_min:
                    out.append(Finding(
                        rule_asc, cluster,
                        detail=f"Pool '{pname}' on cluster '{cname}' has {count} nodes, autoscaler OFF.",
                        recommendation=f"Enable cluster autoscaler: az aks nodepool update --enable-cluster-autoscaler --min-count 1 --max-count {count}",
                        savings=savings_from_factor(pool_cost, 0.30), score=75,
                        evidence={
                            "pool_name": pname,
                            "node_count": count,
                            "autoscaler_enabled": bool(asc),
                            "node_count_min": rule_asc.node_count_min,
                            "monthly_cost_usd": pool_cost,
                        },
                    ))

                # Spot opportunity for non-system pools
                if rule_spot.enabled and mode != "system":
                    spot_mode = pool.get("scaleSetPriority", "").lower()
                    if spot_mode != "spot":
                        out.append(Finding(
                            rule_spot, cluster,
                            detail=f"Pool '{pname}' ({vm_sku} x{count}) on cluster '{cname}' using on-demand nodes.",
                            recommendation="Use Spot node pool for interruptible workloads. Add --priority Spot --eviction-policy Delete.",
                            savings=savings_from_factor(pool_cost, 0.80), score=65,
                            evidence={
                                "pool_name": pname,
                                "scale_set_priority": spot_mode or "regular",
                                "node_count": count,
                                "vm_size": vm_sku,
                                "monthly_cost_usd": pool_cost,
                            },
                        ))

                # Dev cluster running 24/7
                if rule_dev.enabled and env in ("dev", "development", "staging", "stage", "test"):
                    out.append(Finding(
                        rule_dev, cluster,
                        detail=f"Non-prod cluster '{cname}' (env={env}) appears to run 24/7.",
                        recommendation=f"Enable AKS start/stop schedule for {rule_dev.cluster_dev_hours}. Saves ~14 hrs/day.",
                        savings=savings_from_factor(pool_cost, 14 / 24), score=70,
                        evidence={
                            "environment": env,
                            "pool_name": pname,
                            "monthly_cost_usd": pool_cost,
                        },
                    ))

                # Node metrics — idle nodes
                pool_node_prefix = f"{cname}-{pname}".lower()
                idle_nodes = 0
                for _node_id, nm in node_index.get(pool_node_prefix, []):
                    ncpu = _avg_metric(nm, "cpuUsage") or _avg_metric(nm, "Percentage CPU") or 0
                    nmem = _avg_metric(nm, "memUsage") or _avg_metric(nm, "Memory Working Set Bytes") or 0
                    if rule_idle.enabled and ncpu < rule_idle.node_cpu_idle and nmem < rule_idle.node_mem_idle:
                        idle_nodes += 1

                if rule_over.enabled and not nap_enabled and idle_nodes > 0:
                    out.append(Finding(
                        rule_over, cluster,
                        detail=f"Pool '{pname}': {idle_nodes}/{count} nodes are idle (CPU<{rule_idle.node_cpu_idle}%, Mem<{rule_idle.node_mem_idle}%).",
                        recommendation=f"Reduce pool min-count by {idle_nodes}. Enable autoscaler to manage this automatically.",
                        savings=round(idle_nodes * node_monthly, 2) if node_monthly > 0 else 0, score=80,
                        evidence={
                            "idle_nodes": idle_nodes,
                            "node_count": count,
                            "pool_name": pname,
                            "monthly_cost_usd": pool_cost,
                        },
                    ))
        return out

    # ─── STORAGE ──────────────────────────────────────────────────────────
    def _check_storage(self, accounts: list) -> list[Finding]:
        out = []
        rule_hot  = self.rules["STORAGE_HOT_UNUSED"]
        rule_lc   = self.rules["STORAGE_NO_LIFECYCLE"]

        for acct in accounts:
            props = acct.get("properties", {})
            kind  = acct.get("kind", "")
            sku   = acct.get("sku", {}).get("name", "")
            tier  = props.get("accessTier", "")

            if rule_hot.enabled and tier == "Hot":
                out.append(Finding(
                    rule_hot, acct,
                    detail=f"Storage '{acct.get('name')}' is on Hot tier. Verify if data is actively accessed.",
                    recommendation="Set lifecycle policy to move blobs to Cool after 30 days, Archive after 90 days.",
                    savings=0, score=35,
                    evidence={"access_tier": tier, "sku": sku},
                ))

            if rule_lc.enabled:
                out.append(Finding(
                    rule_lc, acct,
                    detail=f"Storage '{acct.get('name')}' has no verified lifecycle management policy.",
                    recommendation="Add blob lifecycle policy via: az storage account management-policy create",
                    savings=0, score=25,
                    evidence={"has_lifecycle_policy": False, "kind": kind},
                ))
        return out

    # ─── NETWORKING ───────────────────────────────────────────────────────
    def _check_network(self, public_ips: list, load_balancers: list, app_gateways: list,
                       network_interfaces: list | None = None, nat_gateways: list | None = None,
                       costs: dict | None = None) -> list[Finding]:
        out = []
        costs = costs or {}
        rule_ip  = self.rules["IP_UNASSOCIATED"]
        rule_lb  = self.rules["LB_NO_BACKEND"]
        rule_agw = self.rules["APPGW_UNUSED"]
        rule_nic = self.rules.get("NIC_UNATTACHED")
        rule_nat = self.rules.get("NAT_GATEWAY_IDLE")

        for ip in public_ips:
            if not rule_ip.enabled:
                break
            props = ip.get("properties", {})
            assoc = props.get("ipConfiguration") or props.get("natGateway")
            alloc = props.get("publicIPAllocationMethod", "")
            if not assoc and alloc == "Static":
                ip_cost = resource_cost(costs, ip.get("id", ""))
                out.append(Finding(
                    rule_ip, ip,
                    detail=f"Static Public IP '{ip.get('name')}' is not associated with any resource.",
                    recommendation="Delete: az network public-ip delete --ids <id>",
                    savings=ip_cost, score=70,
                    evidence={
                        "allocation": "unassociated",
                        "public_ip_allocation_method": alloc,
                        "monthly_cost_usd": ip_cost,
                    },
                ))

        for lb in load_balancers:
            if not rule_lb.enabled:
                break
            props    = lb.get("properties", {})
            backends = props.get("backendAddressPools", [])
            # Check if all backend pools are empty
            all_empty = all(
                not pool.get("properties", {}).get("backendIPConfigurations")
                and not pool.get("properties", {}).get("loadBalancerBackendAddresses")
                for pool in backends
            )
            sku_name = lb.get("sku", {}).get("name", "Basic")
            lb_cost  = resource_cost(costs, lb.get("id", ""))
            if all_empty and backends:
                out.append(Finding(
                    rule_lb, lb,
                    detail=f"Load Balancer '{lb.get('name')}' ({sku_name}) has no backend instances.",
                    recommendation="Delete idle LB or attach it to active backend resources.",
                    savings=lb_cost, score=82,
                    evidence={
                        "backend_pool_count": len(backends),
                        "all_backends_empty": True,
                        "sku": lb.get("sku") or {},
                        "monthly_cost_usd": lb_cost,
                    },
                ))

        for agw in app_gateways:
            if not rule_agw.enabled:
                break
            props     = agw.get("properties", {})
            listener_count = http_listener_count(props)
            sku_tier  = agw.get("sku", {}).get("tier", "Standard_v2")
            agw_cost  = resource_cost(costs, agw.get("id", ""))
            if listener_count == 0:
                out.append(Finding(
                    rule_agw, agw,
                    detail=f"Application Gateway '{agw.get('name')}' has no HTTP listeners configured.",
                    recommendation="Delete or reconfigure. Idle Application Gateway still incurs billed cost.",
                    savings=agw_cost, score=85,
                    evidence={
                        "determination": "idle_no_listeners",
                        "data_source": "synced_inventory",
                        "http_listener_count": listener_count,
                        "sku": agw.get("sku") or {},
                        "sku_tier": sku_tier,
                        "monthly_cost_usd": agw_cost,
                    },
                ))

        for nic in network_interfaces or []:
            if not rule_nic or not rule_nic.enabled:
                break
            props = nic.get("properties", {})
            if not props.get("virtualMachine") and not props.get("privateEndpoint"):
                out.append(Finding(
                    rule_nic, nic,
                    detail=f"NIC '{nic.get('name')}' is not attached to a VM or private endpoint.",
                    recommendation="Delete orphaned NIC after confirming no DNS or firewall dependency.",
                    savings=0, score=55,
                    evidence={"has_vm": False, "has_private_endpoint": False},
                ))

        for nat in nat_gateways or []:
            if not rule_nat or not rule_nat.enabled:
                break
            props = nat.get("properties", {})
            subnets = props.get("subnets") or []
            if not subnets:
                nat_cost = resource_cost(costs, nat.get("id", ""))
                out.append(Finding(
                    rule_nat, nat,
                    detail=f"NAT Gateway '{nat.get('name')}' has no subnet associations.",
                    recommendation="Delete idle NAT Gateway or attach required subnets.",
                    savings=nat_cost, score=78,
                    evidence={
                        "subnet_count": 0,
                        "monthly_cost_usd": nat_cost,
                    },
                ))
        return out

    # ─── APP SERVICES ─────────────────────────────────────────────────────
    def _check_app_services(self, apps: list, plans: list, costs: dict) -> list[Finding]:
        out = []
        rule_empty = self.rules.get("ASP_EMPTY")
        rule_over  = self.rules.get("ASP_OVERPROVISIONED")
        if not rule_empty and not rule_over:
            return out

        apps_by_plan: dict[str, int] = {}
        for app in apps:
            props = app.get("properties", {})
            plan_id = (props.get("serverFarmId") or "").lower()
            if plan_id:
                apps_by_plan[plan_id] = apps_by_plan.get(plan_id, 0) + 1

        for plan in plans:
            pid = (plan.get("id") or "").lower()
            pname = plan.get("name", "")
            sku = plan.get("sku", {}) or {}
            tier = (sku.get("tier") or "").lower()
            app_count = apps_by_plan.get(pid, 0)

            if rule_empty and rule_empty.enabled and app_count == 0:
                plan_cost = resource_cost(costs, plan.get("id", ""))
                out.append(Finding(
                    rule_empty, plan,
                    detail=f"App Service Plan '{pname}' ({tier}) hosts no apps.",
                    recommendation="Delete unused plan or migrate apps from other plans to consolidate.",
                    savings=plan_cost, score=72,
                    evidence={"app_count": app_count, "tier": tier, "monthly_cost_usd": plan_cost},
                ))
            elif rule_over and rule_over.enabled and tier in ("premium", "premiumv2", "premiumv3", "isolated") and app_count < 2:
                plan_cost = resource_cost(costs, plan.get("id", ""))
                out.append(Finding(
                    rule_over, plan,
                    detail=f"Plan '{pname}' is {tier} tier with only {app_count} app(s).",
                    recommendation="Downgrade to Standard tier or consolidate more apps onto this plan.",
                    savings=savings_from_factor(plan_cost, 0.35), score=58,
                    evidence={"app_count": app_count, "tier": tier, "monthly_cost_usd": plan_cost},
                ))
        return out

    # ─── REDIS ────────────────────────────────────────────────────────────
    def _check_redis(self, caches: list, costs: dict) -> list[Finding]:
        out = []
        rule_failed = self.rules.get("REDIS_FAILED")
        rule_over   = self.rules.get("REDIS_OVERSIZED")
        for cache in caches:
            props = cache.get("properties", {}) or {}
            state = (props.get("provisioningState") or "").lower()
            sku = cache.get("sku", {}) or {}
            tier = (sku.get("family") or sku.get("name") or "").lower()
            capacity = int(sku.get("capacity") or 0)
            if rule_failed and rule_failed.enabled and state == "failed":
                out.append(Finding(
                    rule_failed, cache,
                    detail=f"Redis '{cache.get('name')}' is in Failed state.",
                    recommendation="Delete failed cache and recreate, or open Azure support ticket.",
                    savings=0, score=90,
                    evidence={"provisioning_state": state},
                ))
            if rule_over and rule_over.enabled and "premium" in tier and capacity >= 1:
                monthly = resource_cost(costs, cache.get("id", ""))
                out.append(Finding(
                    rule_over, cache,
                    detail=f"Redis '{cache.get('name')}' uses Premium capacity {capacity}.",
                    recommendation="Validate memory usage; consider Standard tier or lower capacity for dev/test.",
                    savings=savings_from_factor(monthly, 0.35), score=50,
                    evidence={"tier": tier, "capacity": capacity, "monthly_cost_usd": monthly},
                ))
        return out

    # ─── DATABASE ─────────────────────────────────────────────────────────
    def _check_databases(self, sql_servers: list, sql_dbs: list, cosmosdb: list) -> list[Finding]:
        out = []
        rule_sql  = self.rules["SQL_IDLE"]
        rule_svls = self.rules["SQL_NO_SERVERLESS"]
        rule_csm  = self.rules["COSMOS_PROVISIONED"]

        for db in sql_dbs:
            props    = db.get("properties", {})
            sku_name = db.get("sku", {}).get("name", "")
            tier     = db.get("sku", {}).get("tier", "")
            status   = props.get("status", "")
            # Serverless check
            if rule_svls.enabled and tier in ("GeneralPurpose", "BusinessCritical") and "Serverless" not in sku_name:
                out.append(Finding(
                    rule_svls, db,
                    detail=f"SQL DB '{db.get('name')}' on provisioned {tier}/{sku_name}.",
                    recommendation="Switch to Serverless tier for auto-pause when idle (dev/test DBs).",
                    savings=0, score=40,
                    evidence={"tier": tier, "sku": sku_name},
                ))

        for cosmos in cosmosdb:
            if not rule_csm.enabled:
                break
            props = cosmos.get("properties", {})
            cap   = props.get("capabilities", [])
            is_serverless = any(c.get("name") == "EnableServerless" for c in cap)
            if not is_serverless:
                out.append(Finding(
                    rule_csm, cosmos,
                    detail=f"Cosmos DB '{cosmos.get('name')}' is on provisioned throughput.",
                    recommendation="Enable autoscale or switch to serverless mode for variable-traffic workloads.",
                    savings=0, score=35,
                    evidence={"serverless_enabled": is_serverless},
                ))
        return out

    # ─── SECURITY ─────────────────────────────────────────────────────────
    def _check_security(self, keyvaults: list) -> list[Finding]:
        from app.keyvault_utilization import (
            kv_inventory_evidence,
            protection_baseline_gap,
            purge_protection_enabled,
            soft_delete_enabled,
        )

        out = []
        rule = self.rules["KEYVAULT_SOFT_DELETE_OFF"]
        if not rule.enabled:
            return out
        for kv in keyvaults:
            if not protection_baseline_gap(kv):
                continue
            props = kv.get("properties", {})
            soft_delete = soft_delete_enabled(kv)
            purge_protection = purge_protection_enabled(kv)
            out.append(Finding(
                rule, kv,
                detail=f"Key Vault '{kv.get('name')}' missing soft-delete or purge protection.",
                recommendation="az keyvault update --enable-soft-delete true --enable-purge-protection true --name <name>",
                savings=0, score=70,
                evidence={
                    "enableSoftDelete": props.get("enableSoftDelete") if soft_delete is None else soft_delete,
                    "enablePurgeProtection": purge_protection,
                    **kv_inventory_evidence(kv),
                },
            ))
        return out

    # ─── COST ─────────────────────────────────────────────────────────────
    def _check_cost(self, budgets: list, spend_usd: float) -> list[Finding]:
        out = []
        rule_warn = self.rules["BUDGET_WARNING"]
        rule_crit = self.rules["BUDGET_CRITICAL"]

        for budget in budgets:
            props  = budget.get("properties", {})
            amount = props.get("amount", 0)
            current = props.get("currentSpend", {}).get("amount", spend_usd)
            if amount <= 0:
                continue
            pct = (current / amount) * 100
            if rule_crit.enabled and pct >= rule_crit.budget_crit_pct:
                out.append(Finding(
                    rule_crit, budget,
                    detail=f"Budget '{budget.get('name')}': {pct:.1f}% used (${current:,.0f} of ${amount:,.0f}).",
                    recommendation="Immediate cost review. Apply resource tagging and cost allocation policies.",
                    savings=0, score=95,
                    evidence={
                        "used_pct": round(pct, 2),
                        "budget_crit_pct": rule_crit.budget_crit_pct,
                        "amount": amount,
                        "current_spend_usd": current,
                    },
                ))
            elif rule_warn.enabled and pct >= rule_warn.budget_warn_pct:
                out.append(Finding(
                    rule_warn, budget,
                    detail=f"Budget '{budget.get('name')}': {pct:.1f}% used (${current:,.0f} of ${amount:,.0f}).",
                    recommendation="Review top spending resources and apply reserved instances or rightsizing.",
                    savings=0, score=75,
                    evidence={
                        "used_pct": round(pct, 2),
                        "budget_warn_pct": rule_warn.budget_warn_pct,
                        "amount": amount,
                        "current_spend_usd": current,
                    },
                ))
        return out


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _subscription_id_from(*resource_lists: list | None) -> str:
    for bucket in resource_lists:
        for item in bucket or []:
            sub = _extract_sub(item.get("id", "") if isinstance(item, dict) else "")
            if sub:
                return sub
    return ""


def _avg_metric(metrics: dict | None, name: str) -> float | None:
    if not metrics:
        return None
    # Azure Monitor response structure
    value = metrics.get("value", [])
    for m in value:
        if m.get("name", {}).get("value") == name:
            ts = m.get("timeseries", [])
            if ts:
                data = ts[0].get("data", [])
                vals = [d.get("average") for d in data if d.get("average") is not None]
                return sum(vals) / len(vals) if vals else None
    return None


def _severity_rank(s: str) -> int:
    return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}.get(s, 5)


def _build_summary(findings: list[Finding], total_savings: float) -> dict:
    by_severity  = {}
    by_category  = {}
    for f in findings:
        by_severity[f.severity]  = by_severity.get(f.severity, 0)  + 1
        by_category[f.category]  = by_category.get(f.category, 0)  + 1
    return {
        "total_findings": len(findings),
        "total_estimated_monthly_savings_usd": round(total_savings, 2),
        "by_severity":  by_severity,
        "by_category":  by_category,
        "top_savings": [
            {"resource": f.resource_name, "rule": f.rule_name,
             "savings": f.estimated_savings_usd, "severity": f.severity}
            for f in sorted(findings, key=lambda x: x.estimated_savings_usd, reverse=True)[:10]
        ],
    }

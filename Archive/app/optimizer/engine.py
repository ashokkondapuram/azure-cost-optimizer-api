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
from app.optimizer.rules import DEFAULT_RULES, Rule, Severity, Category

log = structlog.get_logger()

# Latest supported AKS k8s minor versions (update quarterly)
SUPPORTED_K8S = {"1.29", "1.30", "1.31", "1.32"}


# ─── Finding dataclass ────────────────────────────────────────────────────────
class Finding:
    __slots__ = (
        "rule_id", "rule_name", "category", "severity",
        "resource_id", "resource_name", "resource_type",
        "subscription_id", "resource_group", "location",
        "detail", "recommendation", "estimated_savings_usd",
        "waste_score", "tags", "detected_at",
    )

    def __init__(self, rule: Rule, resource: dict, detail: str,
                 recommendation: str, savings: float = 0.0, score: int = 50):
        self.rule_id   = rule.id
        self.rule_name = rule.name
        self.category  = rule.category.value
        self.severity  = rule.severity.value
        self.resource_id   = resource.get("id", "")
        self.resource_name = resource.get("name", "")
        self.resource_type = resource.get("type", "")
        self.subscription_id = _extract_sub(resource.get("id", ""))
        self.resource_group  = _extract_rg(resource.get("id", ""))
        self.location        = resource.get("location", "")
        self.detail          = detail
        self.recommendation  = recommendation
        self.estimated_savings_usd = round(savings, 2)
        self.waste_score     = score   # 0=fine, 100=critical waste
        self.tags            = resource.get("tags") or {}
        self.detected_at     = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}


def _extract_sub(resource_id: str) -> str:
    parts = resource_id.lower().split("/")
    try:
        return parts[parts.index("subscriptions") + 1]
    except (ValueError, IndexError):
        return ""


def _extract_rg(resource_id: str) -> str:
    parts = resource_id.lower().split("/")
    try:
        return parts[parts.index("resourcegroups") + 1]
    except (ValueError, IndexError):
        return ""


# ─── Engine ───────────────────────────────────────────────────────────────────
class OptimizationEngine:
    """Main engine. Instantiate once, call .analyze() per subscription/scope."""

    def __init__(self, rule_overrides: dict[str, dict] | None = None):
        """
        rule_overrides: per-rule threshold overrides, e.g.:
          { "VM_IDLE": {"cpu_idle_pct": 3.0, "enabled": False} }
        """
        self.rules: dict[str, Rule] = {}
        for rid, rule in DEFAULT_RULES.items():
            import copy
            r = copy.deepcopy(rule)
            if rule_overrides and rid in rule_overrides:
                for k, v in rule_overrides[rid].items():
                    if hasattr(r, k):
                        setattr(r, k, v)
            self.rules[rid] = r

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
        sql_servers:   list[dict] | None = None,
        sql_databases: list[dict] | None = None,
        cosmosdb:      list[dict] | None = None,
        keyvaults:     list[dict] | None = None,
        vm_metrics:    dict[str, dict] | None = None,  # resource_id -> metrics
        node_metrics:  dict[str, dict] | None = None,  # node_name -> metrics
        cost_by_resource: dict | None = None,           # resourceId -> cost_usd
        budgets:       list[dict] | None = None,
        subscription_spend_usd: float = 0.0,
        max_workers:   int = 16,
    ) -> dict:
        """Run all rule checks in parallel. Returns structured report."""
        log.info("engine.analyze.start",
                 vms=len(vms or []), aks=len(aks_clusters or []),
                 disks=len(disks or []), storage=len(storage or []))

        findings: list[Finding] = []

        tasks = [
            (self._check_vms,        (vms or [], vm_metrics or {}, cost_by_resource or {})),
            (self._check_disks,      (disks or [], snapshots or [])),
            (self._check_aks,        (aks_clusters or [], aks_node_pools or {}, node_metrics or {})),
            (self._check_storage,    (storage or [],)),
            (self._check_network,    (public_ips or [], load_balancers or [], app_gateways or [])),
            (self._check_databases,  (sql_servers or [], sql_databases or [], cosmosdb or [])),
            (self._check_security,   (keyvaults or [],)),
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
            if not rule_idle.enabled and not rule_over.enabled:
                continue
            rid  = vm.get("id", "")
            name = vm.get("name", "")
            props = vm.get("properties", {})
            hw    = props.get("hardwareProfile", {})
            sku   = hw.get("vmSize", "")
            cost  = costs.get(rid.lower(), 0.0)

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
                ))
                continue

            # CPU metrics-based checks
            m = metrics.get(rid.lower()) or metrics.get(rid)
            avg_cpu = _avg_metric(m, "Percentage CPU") if m else None
            avg_mem = _avg_metric(m, "Available Memory Bytes") if m else None

            if avg_cpu is not None:
                if rule_idle.enabled and avg_cpu < rule_idle.cpu_idle_pct:
                    out.append(Finding(
                        rule_idle, vm,
                        detail=f"VM '{name}' avg CPU {avg_cpu:.1f}% over 7d (threshold {rule_idle.cpu_idle_pct}%). SKU: {sku}.",
                        recommendation="Deallocate if unused, or downsize to B-series burstable.",
                        savings=cost * 0.90, score=85,
                    ))
                elif rule_over.enabled and avg_cpu < rule_over.cpu_oversize_pct:
                    # Recommend smaller SKU
                    smaller = _suggest_smaller_sku(sku)
                    out.append(Finding(
                        rule_over, vm,
                        detail=f"VM '{name}' avg CPU {avg_cpu:.1f}% (threshold {rule_over.cpu_oversize_pct}%). SKU: {sku}.",
                        recommendation=f"Downsize from {sku} to {smaller}. Estimated 30-50% cost reduction.",
                        savings=cost * 0.35, score=60,
                    ))

            # Reserved Instance check — on-demand VMs running >7d
            if rule_ri.enabled and power == "PowerState/running":
                out.append(Finding(
                    rule_ri, vm,
                    detail=f"VM '{name}' ({sku}) running on pay-as-you-go.",
                    recommendation="Purchase 1-yr Reserved Instance for ~40% savings.",
                    savings=cost * 0.40, score=40,
                ))

            # Spot opportunity for dev/test
            if rule_spot.enabled:
                tags = vm.get("tags") or {}
                env  = tags.get("environment", tags.get("env", "")).lower()
                if any(w in env for w in rule_spot.spot_eligible_workloads):
                    out.append(Finding(
                        rule_spot, vm,
                        detail=f"VM '{name}' tagged env='{env}' running on on-demand.",
                        recommendation="Switch to Azure Spot VMs for up to 90% savings on interruptible workloads.",
                        savings=cost * 0.85, score=55,
                    ))
        return out

    # ─── COMPUTE: Disks & Snapshots ───────────────────────────────────────
    def _check_disks(self, disks: list, snapshots: list) -> list[Finding]:
        out = []
        rule_ua  = self.rules["DISK_UNATTACHED"]
        rule_snp = self.rules["SNAPSHOT_OLD"]
        rule_ov  = self.rules["DISK_OVERSIZE"]
        now      = datetime.now(timezone.utc)

        for disk in disks:
            props  = disk.get("properties", {})
            state  = props.get("diskState", "")
            sku_t  = disk.get("sku", {}).get("name", "")
            size_gb = props.get("diskSizeGB", 0)
            # Estimate cost: Premium_LRS ~$0.17/GB, Standard_LRS ~$0.05/GB
            cost_per_gb = 0.17 if "Premium" in sku_t else 0.05
            monthly_cost = size_gb * cost_per_gb

            if rule_ua.enabled and state == "Unattached":
                out.append(Finding(
                    rule_ua, disk,
                    detail=f"Disk '{disk.get('name')}' ({size_gb} GB, {sku_t}) is unattached.",
                    recommendation="Delete the disk or snapshot it first: az disk delete --ids <id>",
                    savings=monthly_cost, score=88,
                ))
            elif rule_ov.enabled and state == "Unattached" and "Premium" in sku_t:
                out.append(Finding(
                    rule_ov, disk,
                    detail=f"Premium disk '{disk.get('name')}' is unattached. Downgrade to Standard SSD.",
                    recommendation="az disk update --sku StandardSSD_LRS --ids <id>",
                    savings=monthly_cost * 0.70, score=55,
                ))

        for snap in snapshots:
            if not rule_snp.enabled:
                break
            props      = snap.get("properties", {})
            time_str   = props.get("timeCreated", "")
            size_gb    = props.get("diskSizeGB", 0)
            monthly_cost = size_gb * 0.05
            try:
                created = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                age_days = (now - created).days
                if age_days > 90:
                    out.append(Finding(
                        rule_snp, snap,
                        detail=f"Snapshot '{snap.get('name')}' is {age_days} days old ({size_gb} GB).",
                        recommendation="Delete snapshots older than 90 days if the source disk is healthy.",
                        savings=monthly_cost, score=40,
                    ))
            except Exception:
                pass
        return out

    # ─── KUBERNETES ───────────────────────────────────────────────────────
    def _check_aks(self, clusters: list, node_pools: dict, node_metrics: dict) -> list[Finding]:
        out = []
        rule_idle   = self.rules["AKS_NODE_IDLE"]
        rule_over   = self.rules["AKS_OVERPROVISIONED"]
        rule_dev    = self.rules["AKS_DEV_RUNNING_NIGHTS"]
        rule_spot   = self.rules["AKS_NO_SPOT"]
        rule_ver    = self.rules["AKS_OLD_VERSION"]
        rule_asc    = self.rules["AKS_NO_AUTOSCALER"]
        rule_split  = self.rules["AKS_SINGLE_NODE_POOL"]

        for cluster in clusters:
            cid   = cluster.get("id", "")
            cname = cluster.get("name", "")
            props = cluster.get("properties", {})
            tags  = cluster.get("tags") or {}
            env   = tags.get("environment", tags.get("env", "prod")).lower()

            # k8s version check
            k8s_ver = props.get("kubernetesVersion", "")
            minor   = ".".join(k8s_ver.split(".")[:2]) if k8s_ver else ""
            if rule_ver.enabled and minor and minor not in SUPPORTED_K8S:
                out.append(Finding(
                    rule_ver, cluster,
                    detail=f"Cluster '{cname}' is on k8s {k8s_ver}. Supported: {', '.join(sorted(SUPPORTED_K8S))}.",
                    recommendation="az aks upgrade --name {cname} --kubernetes-version <latest>",
                    savings=0, score=50,
                ))

            pools = node_pools.get(cid, node_pools.get(cid.lower(), []))
            if not pools:
                pools = props.get("agentPoolProfiles", [])

            # Single pool check
            if rule_split.enabled and len(pools) == 1:
                out.append(Finding(
                    rule_split, cluster,
                    detail=f"Cluster '{cname}' has only 1 node pool. All workloads share the same nodes.",
                    recommendation="Add a separate user node pool for workloads; keep system pool lean (Standard_D2s_v3 x2).",
                    savings=0, score=30,
                ))

            for pool in pools:
                pname  = pool.get("name", "")
                mode   = pool.get("mode", "User").lower()
                count  = pool.get("count") or pool.get("nodeCount") or pool.get("vmCount") or 0
                vm_sku = pool.get("vmSize", "")
                asc    = pool.get("enableAutoScaling") or pool.get("autoscaleEnabled")

                # Estimate node cost ($0.10/core/hr * 730hr * vCPU_guess)
                vcpu_guess = _sku_vcpu_guess(vm_sku)
                node_monthly = vcpu_guess * 0.10 * 730
                pool_cost    = count * node_monthly

                # Autoscaler disabled
                if rule_asc.enabled and not asc and count > rule_asc.node_count_min:
                    out.append(Finding(
                        rule_asc, cluster,
                        detail=f"Pool '{pname}' on cluster '{cname}' has {count} nodes, autoscaler OFF.",
                        recommendation=f"Enable cluster autoscaler: az aks nodepool update --enable-cluster-autoscaler --min-count 1 --max-count {count}",
                        savings=pool_cost * 0.30, score=75,
                    ))

                # Spot opportunity for non-system pools
                if rule_spot.enabled and mode != "system":
                    spot_mode = pool.get("scaleSetPriority", "").lower()
                    if spot_mode != "spot":
                        out.append(Finding(
                            rule_spot, cluster,
                            detail=f"Pool '{pname}' ({vm_sku} x{count}) on cluster '{cname}' using on-demand nodes.",
                            recommendation="Use Spot node pool for interruptible workloads. Add --priority Spot --eviction-policy Delete.",
                            savings=pool_cost * 0.80, score=65,
                        ))

                # Dev cluster running 24/7
                if rule_dev.enabled and env in ("dev", "development", "staging", "stage", "test"):
                    out.append(Finding(
                        rule_dev, cluster,
                        detail=f"Non-prod cluster '{cname}' (env={env}) appears to run 24/7.",
                        recommendation=f"Enable AKS start/stop schedule for {rule_dev.cluster_dev_hours}. Saves ~14 hrs/day.",
                        savings=pool_cost * (14 / 24), score=70,
                    ))

                # Node metrics — idle nodes
                pool_node_prefix = f"{cname}-{pname}"
                idle_nodes = 0
                for node_id, nm in node_metrics.items():
                    if pool_node_prefix.lower() in node_id.lower():
                        ncpu = _avg_metric(nm, "cpuUsage") or _avg_metric(nm, "Percentage CPU") or 0
                        nmem = _avg_metric(nm, "memUsage") or _avg_metric(nm, "Memory Working Set Bytes") or 0
                        if rule_idle.enabled and ncpu < rule_idle.node_cpu_idle and nmem < rule_idle.node_mem_idle:
                            idle_nodes += 1

                if rule_over.enabled and idle_nodes > 0:
                    out.append(Finding(
                        rule_over, cluster,
                        detail=f"Pool '{pname}': {idle_nodes}/{count} nodes are idle (CPU<{rule_idle.node_cpu_idle}%, Mem<{rule_idle.node_mem_idle}%).",
                        recommendation=f"Reduce pool min-count by {idle_nodes}. Enable autoscaler to manage this automatically.",
                        savings=idle_nodes * node_monthly, score=80,
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
                ))

            if rule_lc.enabled:
                lc = props.get("networkAcls") or {}  # lifecycle is a management policy, flagging for review
                out.append(Finding(
                    rule_lc, acct,
                    detail=f"Storage '{acct.get('name')}' has no verified lifecycle management policy.",
                    recommendation="Add blob lifecycle policy via: az storage account management-policy create",
                    savings=0, score=25,
                ))
        return out

    # ─── NETWORKING ───────────────────────────────────────────────────────
    def _check_network(self, public_ips: list, load_balancers: list, app_gateways: list) -> list[Finding]:
        out = []
        rule_ip  = self.rules["IP_UNASSOCIATED"]
        rule_lb  = self.rules["LB_NO_BACKEND"]
        rule_agw = self.rules["APPGW_UNUSED"]

        for ip in public_ips:
            if not rule_ip.enabled:
                break
            props = ip.get("properties", {})
            assoc = props.get("ipConfiguration") or props.get("natGateway")
            alloc = props.get("publicIPAllocationMethod", "")
            if not assoc and alloc == "Static":
                out.append(Finding(
                    rule_ip, ip,
                    detail=f"Static Public IP '{ip.get('name')}' is not associated with any resource.",
                    recommendation="Delete: az network public-ip delete --ids <id>",
                    savings=3.65, score=80,  # Static IP ~$3.65/mo
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
            lb_cost  = 18.0 if sku_name == "Standard" else 0.0
            if all_empty and backends:
                out.append(Finding(
                    rule_lb, lb,
                    detail=f"Load Balancer '{lb.get('name')}' ({sku_name}) has no backend instances.",
                    recommendation="Delete idle LB or attach it to active backend resources.",
                    savings=lb_cost, score=82,
                ))

        for agw in app_gateways:
            if not rule_agw.enabled:
                break
            props     = agw.get("properties", {})
            listeners = props.get("httpListeners", [])
            sku_tier  = agw.get("sku", {}).get("tier", "Standard_v2")
            agw_cost  = 125.0 if "WAF" in sku_tier else 125.0
            if not listeners:
                out.append(Finding(
                    rule_agw, agw,
                    detail=f"Application Gateway '{agw.get('name')}' has no HTTP listeners configured.",
                    recommendation="Delete or reconfigure. WAF v2/Standard v2 costs ~$125+/mo idle.",
                    savings=agw_cost, score=85,
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
                ))
        return out

    # ─── SECURITY ─────────────────────────────────────────────────────────
    def _check_security(self, keyvaults: list) -> list[Finding]:
        out = []
        rule = self.rules["KEYVAULT_SOFT_DELETE_OFF"]
        if not rule.enabled:
            return out
        for kv in keyvaults:
            props = kv.get("properties", {})
            if not props.get("enableSoftDelete") or not props.get("enablePurgeProtection"):
                out.append(Finding(
                    rule, kv,
                    detail=f"Key Vault '{kv.get('name')}' missing soft-delete or purge protection.",
                    recommendation="az keyvault update --enable-soft-delete true --enable-purge-protection true --name <name>",
                    savings=0, score=70,
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
                ))
            elif rule_warn.enabled and pct >= rule_warn.budget_warn_pct:
                out.append(Finding(
                    rule_warn, budget,
                    detail=f"Budget '{budget.get('name')}': {pct:.1f}% used (${current:,.0f} of ${amount:,.0f}).",
                    recommendation="Review top spending resources and apply reserved instances or rightsizing.",
                    savings=0, score=75,
                ))
        return out


# ─── Helpers ──────────────────────────────────────────────────────────────────
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


def _suggest_smaller_sku(sku: str) -> str:
    """Simple SKU downsize heuristic."""
    sku = sku.upper()
    mappings = {
        "STANDARD_D64S_V5": "Standard_D32s_v5",
        "STANDARD_D32S_V5": "Standard_D16s_v5",
        "STANDARD_D16S_V5": "Standard_D8s_v5",
        "STANDARD_D8S_V5":  "Standard_D4s_v5",
        "STANDARD_D4S_V5":  "Standard_D2s_v5",
        "STANDARD_D64S_V3": "Standard_D32s_v3",
        "STANDARD_D32S_V3": "Standard_D16s_v3",
        "STANDARD_D16S_V3": "Standard_D8s_v3",
        "STANDARD_D8S_V3":  "Standard_D4s_v3",
        "STANDARD_D4S_V3":  "Standard_D2s_v3",
        "STANDARD_E64S_V5": "Standard_E32s_v5",
        "STANDARD_E32S_V5": "Standard_E16s_v5",
        "STANDARD_E16S_V5": "Standard_E8s_v5",
        "STANDARD_E8S_V5":  "Standard_E4s_v5",
        "STANDARD_F72S_V2": "Standard_F36s_v2",
        "STANDARD_F36S_V2": "Standard_F16s_v2",
        "STANDARD_F16S_V2": "Standard_F8s_v2",
    }
    return mappings.get(sku, "B-series burstable equivalent")


def _sku_vcpu_guess(sku: str) -> int:
    """Best-effort vCPU count from SKU name."""
    import re
    m = re.search(r'_(\d+)', sku.upper())
    return int(m.group(1)) if m else 4


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

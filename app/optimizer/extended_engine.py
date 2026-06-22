"""Extended optimization engine.

This layer keeps the existing engine intact and adds a more reliable, more
enterprise-ready analysis model with:
- richer findings metadata
- confidence scoring
- business impact and action priority
- governance and reliability checks
- profile-aware threshold overrides
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app.optimizer.advanced_rules import ADVANCED_RULES, AdvancedRule


@dataclass
class ExtendedFinding:
    rule_id: str
    rule_name: str
    category: str
    severity: str
    resource_id: str
    resource_name: str
    resource_type: str
    subscription_id: str
    resource_group: str
    location: str
    detail: str
    recommendation: str
    estimated_savings_usd: float
    annualized_savings_usd: float
    waste_score: int
    confidence_score: int
    action_priority: str
    impact: str
    evidence: dict[str, Any]
    tags: dict[str, Any]
    detected_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExtendedOptimizationEngine:
    def __init__(self, rule_overrides: dict[str, dict] | None = None):
        self.rules: dict[str, AdvancedRule] = {}
        import copy
        for rid, rule in ADVANCED_RULES.items():
            r = copy.deepcopy(rule)
            if rule_overrides and rid in rule_overrides:
                for k, v in rule_overrides[rid].items():
                    if hasattr(r, k):
                        setattr(r, k, v)
            self.rules[rid] = r

    def analyze(
        self,
        *,
        subscription_id: str,
        vms: list[dict] | None = None,
        disks: list[dict] | None = None,
        public_ips: list[dict] | None = None,
        storage: list[dict] | None = None,
        aks_clusters: list[dict] | None = None,
        aks_node_pools: dict[str, list] | None = None,
        sql_databases: list[dict] | None = None,
        cosmosdb: list[dict] | None = None,
        vm_metrics: dict[str, dict] | None = None,
        node_metrics: dict[str, dict] | None = None,
        cost_by_resource: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        findings: list[ExtendedFinding] = []
        findings.extend(self._analyze_vms(subscription_id, vms or [], vm_metrics or {}, cost_by_resource or {}))
        findings.extend(self._analyze_disks(subscription_id, disks or []))
        findings.extend(self._analyze_public_ips(subscription_id, public_ips or []))
        findings.extend(self._analyze_storage(subscription_id, storage or []))
        findings.extend(self._analyze_aks(subscription_id, aks_clusters or [], aks_node_pools or {}, node_metrics or {}))
        findings.extend(self._analyze_sql(subscription_id, sql_databases or []))
        findings.extend(self._analyze_cosmos(subscription_id, cosmosdb or []))
        findings.sort(key=lambda f: (self._severity_rank(f.severity), -f.estimated_savings_usd, -f.confidence_score))
        total = round(sum(f.estimated_savings_usd for f in findings), 2)
        return {
            "summary": {
                "total_findings": len(findings),
                "total_estimated_monthly_savings_usd": total,
                "total_estimated_annual_savings_usd": round(total * 12, 2),
                "by_severity": self._count_by(findings, "severity"),
                "by_category": self._count_by(findings, "category"),
                "average_confidence_score": round(sum(f.confidence_score for f in findings) / len(findings), 1) if findings else 0,
            },
            "findings": [f.to_dict() for f in findings],
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _analyze_vms(self, subscription_id: str, vms: list[dict], vm_metrics: dict[str, dict], cost_by_resource: dict[str, float]) -> list[ExtendedFinding]:
        out: list[ExtendedFinding] = []
        under = self.rules["VM_UNDERUTILIZED_EXTENDED"]
        family = self.rules["VM_RIGHTSIZE_FAMILY"]
        commit = self.rules["VM_COMMITMENT_CANDIDATE"]
        tags_rule = self.rules["VM_MISSING_GOVERNANCE_TAGS"]
        for vm in vms:
            rid = (vm.get("id") or "").lower()
            name = vm.get("name") or ""
            tags = vm.get("tags") or {}
            loc = vm.get("location") or ""
            props = vm.get("properties") or {}
            sku = ((props.get("hardwareProfile") or {}).get("vmSize") or "")
            monthly_cost = float(cost_by_resource.get(rid, 0.0))
            cpu = self._metric_average(vm_metrics.get(rid), "Percentage CPU")
            mem = self._metric_average(vm_metrics.get(rid), "Available Memory Bytes")
            if cpu is not None and monthly_cost >= under.min_monthly_savings_usd and cpu < under.cpu_idle_pct:
                savings = round(monthly_cost * 0.45, 2)
                out.append(self._finding(
                    rule=under,
                    subscription_id=subscription_id,
                    resource=vm,
                    detail=f"VM '{name}' shows sustained low CPU utilization ({cpu:.1f}%) with recurring monthly cost.",
                    recommendation="Downsize, schedule shutdown, or move suitable non-prod workloads to burstable or Spot-backed patterns.",
                    savings=savings,
                    waste_score=82,
                    confidence=88 if vm_metrics.get(rid) else 60,
                    priority="P1",
                    impact="High recurring compute savings",
                    evidence={"avg_cpu_pct": cpu, "vm_size": sku, "monthly_cost_usd": monthly_cost},
                ))
            if cpu is not None and cpu < family.cpu_oversize_pct and monthly_cost >= family.min_monthly_savings_usd:
                savings = round(monthly_cost * 0.25, 2)
                out.append(self._finding(
                    rule=family,
                    subscription_id=subscription_id,
                    resource=vm,
                    detail=f"VM '{name}' is a right-sizing candidate because CPU is consistently below {family.cpu_oversize_pct}%.",
                    recommendation="Model next-lower SKU family and verify memory/network requirements before resizing.",
                    savings=savings,
                    waste_score=64,
                    confidence=84 if vm_metrics.get(rid) else 58,
                    priority="P2",
                    impact="Meaningful compute optimization with low risk",
                    evidence={"avg_cpu_pct": cpu, "vm_size": sku, "monthly_cost_usd": monthly_cost},
                ))
            if monthly_cost >= commit.min_monthly_savings_usd and monthly_cost > 0:
                savings = round(monthly_cost * 0.18, 2)
                out.append(self._finding(
                    rule=commit,
                    subscription_id=subscription_id,
                    resource=vm,
                    detail=f"VM '{name}' has sufficient recurring spend to evaluate Reservations or Savings Plans.",
                    recommendation="Group always-on compute by family and region, then compare 1-year Reservation versus Savings Plan coverage.",
                    savings=savings,
                    waste_score=42,
                    confidence=70,
                    priority="P3",
                    impact="Portfolio-level discount opportunity",
                    evidence={"monthly_cost_usd": monthly_cost, "vm_size": sku},
                ))
            missing_tags = [t for t in tags_rule.require_tags if not tags.get(t)]
            if missing_tags:
                out.append(self._finding(
                    rule=tags_rule,
                    subscription_id=subscription_id,
                    resource=vm,
                    detail=f"VM '{name}' is missing governance tags: {', '.join(missing_tags)}.",
                    recommendation="Enforce Azure Policy for required tags so savings can be assigned to owners and cost centers.",
                    savings=0,
                    waste_score=38,
                    confidence=96,
                    priority="P2",
                    impact="Improves accountability and recommendation quality",
                    evidence={"missing_tags": missing_tags},
                ))
        return out

    def _analyze_disks(self, subscription_id: str, disks: list[dict]) -> list[ExtendedFinding]:
        out: list[ExtendedFinding] = []
        rule = self.rules["DISK_UNUSED_EXTENDED"]
        for disk in disks:
            props = disk.get("properties") or {}
            state = props.get("diskState") or ""
            size_gb = props.get("diskSizeGB") or 0
            sku_name = ((disk.get("sku") or {}).get("name") or "")
            if state == "Unattached":
                est = round((0.17 if "Premium" in sku_name else 0.05) * size_gb, 2)
                out.append(self._finding(
                    rule=rule,
                    subscription_id=subscription_id,
                    resource=disk,
                    detail=f"Disk '{disk.get('name')}' is unattached and still billable.",
                    recommendation="Delete unused disks or snapshot only what must be retained for recovery requirements.",
                    savings=est,
                    waste_score=86,
                    confidence=94,
                    priority="P1",
                    impact="Direct storage cost reduction",
                    evidence={"disk_state": state, "size_gb": size_gb, "sku": sku_name},
                ))
        return out

    def _analyze_public_ips(self, subscription_id: str, public_ips: list[dict]) -> list[ExtendedFinding]:
        out: list[ExtendedFinding] = []
        rule = self.rules["PUBLIC_IP_IDLE_EXTENDED"]
        for ip in public_ips:
            props = ip.get("properties") or {}
            assoc = props.get("ipConfiguration") or props.get("natGateway")
            alloc = props.get("publicIPAllocationMethod") or ""
            if alloc == "Static" and not assoc:
                out.append(self._finding(
                    rule=rule,
                    subscription_id=subscription_id,
                    resource=ip,
                    detail=f"Public IP '{ip.get('name')}' is static and not associated to any live resource.",
                    recommendation="Delete idle static public IPs after confirming no DNS or failover dependency exists.",
                    savings=3.65,
                    waste_score=80,
                    confidence=95,
                    priority="P2",
                    impact="Low-risk direct network savings",
                    evidence={"allocation": alloc},
                ))
        return out

    def _analyze_storage(self, subscription_id: str, storage: list[dict]) -> list[ExtendedFinding]:
        out: list[ExtendedFinding] = []
        rule = self.rules["STORAGE_LIFECYCLE_EXTENDED"]
        for acct in storage:
            props = acct.get("properties") or {}
            tier = props.get("accessTier") or "Unknown"
            out.append(self._finding(
                rule=rule,
                subscription_id=subscription_id,
                resource=acct,
                detail=f"Storage account '{acct.get('name')}' should be reviewed for Hot/Cool/Archive lifecycle automation.",
                recommendation=f"Add lifecycle rules to move cold data to Cool after {rule.storage_cool_after_days} days and Archive after {rule.storage_archive_after_days} days.",
                savings=0,
                waste_score=32,
                confidence=62,
                priority="P3",
                impact="Can reduce blob storage cost for cold data",
                evidence={"access_tier": tier},
            ))
        return out

    def _analyze_aks(self, subscription_id: str, clusters: list[dict], aks_node_pools: dict[str, list], node_metrics: dict[str, dict]) -> list[ExtendedFinding]:
        out: list[ExtendedFinding] = []
        idle_rule = self.rules["AKS_IDLE_POOL_EXTENDED"]
        nonprod_rule = self.rules["AKS_NONPROD_SCHEDULING"]
        reliability_rule = self.rules["AKS_SYSTEM_POOL_RELIABILITY"]
        for cluster in clusters:
            cid = cluster.get("id") or ""
            cname = cluster.get("name") or ""
            tags = cluster.get("tags") or {}
            env = str(tags.get("environment") or tags.get("env") or "").lower()
            pools = aks_node_pools.get(cid) or aks_node_pools.get(cid.lower()) or ((cluster.get("properties") or {}).get("agentPoolProfiles") or [])
            if env in nonprod_rule.nonprod_tag_values:
                out.append(self._finding(
                    rule=nonprod_rule,
                    subscription_id=subscription_id,
                    resource=cluster,
                    detail=f"AKS cluster '{cname}' appears non-production (env={env}) and should use cost-aware runtime scheduling.",
                    recommendation=f"Apply nightly shutdown or aggressive autoscaling to save up to {nonprod_rule.nonprod_shutdown_hours_per_day} hours/day of idle runtime.",
                    savings=0,
                    waste_score=58,
                    confidence=76,
                    priority="P2",
                    impact="Substantial non-prod cluster savings",
                    evidence={"environment": env, "pool_count": len(pools)},
                ))
            for pool in pools:
                mode = str(pool.get("mode") or "User")
                count = int(pool.get("count") or pool.get("nodeCount") or 0)
                if mode.lower() == "system" and env in reliability_rule.prod_tag_values and count < reliability_rule.aks_min_system_nodes:
                    out.append(self._finding(
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
                if count > 0:
                    idle_nodes = 0
                    prefix = f"{cname}-{pool.get('name', '')}".lower()
                    for key, metric in node_metrics.items():
                        if prefix and prefix in key.lower():
                            cpu = self._generic_metric_average(metric)
                            if cpu is not None and cpu < idle_rule.node_cpu_idle_pct:
                                idle_nodes += 1
                    if idle_nodes and (idle_nodes / max(count, 1)) >= idle_rule.aks_max_idle_node_ratio:
                        out.append(self._finding(
                            rule=idle_rule,
                            subscription_id=subscription_id,
                            resource=cluster,
                            detail=f"AKS pool '{pool.get('name')}' on cluster '{cname}' has {idle_nodes}/{count} idle nodes.",
                            recommendation="Lower max node count, enable autoscaler, and split noisy workloads into distinct pools.",
                            savings=0,
                            waste_score=74,
                            confidence=72 if node_metrics else 52,
                            priority="P1",
                            impact="Reduces persistent AKS node waste",
                            evidence={"idle_nodes": idle_nodes, "node_count": count},
                        ))
        return out

    def _analyze_sql(self, subscription_id: str, sql_databases: list[dict]) -> list[ExtendedFinding]:
        out: list[ExtendedFinding] = []
        rule = self.rules["SQL_SERVERLESS_EXTENDED"]
        for db in sql_databases:
            sku = db.get("sku") or {}
            tier = sku.get("tier") or ""
            name = db.get("name") or ""
            if tier in {"GeneralPurpose", "Standard", "BusinessCritical"} and "serverless" not in str(sku.get("name") or "").lower():
                out.append(self._finding(
                    rule=rule,
                    subscription_id=subscription_id,
                    resource=db,
                    detail=f"SQL database '{name}' is provisioned and should be reviewed for serverless eligibility.",
                    recommendation="Move dev/test and intermittent workloads to serverless compute with auto-pause where supported.",
                    savings=0,
                    waste_score=48,
                    confidence=66,
                    priority="P3",
                    impact="Can reduce idle database compute spend",
                    evidence={"sku": sku},
                ))
        return out

    def _analyze_cosmos(self, subscription_id: str, cosmosdb: list[dict]) -> list[ExtendedFinding]:
        out: list[ExtendedFinding] = []
        rule = self.rules["COSMOS_AUTOSCALE_EXTENDED"]
        for acct in cosmosdb:
            props = acct.get("properties") or {}
            capabilities = props.get("capabilities") or []
            is_serverless = any(c.get("name") == "EnableServerless" for c in capabilities)
            if not is_serverless:
                out.append(self._finding(
                    rule=rule,
                    subscription_id=subscription_id,
                    resource=acct,
                    detail=f"Cosmos DB account '{acct.get('name')}' is not serverless-enabled and may be over-provisioned.",
                    recommendation="Evaluate autoscale or serverless based on request volume variance and RU utilization.",
                    savings=0,
                    waste_score=44,
                    confidence=64,
                    priority="P3",
                    impact="Potential RU/s spend optimization",
                    evidence={"capabilities": capabilities},
                ))
        return out

    def _finding(self, *, rule: AdvancedRule, subscription_id: str, resource: dict, detail: str, recommendation: str, savings: float, waste_score: int, confidence: int, priority: str, impact: str, evidence: dict[str, Any]) -> ExtendedFinding:
        rid = resource.get("id") or ""
        return ExtendedFinding(
            rule_id=rule.id,
            rule_name=rule.name,
            category=rule.category.value,
            severity=rule.severity.value,
            resource_id=rid,
            resource_name=resource.get("name") or "",
            resource_type=resource.get("type") or "",
            subscription_id=subscription_id,
            resource_group=self._extract_rg(rid),
            location=resource.get("location") or "",
            detail=detail,
            recommendation=recommendation,
            estimated_savings_usd=round(savings, 2),
            annualized_savings_usd=round(savings * 12, 2),
            waste_score=waste_score,
            confidence_score=confidence,
            action_priority=priority,
            impact=impact,
            evidence=evidence,
            tags=resource.get("tags") or {},
            detected_at=datetime.now(timezone.utc).isoformat(),
        )

    def _count_by(self, findings: list[ExtendedFinding], field: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in findings:
            key = getattr(f, field)
            out[key] = out.get(key, 0) + 1
        return out

    def _severity_rank(self, severity: str) -> int:
        return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}.get(severity, 9)

    def _extract_rg(self, resource_id: str) -> str:
        parts = resource_id.split("/")
        for i, p in enumerate(parts):
            if p.lower() == "resourcegroups" and i + 1 < len(parts):
                return parts[i + 1]
        return ""

    def _metric_average(self, metrics: dict[str, Any] | None, name: str) -> float | None:
        if not metrics:
            return None
        for item in metrics.get("value", []):
            if (item.get("name") or {}).get("value") == name:
                vals = []
                for ts in item.get("timeseries", []):
                    for point in ts.get("data", []):
                        if point.get("average") is not None:
                            vals.append(point["average"])
                if vals:
                    return sum(vals) / len(vals)
        return None

    def _generic_metric_average(self, metrics: dict[str, Any] | None) -> float | None:
        if not metrics:
            return None
        vals = []
        for item in metrics.get("value", []):
            for ts in item.get("timeseries", []):
                for point in ts.get("data", []):
                    if point.get("average") is not None:
                        vals.append(point["average"])
        if vals:
            return sum(vals) / len(vals)
        return None

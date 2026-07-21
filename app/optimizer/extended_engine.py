"""Extended optimization engine.

Delegates per-resource analysis to ``app.optimizer.resource_engines`` modules.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from app.optimizer.analysis_routing import filter_buckets_for_legacy_analysis
from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.core.engine_helpers import EngineAnalysisHelpers
from app.optimizer.core.finding import ExtendedFinding
from app.optimizer.resource_engines.registry import run_sub_engines
from app.optimizer.resource_engines.runtime.context import AnalysisContext
from app.optimizer.rule_overrides import apply_rule_overrides

__all__ = ["ExtendedFinding", "ExtendedOptimizationEngine"]


class ExtendedOptimizationEngine(EngineAnalysisHelpers):
    def __init__(self, rule_overrides: dict[str, dict] | None = None, global_config: dict | None = None):
        from app.optimizer.engine_runtime import split_rule_overrides

        rule_only, inline_global = split_rule_overrides(rule_overrides)
        self.global_config = {**(global_config or {}), **inline_global}
        self._rule_overrides = rule_only
        self.rules: dict[str, Any] = {}
        self._vm_catalog_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._aks_k8s_versions_cache: dict[tuple[str, str], set[str]] = {}
        self._aks_k8s_catalog_cache: dict[tuple[str, str], dict[str, Any]] = {}
        for rid, rule in ADVANCED_RULES.items():
            r = copy.deepcopy(rule)
            if rule_only and rid in rule_only:
                apply_rule_overrides(r, rule_only[rid])
            self.rules[rid] = r
        from app.cosmos_analysis_config import hydrate_cosmos_rules
        from app.disk_analysis_config import hydrate_disk_rules

        hydrate_disk_rules(self.rules)
        hydrate_cosmos_rules(self.rules)

    def analyze(
        self,
        *,
        subscription_id: str,
        vms: list[dict] | None = None,
        vmss: list[dict] | None = None,
        disks: list[dict] | None = None,
        snapshots: list[dict] | None = None,
        public_ips: list[dict] | None = None,
        load_balancers: list[dict] | None = None,
        app_gateways: list[dict] | None = None,
        app_services: list[dict] | None = None,
        app_service_plans: list[dict] | None = None,
        network_interfaces: list[dict] | None = None,
        nat_gateways: list[dict] | None = None,
        redis_caches: list[dict] | None = None,
        storage: list[dict] | None = None,
        aks_clusters: list[dict] | None = None,
        aks_node_pools: dict[str, list] | None = None,
        sql_databases: list[dict] | None = None,
        cosmosdb: list[dict] | None = None,
        keyvaults: list[dict] | None = None,
        nsgs: list[dict] | None = None,
        postgresql: list[dict] | None = None,
        container_registries: list[dict] | None = None,
        log_analytics_workspaces: list[dict] | None = None,
        app_insights_components: list[dict] | None = None,
        apim_services: list[dict] | None = None,
        data_factories: list[dict] | None = None,
        logic_apps: list[dict] | None = None,
        event_hubs: list[dict] | None = None,
        service_bus_namespaces: list[dict] | None = None,
        databricks_workspaces: list[dict] | None = None,
        synapse_workspaces: list[dict] | None = None,
        adx_clusters: list[dict] | None = None,
        ml_workspaces: list[dict] | None = None,
        recovery_vaults: list[dict] | None = None,
        cognitive_search_services: list[dict] | None = None,
        firewalls: list[dict] | None = None,
        cdn_profiles: list[dict] | None = None,
        expressroute_circuits: list[dict] | None = None,
        traffic_managers: list[dict] | None = None,
        front_doors: list[dict] | None = None,
        vnets: list[dict] | None = None,
        private_endpoints: list[dict] | None = None,
        private_link_services: list[dict] | None = None,
        private_dns_zones: list[dict] | None = None,
        budgets: list[dict] | None = None,
        subscription_spend_usd: float = 0.0,
        vm_metrics: dict[str, dict] | None = None,
        node_metrics: dict[str, dict] | None = None,
        resource_metrics: dict[str, dict] | None = None,
        resource_facts: dict[str, dict[str, float]] | None = None,
        cost_by_resource: dict[str, float] | None = None,
        resource_graph: dict[str, dict[str, list[str]]] | None = None,
        cost_history: dict[str, list[float]] | None = None,
        resource_cost_histories: dict[str, list[float]] | None = None,
        utilization_trends: dict[str, dict[str, dict[str, Any]]] | None = None,
        workload_classes: dict[str, str] | None = None,
        advisor_vm_targets: dict[str, Any] | None = None,
        advisor_by_resource: dict[str, list[Any]] | None = None,
        db: Any | None = None,
        scoped_canonical_types: list[str] | None = None,
    ) -> dict[str, Any]:
        from app.optimizer.engine_runtime import build_standard_rules, filter_resources
        from app.optimizer.post_analysis import run_post_analysis

        gc = self.global_config
        buckets = {
            "vms": filter_resources(vms, gc),
            "vmss": filter_resources(vmss, gc),
            "disks": filter_resources(disks, gc),
            "snapshots": filter_resources(snapshots, gc),
            "public_ips": filter_resources(public_ips, gc),
            "load_balancers": filter_resources(load_balancers, gc),
            "app_gateways": filter_resources(app_gateways, gc),
            "app_services": filter_resources(app_services, gc),
            "app_service_plans": filter_resources(app_service_plans, gc),
            "network_interfaces": filter_resources(network_interfaces, gc),
            "nat_gateways": filter_resources(nat_gateways, gc),
            "redis_caches": filter_resources(redis_caches, gc),
            "storage": filter_resources(storage, gc),
            "aks_clusters": filter_resources(aks_clusters, gc),
            "sql_databases": filter_resources(sql_databases, gc),
            "cosmosdb": filter_resources(cosmosdb, gc),
            "keyvaults": filter_resources(keyvaults, gc),
            "nsgs": filter_resources(nsgs, gc),
            "postgresql": filter_resources(postgresql, gc),
            "container_registries": filter_resources(container_registries, gc),
            "log_analytics_workspaces": filter_resources(log_analytics_workspaces, gc),
            "app_insights_components": filter_resources(app_insights_components, gc),
            "apim_services": filter_resources(apim_services, gc),
            "data_factories": filter_resources(data_factories, gc),
            "logic_apps": filter_resources(logic_apps, gc),
            "event_hubs": filter_resources(event_hubs, gc),
            "service_bus_namespaces": filter_resources(service_bus_namespaces, gc),
            "databricks_workspaces": filter_resources(databricks_workspaces, gc),
            "synapse_workspaces": filter_resources(synapse_workspaces, gc),
            "adx_clusters": filter_resources(adx_clusters, gc),
            "ml_workspaces": filter_resources(ml_workspaces, gc),
            "recovery_vaults": filter_resources(recovery_vaults, gc),
            "cognitive_search_services": filter_resources(cognitive_search_services, gc),
            "firewalls": filter_resources(firewalls, gc),
            "cdn_profiles": filter_resources(cdn_profiles, gc),
            "expressroute_circuits": filter_resources(expressroute_circuits, gc),
            "traffic_managers": filter_resources(traffic_managers, gc),
            "front_doors": filter_resources(front_doors, gc),
            "vnets": filter_resources(vnets, gc),
            "private_endpoints": filter_resources(private_endpoints, gc),
            "private_link_services": filter_resources(private_link_services, gc),
            "private_dns_zones": filter_resources(private_dns_zones, gc),
        }
        buckets = filter_buckets_for_legacy_analysis(
            buckets,
            preserve_canonical_types={
                t.strip().lower() for t in (scoped_canonical_types or []) if t and t.strip()
            } or None,
        )
        ctx = AnalysisContext(
            subscription_id=subscription_id,
            rules=self.rules,
            cost_by_resource=cost_by_resource or {},
            global_config=self.global_config,
            vm_metrics=vm_metrics or {},
            node_metrics=node_metrics or {},
            resource_metrics=resource_metrics or vm_metrics or {},
            resource_facts=resource_facts or {},
            aks_node_pools=aks_node_pools or {},
            subscription_spend_usd=subscription_spend_usd,
            resource_graph=resource_graph or {},
            cost_history=cost_history or {},
            resource_cost_histories=resource_cost_histories or {},
            utilization_trends=utilization_trends or {},
            workload_classes=workload_classes or {},
            advisor_vm_targets=advisor_vm_targets or {},
            advisor_by_resource=advisor_by_resource or {},
        )
        if cost_history:
            buckets["cost_anomalies"] = [{"trigger": True}]
        findings: list[ExtendedFinding] = run_sub_engines(
            self,
            ctx,
            buckets,
            budgets=budgets,
            db=db,
            scoped_canonical_types=scoped_canonical_types,
        )
        std_engine = type("StdBridge", (), {"rules": build_standard_rules(self._rule_overrides), "global_config": self.global_config})()
        post_rows = run_post_analysis(std_engine, buckets=buckets, cost_by_resource=cost_by_resource, subscription_id=subscription_id)
        for row in post_rows:
            payload = row.to_dict()
            findings.append(ExtendedFinding(
                rule_id=payload["rule_id"],
                rule_name=payload["rule_name"],
                category=payload["category"],
                severity=payload["severity"],
                resource_id=payload["resource_id"],
                resource_name=payload["resource_name"],
                resource_type=payload["resource_type"],
                subscription_id=payload["subscription_id"],
                resource_group=payload["resource_group"],
                location=payload["location"],
                detail=payload["detail"],
                recommendation=payload["recommendation"],
                estimated_savings_usd=payload["estimated_savings_usd"],
                annualized_savings_usd=round(payload["estimated_savings_usd"] * 12, 2),
                waste_score=payload["waste_score"],
                confidence_score=60,
                action_priority="P3",
                impact=payload["recommendation"],
                evidence=payload.get("evidence") or {},
                tags=payload.get("tags") or {},
                detected_at=payload["detected_at"],
            ))
        findings.sort(
            key=lambda f: (self._severity_rank(f.severity), -f.estimated_savings_usd, -f.confidence_score),
        )
        total = round(sum(f.estimated_savings_usd for f in findings), 2)
        return {
            "summary": {
                "total_findings": len(findings),
                "total_estimated_monthly_savings_usd": total,
                "total_estimated_annual_savings_usd": round(total * 12, 2),
                "by_severity": self._count_by(findings, "severity"),
                "by_category": self._count_by(findings, "category"),
                "by_priority": self._count_by(findings, "action_priority"),
                "top_rules": self._top_rules(findings),
                "average_confidence_score": round(sum(f.confidence_score for f in findings) / len(findings), 1)
                if findings else 0,
            },
            "findings": [f.to_dict() for f in findings],
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "engine_version": "extended",
        }

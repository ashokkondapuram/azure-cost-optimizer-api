"""Extended optimization engine.

Delegates per-resource analysis to ``app.optimizer.resource_engines`` modules.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.core.engine_helpers import EngineAnalysisHelpers
from app.optimizer.core.finding import ExtendedFinding
from app.optimizer.resource_engines.registry import run_sub_engines
from app.optimizer.resource_engines.runtime.context import AnalysisContext
from app.optimizer.rule_overrides import apply_rule_overrides

__all__ = ["ExtendedFinding", "ExtendedOptimizationEngine"]


class ExtendedOptimizationEngine(EngineAnalysisHelpers):
    def __init__(self, rule_overrides: dict[str, dict] | None = None):
        self.rules: dict[str, Any] = {}
        self._vm_catalog_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._aks_k8s_versions_cache: dict[tuple[str, str], set[str]] = {}
        self._aks_k8s_catalog_cache: dict[tuple[str, str], dict[str, Any]] = {}
        for rid, rule in ADVANCED_RULES.items():
            r = copy.deepcopy(rule)
            if rule_overrides and rid in rule_overrides:
                apply_rule_overrides(r, rule_overrides[rid])
            self.rules[rid] = r

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
    ) -> dict[str, Any]:
        buckets = {
            "vms": vms or [],
            "vmss": vmss or [],
            "disks": disks or [],
            "snapshots": snapshots or [],
            "public_ips": public_ips or [],
            "load_balancers": load_balancers or [],
            "app_gateways": app_gateways or [],
            "app_services": app_services or [],
            "app_service_plans": app_service_plans or [],
            "network_interfaces": network_interfaces or [],
            "nat_gateways": nat_gateways or [],
            "redis_caches": redis_caches or [],
            "storage": storage or [],
            "aks_clusters": aks_clusters or [],
            "sql_databases": sql_databases or [],
            "cosmosdb": cosmosdb or [],
            "keyvaults": keyvaults or [],
            "nsgs": nsgs or [],
            "postgresql": postgresql or [],
            "container_registries": container_registries or [],
            "log_analytics_workspaces": log_analytics_workspaces or [],
            "app_insights_components": app_insights_components or [],
            "apim_services": apim_services or [],
            "data_factories": data_factories or [],
            "logic_apps": logic_apps or [],
            "event_hubs": event_hubs or [],
            "service_bus_namespaces": service_bus_namespaces or [],
            "databricks_workspaces": databricks_workspaces or [],
            "synapse_workspaces": synapse_workspaces or [],
            "adx_clusters": adx_clusters or [],
            "ml_workspaces": ml_workspaces or [],
            "recovery_vaults": recovery_vaults or [],
            "cognitive_search_services": cognitive_search_services or [],
            "firewalls": firewalls or [],
            "cdn_profiles": cdn_profiles or [],
            "vnets": vnets or [],
            "private_endpoints": private_endpoints or [],
            "private_link_services": private_link_services or [],
            "private_dns_zones": private_dns_zones or [],
        }
        ctx = AnalysisContext(
            subscription_id=subscription_id,
            rules=self.rules,
            cost_by_resource=cost_by_resource or {},
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
        )
        if cost_history:
            buckets["cost_anomalies"] = [{"trigger": True}]
        findings: list[ExtendedFinding] = run_sub_engines(
            self,
            ctx,
            buckets,
            budgets=budgets,
        )
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

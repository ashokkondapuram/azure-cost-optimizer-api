"""Per-resource-type optimization sub-engines (one per analysis batch component)."""
from __future__ import annotations

from typing import Any

from .base import ResourceSubEngine


class VmSubEngine(ResourceSubEngine):
    component = "Virtual Machines"
    bucket_keys = ("vms",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        vms = self.prepare_resources(buckets.get("vms") or [], metrics_kind="vm")
        findings = self.engine._analyze_vms(
            self.ctx.subscription_id,
            vms,
            self.ctx.vm_metrics,
            self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, vms)


class VmssSubEngine(ResourceSubEngine):
    component = "Virtual Machine Scale Sets"
    bucket_keys = ("vmss",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        scale_sets = self.prepare_resources(buckets.get("vmss") or [], metrics_kind="vm")
        findings = self.engine._analyze_vms(
            self.ctx.subscription_id,
            scale_sets,
            self.ctx.vm_metrics,
            self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, scale_sets)


class DiskSubEngine(ResourceSubEngine):
    component = "Managed Disks"
    bucket_keys = ("disks",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        disks = self.prepare_resources(buckets.get("disks") or [])
        findings = self.engine._analyze_disks(
            self.ctx.subscription_id,
            disks,
            self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, disks)


class SnapshotSubEngine(ResourceSubEngine):
    component = "Disk Snapshots"
    bucket_keys = ("snapshots",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        snapshots = self.prepare_resources(buckets.get("snapshots") or [])
        findings = self.engine._analyze_snapshots(
            self.ctx.subscription_id,
            snapshots,
            self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, snapshots)


class AksSubEngine(ResourceSubEngine):
    component = "AKS"
    bucket_keys = ("aks_clusters",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        clusters = self.prepare_resources(buckets.get("aks_clusters") or [], metrics_kind="node")
        findings = self.engine._analyze_aks(
            self.ctx.subscription_id,
            clusters,
            self.ctx.aks_node_pools,
            self.ctx.node_metrics,
            self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, clusters)


class AppServiceSubEngine(ResourceSubEngine):
    component = "App Service"
    bucket_keys = ("app_services", "app_service_plans")

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        apps = self.prepare_resources(buckets.get("app_services") or [])
        plans = self.prepare_resources(buckets.get("app_service_plans") or [])
        findings = self.engine._analyze_app_services(
            self.ctx.subscription_id,
            apps,
            plans,
            self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, apps + plans)


class StorageSubEngine(ResourceSubEngine):
    component = "Storage Accounts"
    bucket_keys = ("storage",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        storage = self.prepare_resources(buckets.get("storage") or [])
        findings = self.engine._analyze_storage(self.ctx.subscription_id, storage)
        return self.enhance_findings(findings, storage)


class PublicIpSubEngine(ResourceSubEngine):
    component = "Public IPs"
    bucket_keys = ("public_ips",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        ips = self.prepare_resources(buckets.get("public_ips") or [])
        findings = self.engine._analyze_public_ips(
            self.ctx.subscription_id, ips, self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, ips)


class NicSubEngine(ResourceSubEngine):
    component = "Network Interfaces"
    bucket_keys = ("network_interfaces",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        nics = self.prepare_resources(buckets.get("network_interfaces") or [])
        findings = self.engine._analyze_network_interfaces(self.ctx.subscription_id, nics)
        return self.enhance_findings(findings, nics)


class NatSubEngine(ResourceSubEngine):
    component = "NAT Gateways"
    bucket_keys = ("nat_gateways",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        nats = self.prepare_resources(buckets.get("nat_gateways") or [])
        findings = self.engine._analyze_nat_gateways(
            self.ctx.subscription_id, nats, self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, nats)


class NsgSubEngine(ResourceSubEngine):
    component = "Network Security Groups"
    bucket_keys = ("nsgs",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        nsgs = self.prepare_resources(buckets.get("nsgs") or [])
        findings = self.engine._analyze_nsgs(self.ctx.subscription_id, nsgs)
        return self.enhance_findings(findings, nsgs)


class LoadBalancerSubEngine(ResourceSubEngine):
    component = "Load Balancers"
    bucket_keys = ("load_balancers",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        lbs = self.prepare_resources(buckets.get("load_balancers") or [])
        findings = self.engine._analyze_load_balancers(
            self.ctx.subscription_id, lbs, self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, lbs)


class AppGatewaySubEngine(ResourceSubEngine):
    component = "Application Gateways"
    bucket_keys = ("app_gateways",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        gateways = self.prepare_resources(buckets.get("app_gateways") or [])
        findings = self.engine._analyze_app_gateways(
            self.ctx.subscription_id, gateways, self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, gateways)


class SqlSubEngine(ResourceSubEngine):
    component = "SQL Database"
    bucket_keys = ("sql_servers", "sql_databases")

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        servers = self.prepare_resources(buckets.get("sql_servers") or [])
        databases = self.prepare_resources(buckets.get("sql_databases") or [])
        findings = self.engine._analyze_sql(self.ctx.subscription_id, databases)
        return self.enhance_findings(findings, servers + databases)


class PostgresqlSubEngine(ResourceSubEngine):
    component = "PostgreSQL"
    bucket_keys = ("postgresql",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        servers = self.prepare_resources(buckets.get("postgresql") or [])
        findings = self.engine._analyze_postgresql(
            self.ctx.subscription_id, servers, self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, servers)


class CosmosSubEngine(ResourceSubEngine):
    component = "Cosmos DB"
    bucket_keys = ("cosmosdb",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        accounts = self.prepare_resources(buckets.get("cosmosdb") or [])
        findings = self.engine._analyze_cosmos(self.ctx.subscription_id, accounts)
        return self.enhance_findings(findings, accounts)


class RedisSubEngine(ResourceSubEngine):
    component = "Redis Cache"
    bucket_keys = ("redis_caches",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        caches = self.prepare_resources(buckets.get("redis_caches") or [])
        findings = self.engine._analyze_redis(
            self.ctx.subscription_id, caches, self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, caches)


class AcrSubEngine(ResourceSubEngine):
    component = "Container Registry"
    bucket_keys = ("container_registries",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        registries = self.prepare_resources(buckets.get("container_registries") or [])
        findings = self.engine._analyze_acr(
            self.ctx.subscription_id, registries, self.ctx.cost_by_resource,
        )
        return self.enhance_findings(findings, registries)


class KeyVaultSubEngine(ResourceSubEngine):
    component = "Key Vault"
    bucket_keys = ("keyvaults",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        vaults = self.prepare_resources(buckets.get("keyvaults") or [])
        findings = self.engine._analyze_keyvaults(self.ctx.subscription_id, vaults)
        return self.enhance_findings(findings, vaults)


class BudgetSubEngine(ResourceSubEngine):
    component = "Budgets"
    bucket_keys = ("budgets",)

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        budgets = buckets.get("budgets") or []
        findings = self.engine._analyze_budgets(
            self.ctx.subscription_id,
            budgets,
            self.ctx.subscription_spend_usd,
        )
        return findings

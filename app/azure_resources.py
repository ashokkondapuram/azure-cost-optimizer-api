"""Azure Resource Manager — typed resource fetchers using official API versions.

All API versions sourced from:
https://learn.microsoft.com/en-us/rest/api/azure/

Improvements:
  - list_vms / list_vm_scale_sets now accept include_maintenance flag to
    attach AzureMaintenanceClient data without a separate call.
  - get_resource_health_overview() added for dashboard use.
  - list_all_resources_parallel() fans out resource-type fetches concurrently.
"""
import concurrent.futures
import os
import structlog
from app.auth import auth_headers
from app.arm_api_versions import (
    ARM_GET_API_VERSIONS,
    MONITOR_METRICS_API_VERSION,
    RESOURCES_LIST_API_VERSION,
    SUBSCRIPTIONS_LIST_API_VERSION,
)
from app.http_client import _get, get_all_pages, BASE, AzureAPIError, arm_patient_active, _patch
from app.vm_utils import filter_standalone_vms

log = structlog.get_logger()

_COMPUTE_VM_API_VERSION = ARM_GET_API_VERSIONS["microsoft.compute/virtualmachines"]
_COMPUTE_VMSS_API_VERSION = ARM_GET_API_VERSIONS["microsoft.compute/virtualmachinescalesets"]
_COMPUTE_DISK_API_VERSION = ARM_GET_API_VERSIONS["microsoft.compute/disks"]
_COMPUTE_SNAPSHOT_API_VERSION = ARM_GET_API_VERSIONS["microsoft.compute/snapshots"]
_APPLICATION_GATEWAY_API_VERSION = ARM_GET_API_VERSIONS["microsoft.network/applicationgateways"]
_STORAGE_ACCOUNT_API_VERSION = ARM_GET_API_VERSIONS["microsoft.storage/storageaccounts"]
_AKS_API_VERSION = ARM_GET_API_VERSIONS["microsoft.containerservice/managedclusters"]
_NETWORK_API_VERSION = ARM_GET_API_VERSIONS["microsoft.network/publicipaddresses"]
_WEB_SITES_API_VERSION = ARM_GET_API_VERSIONS["microsoft.web/sites"]
_WEB_SERVERFARMS_API_VERSION = ARM_GET_API_VERSIONS["microsoft.web/serverfarms"]

_VM_INSTANCE_VIEW_WORKERS = max(1, int(os.getenv("ARM_VM_INSTANCE_VIEW_WORKERS", "4")))

# Resource types to fetch in parallel during list_all_resources_parallel
_PARALLEL_RESOURCE_TYPES = [
    "Microsoft.Compute/virtualMachines",
    "Microsoft.Compute/virtualMachineScaleSets",
    "Microsoft.Compute/disks",
    "Microsoft.Compute/snapshots",
    "Microsoft.ContainerService/managedClusters",
    "Microsoft.Storage/storageAccounts",
    "Microsoft.Web/sites",
    "Microsoft.Web/serverFarms",
    "Microsoft.Sql/servers",
    "Microsoft.Network/publicIPAddresses",
    "Microsoft.Network/loadBalancers",
    "Microsoft.Network/applicationGateways",
    "Microsoft.Network/networkSecurityGroups",
    "Microsoft.Cache/redis",
    "Microsoft.KeyVault/vaults",
    "Microsoft.ContainerRegistry/registries",
]


def _rg_from_id(resource_id: str) -> str:
    parts = resource_id.split("/")
    try:
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""


class AzureResourcesClient:

    def __init__(self, db=None):
        self._db = db

    def _headers(self, db=None) -> dict:
        return auth_headers(db if db is not None else self._db)

    # ------------------------------------------------------------------ #
    #  Generic resource list                                              #
    # ------------------------------------------------------------------ #
    def list_resources(self, subscription_id: str, resource_type: str | None = None) -> list:
        params = {"api-version": RESOURCES_LIST_API_VERSION}
        if resource_type:
            params["$filter"] = f"resourceType eq '{resource_type}'"
        url = f"{BASE}/subscriptions/{subscription_id}/resources"
        return get_all_pages(url, self._headers(), params)

    def list_resource_groups(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/resourcegroups"
        return get_all_pages(url, self._headers(), {"api-version": RESOURCES_LIST_API_VERSION})

    def list_subscriptions(self) -> list:
        url = f"{BASE}/subscriptions"
        return get_all_pages(url, self._headers(), {"api-version": SUBSCRIPTIONS_LIST_API_VERSION})

    def list_all_resources_parallel(
        self,
        subscription_id: str,
        resource_types: list[str] | None = None,
        max_workers: int = 6,
    ) -> dict[str, list]:
        """Fetch multiple resource types concurrently.

        Returns a dict keyed by resource type (lowercased) → list of resources.
        Errors for individual types are logged and an empty list is returned for that type.
        """
        types = resource_types or _PARALLEL_RESOURCE_TYPES

        def fetch(rtype: str) -> tuple[str, list]:
            try:
                return rtype.lower(), self.list_resources(subscription_id, rtype)
            except Exception as exc:
                log.warning("list_all_resources_parallel.failed", rtype=rtype, error=str(exc))
                return rtype.lower(), []

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="res_parallel"
        ) as pool:
            results = dict(pool.map(fetch, types))
        log.info(
            "list_all_resources_parallel.done",
            types=len(types),
            total=sum(len(v) for v in results.values()),
        )
        return results

    # ------------------------------------------------------------------ #
    #  Compute                                                            #
    # ------------------------------------------------------------------ #
    _TRANSIENT_ARM = {500, 502, 503, 504}

    def _list_vms_compute(self, subscription_id: str, *, expand_instance_view: bool = False) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute/virtualMachines"
        params = {"api-version": _COMPUTE_VM_API_VERSION}
        if expand_instance_view:
            params = {**params, "$expand": "instanceView"}
        return get_all_pages(url, self._headers(), params)

    def _list_vms_with_fallback(self, subscription_id: str) -> list:
        try:
            return self._list_vms_compute(subscription_id)
        except AzureAPIError as exc:
            if exc.status not in self._TRANSIENT_ARM:
                raise
            log.warning("list_vms.compute_provider_failed", status=exc.status, fallback="resources_api")
            return self.list_resources(subscription_id, "Microsoft.Compute/virtualMachines")

    def list_vms(
        self,
        subscription_id: str,
        include_instance_view: bool = True,
        include_maintenance: bool = False,
    ) -> list:
        """List VMs. Optionally attach maintenance status via AzureMaintenanceClient."""
        if not include_instance_view:
            vms = self._list_vms_with_fallback(subscription_id)
            vms = filter_standalone_vms(vms)
        else:
            vms = self._list_vms_with_fallback(subscription_id)
            vms = filter_standalone_vms(vms)
            vms = self._attach_instance_views(subscription_id, vms)

        if include_maintenance:
            from app.azure_maintenance import AzureMaintenanceClient
            mc = AzureMaintenanceClient(db=self._db)
            health_events = mc.list_resource_health_events(subscription_id, filter_planned=True)
            # Build a fast lookup: resource_id -> health event
            health_by_rid = {}
            for e in health_events:
                impacted = (e.get("properties") or {}).get("impactedResource") or ""
                if impacted:
                    health_by_rid[impacted.lower()] = e

            def attach_vm_maint(vm: dict) -> dict:
                rg = _rg_from_id(vm.get("id", ""))
                name = vm.get("name", "")
                if rg and name:
                    vm["maintenance_status"] = mc.get_vm_maintenance_status(
                        subscription_id, rg, name
                    )
                event = health_by_rid.get((vm.get("id") or "").lower())
                if event:
                    vm["planned_health_event"] = {
                        "title": (event.get("properties") or {}).get("title"),
                        "impact_start": (event.get("properties") or {}).get("impactStartTime"),
                    }
                return vm

            workers = min(len(vms), 4) if vms else 1
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="vm_maint"
            ) as pool:
                vms = list(pool.map(attach_vm_maint, vms))

        log.info("list_vms", count=len(vms), instance_view=include_instance_view, maintenance=include_maintenance)
        return vms

    def list_vm_scale_sets(
        self,
        subscription_id: str,
        include_maintenance: bool = False,
    ) -> list:
        """List VMSS. Optionally attach maintenance and upgrade-policy status."""
        url = (
            f"{BASE}/subscriptions/{subscription_id}"
            f"/providers/Microsoft.Compute/virtualMachineScaleSets"
        )
        items = get_all_pages(url, self._headers(), {"api-version": _COMPUTE_VMSS_API_VERSION})

        if include_maintenance:
            from app.azure_maintenance import AzureMaintenanceClient
            mc = AzureMaintenanceClient(db=self._db)

            def attach_vmss_maint(vmss: dict) -> dict:
                rg = _rg_from_id(vmss.get("id", ""))
                name = vmss.get("name", "")
                if rg and name:
                    vmss["maintenance_status"] = mc.get_vmss_maintenance_status(
                        subscription_id, rg, name
                    )
                return vmss

            workers = min(len(items), 4) if items else 1
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="vmss_maint"
            ) as pool:
                items = list(pool.map(attach_vmss_maint, items))

        log.info("list_vm_scale_sets", count=len(items), maintenance=include_maintenance)
        return items

    def get_vm_scale_set(self, subscription_id: str, resource_group: str, vmss_name: str) -> dict:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/virtualMachineScaleSets/{vmss_name}"
        )
        return _get(url, self._headers(), {"api-version": _COMPUTE_VMSS_API_VERSION})

    def list_vm_scale_set_vms(self, subscription_id, resource_group, vmss_name) -> list:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/virtualMachineScaleSets/{vmss_name}/virtualMachines"
        )
        items = get_all_pages(url, self._headers(), {"api-version": _COMPUTE_VMSS_API_VERSION})
        log.info("list_vm_scale_set_vms", vmss=vmss_name, count=len(items))
        return items

    def get_vm_scale_set_vm_instance_view(self, subscription_id, resource_group, vmss_name, instance_id) -> dict:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/virtualMachineScaleSets/{vmss_name}"
            f"/virtualMachines/{instance_id}/instanceView"
        )
        return _get(url, self._headers(), {"api-version": _COMPUTE_VMSS_API_VERSION})

    def _attach_instance_views(self, subscription_id: str, vms: list[dict]) -> list[dict]:
        if not vms:
            return vms

        def enrich(vm: dict) -> dict:
            rg = _rg_from_id(vm.get("id", ""))
            name = vm.get("name", "")
            if not rg or not name:
                return vm
            iv_url = (
                f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{rg}"
                f"/providers/Microsoft.Compute/virtualMachines/{name}/instanceView"
            )
            try:
                iv = _get(iv_url, self._headers(), {"api-version": _COMPUTE_VM_API_VERSION})
                vm.setdefault("properties", {})["instanceView"] = iv
            except Exception as exc:
                log.warning("vm.instanceView.failed", vm=name, error=str(exc))
            return vm

        workers = 1 if arm_patient_active() else min(_VM_INSTANCE_VIEW_WORKERS, len(vms))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(enrich, vms))

    def get_vm(self, subscription_id, resource_group, vm_name, *, expand="instanceView") -> dict:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/virtualMachines/{vm_name}"
        )
        params: dict = {"api-version": _COMPUTE_VM_API_VERSION}
        if expand:
            params["$expand"] = expand
        return _get(url, self._headers(), params)

    def list_vm_skus(self, subscription_id: str, location: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute/skus"
        params = {
            "api-version": "2021-07-01",
            "$filter": f"location eq '{location}'",
            "includeExtendedLocations": "false",
        }
        skus = get_all_pages(url, self._headers(), params)
        return [s for s in skus if s.get("resourceType") == "virtualMachines"]

    def list_vm_sizes(self, subscription_id: str, location: str) -> list:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute"
            f"/locations/{location}/vmSizes"
        )
        data = _get(url, self._headers(), {"api-version": _COMPUTE_VMSS_API_VERSION})
        return data.get("value", [])

    def list_disks(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute/disks"
        return get_all_pages(url, self._headers(), {"api-version": _COMPUTE_DISK_API_VERSION})

    def get_disk(self, subscription_id, resource_group, disk_name) -> dict:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/disks/{disk_name}"
        )
        return _get(url, self._headers(), {"api-version": _COMPUTE_DISK_API_VERSION})

    def list_snapshots(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute/snapshots"
        return get_all_pages(url, self._headers(), {"api-version": _COMPUTE_SNAPSHOT_API_VERSION})

    def get_snapshot(self, subscription_id, resource_group, snapshot_name) -> dict:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/snapshots/{snapshot_name}"
        )
        return _get(url, self._headers(), {"api-version": _COMPUTE_SNAPSHOT_API_VERSION})

    def list_availability_sets(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute/availabilitySets"
        return get_all_pages(url, self._headers(), {"api-version": _COMPUTE_VMSS_API_VERSION})

    # ------------------------------------------------------------------ #
    #  Kubernetes / AKS                                                   #
    # ------------------------------------------------------------------ #
    def list_aks_clusters(
        self,
        subscription_id: str,
        include_maintenance: bool = False,
    ) -> list:
        """List AKS clusters. Optionally attach maintenance configuration status."""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.ContainerService/managedClusters"
        clusters = get_all_pages(url, self._headers(), {"api-version": _AKS_API_VERSION})

        if include_maintenance:
            from app.azure_maintenance import AzureMaintenanceClient
            mc = AzureMaintenanceClient(db=self._db)

            def attach_aks_maint(cluster: dict) -> dict:
                rg = _rg_from_id(cluster.get("id", ""))
                name = cluster.get("name", "")
                if rg and name:
                    configs = mc.list_aks_maintenance_configurations(
                        subscription_id, rg, name
                    )
                    cluster["maintenance_configurations"] = configs
                    cluster["has_maintenance_config"] = bool(configs)
                return cluster

            workers = min(len(clusters), 4) if clusters else 1
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="aks_maint"
            ) as pool:
                clusters = list(pool.map(attach_aks_maint, clusters))

        return clusters

    def get_aks_cluster(self, subscription_id, resource_group, cluster_name) -> dict:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ContainerService/managedClusters/{cluster_name}"
        )
        return _get(url, self._headers(), {"api-version": _AKS_API_VERSION})

    def list_aks_node_pools(self, subscription_id, resource_group, cluster_name) -> list:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ContainerService/managedClusters/{cluster_name}/agentPools"
        )
        data = _get(url, self._headers(), {"api-version": _AKS_API_VERSION})
        return data.get("value", [])

    def list_aks_upgrades(self, subscription_id, resource_group, cluster_name) -> dict:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ContainerService/managedClusters/{cluster_name}/upgradeProfiles/default"
        )
        return _get(url, self._headers(), {"api-version": _AKS_API_VERSION})

    def list_aks_kubernetes_versions(self, subscription_id: str, location: str) -> dict:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.ContainerService"
            f"/locations/{location}/kubernetesVersions"
        )
        return _get(url, self._headers(), {"api-version": _AKS_API_VERSION})

    def get_resource_health_overview(self, subscription_id: str) -> dict:
        """Fetch a high-level resource health + planned maintenance summary.
        Returns counts of planned events and impacted resource IDs.
        """
        from app.azure_maintenance import AzureMaintenanceClient
        mc = AzureMaintenanceClient(db=self._db)
        events = mc.list_resource_health_events(subscription_id, filter_planned=True)
        impacted = []
        for e in events:
            ir = (e.get("properties") or {}).get("impactedResource") or ""
            if ir:
                impacted.append(ir)
        return {
            "planned_maintenance_event_count": len(events),
            "impacted_resource_ids": impacted,
            "events": [
                {
                    "title": (e.get("properties") or {}).get("title"),
                    "impact_start": (e.get("properties") or {}).get("impactStartTime"),
                    "impact_mitigation": (e.get("properties") or {}).get("impactMitigationTime"),
                    "impacted_resource": (e.get("properties") or {}).get("impactedResource"),
                }
                for e in events
            ],
        }

    # ------------------------------------------------------------------ #
    #  Storage                                                            #
    # ------------------------------------------------------------------ #
    def list_storage_accounts(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Storage/storageAccounts"
        return get_all_pages(url, self._headers(), {"api-version": _STORAGE_ACCOUNT_API_VERSION})

    def get_storage_account(self, subscription_id, resource_group, account_name) -> dict:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Storage/storageAccounts/{account_name}"
        )
        return _get(url, self._headers(), {"api-version": _STORAGE_ACCOUNT_API_VERSION})

    # ------------------------------------------------------------------ #
    #  App Services                                                       #
    # ------------------------------------------------------------------ #
    def list_app_services(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Web/sites"
        return get_all_pages(url, self._headers(), {"api-version": _WEB_SITES_API_VERSION})

    def list_app_service_plans(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Web/serverfarms"
        return get_all_pages(url, self._headers(), {"api-version": _WEB_SERVERFARMS_API_VERSION})

    # ------------------------------------------------------------------ #
    #  Databases                                                          #
    # ------------------------------------------------------------------ #
    def list_sql_servers(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Sql/servers"
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.sql/servers"]})

    def list_sql_databases(self, subscription_id, resource_group, server_name) -> list:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Sql/servers/{server_name}/databases"
        )
        data = _get(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.sql/servers"]})
        return data.get("value", [])

    def list_postgresql_flexible(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.DBforPostgreSQL/flexibleServers"
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.dbforpostgresql/flexibleservers"]})

    def list_mysql_flexible(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.DBforMySQL/flexibleServers"
        return get_all_pages(url, self._headers(), {"api-version": "2023-12-30"})

    def list_cosmosdb(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.DocumentDB/databaseAccounts"
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.documentdb/databaseaccounts"]})

    # ------------------------------------------------------------------ #
    #  Networking                                                         #
    # ------------------------------------------------------------------ #
    def list_public_ips(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/publicIPAddresses"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_vnets(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/virtualNetworks"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_load_balancers(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/loadBalancers"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_application_gateways(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/applicationGateways"
        return get_all_pages(url, self._headers(), {"api-version": _APPLICATION_GATEWAY_API_VERSION})

    def get_application_gateway(self, subscription_id, resource_group, gateway_name, db=None) -> dict:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Network/applicationGateways/{gateway_name}"
        )
        return _get(url, self._headers(db), {"api-version": _APPLICATION_GATEWAY_API_VERSION})

    def get_arm_resource(self, resource_id: str, *, api_version: str | None = None) -> dict:
        from app.arm_resource_enrichment import api_version_for_resource_id
        rid = (resource_id or "").strip()
        if not rid.startswith("/"):
            rid = f"/{rid}"
        version = api_version or api_version_for_resource_id(rid)
        return _get(f"{BASE}{rid}", self._headers(), {"api-version": version})

    def list_network_security_groups(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/networkSecurityGroups"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_network_interfaces(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/networkInterfaces"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_nat_gateways(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/natGateways"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_private_endpoints(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/privateEndpoints"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_private_link_services(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/privateLinkServices"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_private_dns_zones(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/privateDnsZones"
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.network/privatednszones"]})

    def list_redis_caches(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Cache/redis"
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.cache/redis"]})

    def list_keyvaults(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.KeyVault/vaults"
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.keyvault/vaults"]})

    def list_container_registries(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.ContainerRegistry/registries"
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.containerregistry/registries"]})

    def list_acr_replications(self, subscription_id, resource_group, registry_name) -> list:
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ContainerRegistry/registries/{registry_name}/replications"
        )
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.containerregistry/registries"]})

    # ------------------------------------------------------------------ #
    #  Monitor / Metrics                                                  #
    # ------------------------------------------------------------------ #
    def get_resource_metrics(self, resource_id, metric_names, timespan="PT1H", interval="PT5M", aggregation="Average", db=None) -> dict:
        rid = (resource_id or "").strip()
        if rid and not rid.startswith("/"):
            rid = f"/{rid}"
        url = f"{BASE}{rid}/providers/Microsoft.Insights/metrics"
        params = {
            "api-version": MONITOR_METRICS_API_VERSION,
            "metricnames": ",".join(metric_names),
            "timespan": timespan,
            "interval": interval,
            "aggregation": aggregation,
        }
        return _get(url, self._headers(db), params)

    def get_vm_cpu_metrics(self, resource_id: str, timespan: str = "PT1H", db=None) -> dict:
        return self.get_resource_metrics(
            resource_id,
            metric_names=["Percentage CPU", "Available Memory Bytes"],
            timespan=timespan,
            db=db,
        )

    def patch_resource_tags(self, resource_id: str, tags: dict, *, db=None) -> dict:
        from app.arm_api_versions import api_version_for_arm_type
        rid = (resource_id or "").strip()
        if not rid.startswith("/"):
            rid = f"/{rid}"
        parts = [p for p in rid.split("/") if p]
        arm_type = ""
        try:
            providers_idx = [p.lower() for p in parts].index("providers")
            arm_type = f"{parts[providers_idx + 1]}/{parts[providers_idx + 2]}".lower()
        except (ValueError, IndexError):
            pass
        api_version = api_version_for_arm_type(arm_type)
        return _patch(
            f"{BASE}{rid}",
            self._headers(db),
            params={"api-version": api_version},
            payload={"tags": tags or {}},
        )

"""Azure Resource Manager — typed resource fetchers using official API versions.

All API versions sourced from:
https://learn.microsoft.com/en-us/rest/api/azure/
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

# https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines/get
_COMPUTE_VM_API_VERSION = ARM_GET_API_VERSIONS["microsoft.compute/virtualmachines"]
_COMPUTE_VMSS_API_VERSION = ARM_GET_API_VERSIONS["microsoft.compute/virtualmachinescalesets"]
# https://learn.microsoft.com/en-us/rest/api/compute/disks/get
_COMPUTE_DISK_API_VERSION = ARM_GET_API_VERSIONS["microsoft.compute/disks"]
# https://learn.microsoft.com/en-us/rest/api/compute/snapshots/get
_COMPUTE_SNAPSHOT_API_VERSION = ARM_GET_API_VERSIONS["microsoft.compute/snapshots"]
# https://learn.microsoft.com/en-us/rest/api/application-gateway/application-gateways/get
_APPLICATION_GATEWAY_API_VERSION = ARM_GET_API_VERSIONS["microsoft.network/applicationgateways"]
# https://learn.microsoft.com/en-us/rest/api/storagerp/storage-accounts/get-properties
_STORAGE_ACCOUNT_API_VERSION = ARM_GET_API_VERSIONS["microsoft.storage/storageaccounts"]
_AKS_API_VERSION = ARM_GET_API_VERSIONS["microsoft.containerservice/managedclusters"]
_NETWORK_API_VERSION = ARM_GET_API_VERSIONS["microsoft.network/publicipaddresses"]
_WEB_SITES_API_VERSION = ARM_GET_API_VERSIONS["microsoft.web/sites"]
_WEB_SERVERFARMS_API_VERSION = ARM_GET_API_VERSIONS["microsoft.web/serverfarms"]

_VM_INSTANCE_VIEW_WORKERS = max(1, int(os.getenv("ARM_VM_INSTANCE_VIEW_WORKERS", "4")))


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
    #  Generic resource list (ARM resources API)                          #
    # ------------------------------------------------------------------ #
    def list_resources(self, subscription_id: str, resource_type: str | None = None) -> list:
        """List all resources or filter by type.
        API: https://learn.microsoft.com/en-us/rest/api/resources/resources/list
        """
        params = {"api-version": RESOURCES_LIST_API_VERSION}
        if resource_type:
            params["$filter"] = f"resourceType eq '{resource_type}'"
        url = f"{BASE}/subscriptions/{subscription_id}/resources"
        return get_all_pages(url, self._headers(), params)

    def list_resource_groups(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/resources/resource-groups/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/resourcegroups"
        return get_all_pages(url, self._headers(), {"api-version": RESOURCES_LIST_API_VERSION})

    def list_subscriptions(self) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/resources/subscriptions/list"""
        url = f"{BASE}/subscriptions"
        return get_all_pages(url, self._headers(), {"api-version": SUBSCRIPTIONS_LIST_API_VERSION})

    # ------------------------------------------------------------------ #
    #  Compute                                                             #
    # ------------------------------------------------------------------ #
    _TRANSIENT_ARM = {500, 502, 503, 504}

    def _list_vms_compute(self, subscription_id: str, *, expand_instance_view: bool = False) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute/virtualMachines"
        params = {"api-version": _COMPUTE_VM_API_VERSION}
        if expand_instance_view:
            params = {**params, "$expand": "instanceView"}
        return get_all_pages(url, self._headers(), params)

    def _list_vms_with_fallback(self, subscription_id: str) -> list:
        """Compute provider list, falling back to the generic Resources API on 5xx."""
        try:
            return self._list_vms_compute(subscription_id)
        except AzureAPIError as exc:
            if exc.status not in self._TRANSIENT_ARM:
                raise
            log.warning(
                "list_vms.compute_provider_failed",
                status=exc.status,
                fallback="resources_api",
            )
            return self.list_resources(subscription_id, "Microsoft.Compute/virtualMachines")

    def list_vms(self, subscription_id: str, include_instance_view: bool = True) -> list:
        """List VMs. Power state comes from instanceView when requested.

        Subscription-wide ``$expand=instanceView`` frequently returns 502 from the
        Compute resource provider on large subscriptions. We try expand first; on
        transient failure we list without expand and fetch instanceView per VM
        with bounded concurrency. If the Compute list endpoint keeps failing, we
        fall back to the generic Resources API (same inventory, thinner properties).
        """
        if not include_instance_view:
            vms = self._list_vms_with_fallback(subscription_id)
            vms = filter_standalone_vms(vms)
            log.info("list_vms", count=len(vms), instance_view=False)
            return vms

        # Subscription-wide $expand=instanceView frequently 502s on the Compute
        # provider and then burns the full retry budget (minutes of backoff)
        # before falling back. Skip it and go straight to a plain list + bounded
        # per-VM instanceView fetches, which are paced by the global rate limiter.
        vms = self._list_vms_with_fallback(subscription_id)
        vms = filter_standalone_vms(vms)
        vms = self._attach_instance_views(subscription_id, vms)
        log.info("list_vms", count=len(vms), instance_view="per_vm")
        return vms

    def list_vm_scale_sets(self, subscription_id: str) -> list:
        """List virtual machine scale sets (not individual instance VMs).
        API: https://learn.microsoft.com/en-us/rest/api/compute/virtual-machine-scale-sets/list-all
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}"
            f"/providers/Microsoft.Compute/virtualMachineScaleSets"
        )
        items = get_all_pages(url, self._headers(), {"api-version": _COMPUTE_VMSS_API_VERSION})
        log.info("list_vm_scale_sets", count=len(items))
        return items

    def get_vm_scale_set(self, subscription_id: str, resource_group: str, vmss_name: str) -> dict:
        """API: https://learn.microsoft.com/en-us/rest/api/compute/virtual-machine-scale-sets/get"""
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/virtualMachineScaleSets/{vmss_name}"
        )
        return _get(url, self._headers(), {"api-version": _COMPUTE_VMSS_API_VERSION})

    def list_vm_scale_set_vms(
        self,
        subscription_id: str,
        resource_group: str,
        vmss_name: str,
    ) -> list:
        """List VMSS instances (not full instanceView).
        API: https://learn.microsoft.com/en-us/rest/api/compute/virtual-machine-scale-set-vms/list
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/virtualMachineScaleSets/{vmss_name}/virtualMachines"
        )
        items = get_all_pages(url, self._headers(), {"api-version": _COMPUTE_VMSS_API_VERSION})
        log.info("list_vm_scale_set_vms", vmss=vmss_name, count=len(items))
        return items

    def get_vm_scale_set_vm_instance_view(
        self,
        subscription_id: str,
        resource_group: str,
        vmss_name: str,
        instance_id: str,
    ) -> dict:
        """InstanceView for one VMSS instance (includes provisioning time).
        API: https://learn.microsoft.com/en-us/rest/api/compute/virtual-machine-scale-set-vms/get-instance-view
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/virtualMachineScaleSets/{vmss_name}"
            f"/virtualMachines/{instance_id}/instanceView"
        )
        return _get(url, self._headers(), {"api-version": _COMPUTE_VMSS_API_VERSION})

    def _attach_instance_views(self, subscription_id: str, vms: list[dict]) -> list[dict]:
        """Fetch instanceView per VM (lighter than subscription-wide expand)."""
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

    def get_vm(
        self,
        subscription_id: str,
        resource_group: str,
        vm_name: str,
        *,
        expand: str = "instanceView",
    ) -> dict:
        """Get a single VM (model + optional instance view).
        API: https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines/get
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/virtualMachines/{vm_name}"
        )
        params: dict[str, str] = {"api-version": _COMPUTE_VM_API_VERSION}
        if expand:
            params["$expand"] = expand
        return _get(url, self._headers(), params)

    def list_vm_skus(self, subscription_id: str, location: str) -> list:
        """List all VM SKUs available in a location with capability details.
        API: https://learn.microsoft.com/en-us/rest/api/compute/resource-skus/list
        Returns: vCPUs, memory, max data disks, accelerated networking, premium storage, etc.
        """
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute/skus"
        params = {
            "api-version": "2021-07-01",
            "$filter": f"location eq '{location}'",
            "includeExtendedLocations": "false",
        }
        skus = get_all_pages(url, self._headers(), params)
        # Filter to virtualMachines only
        vm_skus = [s for s in skus if s.get("resourceType") == "virtualMachines"]
        log.info("list_vm_skus", location=location, count=len(vm_skus))
        return vm_skus

    def list_vm_sizes(self, subscription_id: str, location: str) -> list:
        """List VM sizes via Compute/locations API (legacy but still valid).
        API: https://learn.microsoft.com/en-us/rest/api/compute/virtual-machine-sizes/list
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute"
            f"/locations/{location}/vmSizes"
        )
        data = _get(url, self._headers(), {"api-version": _COMPUTE_VMSS_API_VERSION})
        return data.get("value", [])

    def list_disks(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/compute/disks/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute/disks"
        return get_all_pages(url, self._headers(), {"api-version": _COMPUTE_DISK_API_VERSION})

    def get_disk(self, subscription_id: str, resource_group: str, disk_name: str) -> dict:
        """API: https://learn.microsoft.com/en-us/rest/api/compute/disks/get"""
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/disks/{disk_name}"
        )
        return _get(url, self._headers(), {"api-version": _COMPUTE_DISK_API_VERSION})

    def list_snapshots(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/compute/snapshots/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute/snapshots"
        return get_all_pages(url, self._headers(), {"api-version": _COMPUTE_SNAPSHOT_API_VERSION})

    def get_snapshot(self, subscription_id: str, resource_group: str, snapshot_name: str) -> dict:
        """API: https://learn.microsoft.com/en-us/rest/api/compute/snapshots/get"""
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
    def list_aks_clusters(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/aks/managed-clusters/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.ContainerService/managedClusters"
        return get_all_pages(url, self._headers(), {"api-version": _AKS_API_VERSION})

    def get_aks_cluster(self, subscription_id: str, resource_group: str, cluster_name: str) -> dict:
        """Get AKS cluster with full node pool and addon details."""
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ContainerService/managedClusters/{cluster_name}"
        )
        return _get(url, self._headers(), {"api-version": _AKS_API_VERSION})

    def list_aks_node_pools(self, subscription_id: str, resource_group: str, cluster_name: str) -> list:
        """List all node pools in an AKS cluster.
        API: https://learn.microsoft.com/en-us/rest/api/aks/agent-pools/list
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ContainerService/managedClusters/{cluster_name}/agentPools"
        )
        data = _get(url, self._headers(), {"api-version": _AKS_API_VERSION})
        return data.get("value", [])

    def list_aks_upgrades(self, subscription_id: str, resource_group: str, cluster_name: str) -> dict:
        """Available Kubernetes upgrades for a cluster."""
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ContainerService/managedClusters/{cluster_name}/upgradeProfiles/default"
        )
        return _get(url, self._headers(), {"api-version": _AKS_API_VERSION})

    def list_aks_kubernetes_versions(self, subscription_id: str, location: str) -> dict:
        """Supported Kubernetes versions for an Azure region.

        API: https://learn.microsoft.com/en-us/rest/api/aks/managed-clusters/list-kubernetes-versions
        """
        loc = (location or "").strip()
        url = (
            f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.ContainerService"
            f"/locations/{loc}/kubernetesVersions"
        )
        return _get(url, self._headers(), {"api-version": _AKS_API_VERSION})

    # ------------------------------------------------------------------ #
    #  Storage                                                            #
    # ------------------------------------------------------------------ #
    def list_storage_accounts(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/storagerp/storage-accounts/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Storage/storageAccounts"
        return get_all_pages(url, self._headers(), {"api-version": _STORAGE_ACCOUNT_API_VERSION})

    def get_storage_account(self, subscription_id: str, resource_group: str, account_name: str) -> dict:
        """API: https://learn.microsoft.com/en-us/rest/api/storagerp/storage-accounts/get-properties"""
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Storage/storageAccounts/{account_name}"
        )
        return _get(url, self._headers(), {"api-version": _STORAGE_ACCOUNT_API_VERSION})

    # ------------------------------------------------------------------ #
    #  App Services / Web                                                 #
    # ------------------------------------------------------------------ #
    def list_app_services(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/appservice/web-apps/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Web/sites"
        return get_all_pages(url, self._headers(), {"api-version": _WEB_SITES_API_VERSION})

    def list_app_service_plans(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/appservice/app-service-plans/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Web/serverfarms"
        return get_all_pages(url, self._headers(), {"api-version": _WEB_SERVERFARMS_API_VERSION})

    # ------------------------------------------------------------------ #
    #  Databases                                                          #
    # ------------------------------------------------------------------ #
    def list_sql_servers(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/sql/servers/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Sql/servers"
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.sql/servers"]})

    def list_sql_databases(self, subscription_id: str, resource_group: str, server_name: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/sql/databases/list-by-server"""
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Sql/servers/{server_name}/databases"
        )
        data = _get(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.sql/servers"]})
        return data.get("value", [])

    def list_postgresql_flexible(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/postgresql/flexibleservers/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.DBforPostgreSQL/flexibleServers"
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.dbforpostgresql/flexibleservers"]})

    def list_mysql_flexible(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/mysql/flexibleservers/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.DBforMySQL/flexibleServers"
        return get_all_pages(url, self._headers(), {"api-version": "2023-12-30"})

    def list_cosmosdb(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/cosmos-db-resource-provider/database-accounts/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.DocumentDB/databaseAccounts"
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.documentdb/databaseaccounts"]})

    # ------------------------------------------------------------------ #
    #  Networking                                                         #
    # ------------------------------------------------------------------ #
    def list_public_ips(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/virtualnetwork/public-ip-addresses/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/publicIPAddresses"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_vnets(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/virtualnetwork/virtual-networks/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/virtualNetworks"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_load_balancers(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/load-balancer/load-balancers/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/loadBalancers"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_application_gateways(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/application-gateway/application-gateways/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/applicationGateways"
        return get_all_pages(url, self._headers(), {"api-version": _APPLICATION_GATEWAY_API_VERSION})

    def get_application_gateway(
        self,
        subscription_id: str,
        resource_group: str,
        gateway_name: str,
        db=None,
    ) -> dict:
        """API: https://learn.microsoft.com/en-us/rest/api/application-gateway/application-gateways/get"""
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Network/applicationGateways/{gateway_name}"
        )
        return _get(url, self._headers(db), {"api-version": _APPLICATION_GATEWAY_API_VERSION})

    def get_arm_resource(self, resource_id: str, *, api_version: str | None = None) -> dict:
        """GET any ARM resource by ID with the correct provider api-version."""
        from app.arm_resource_enrichment import api_version_for_resource_id

        rid = (resource_id or "").strip()
        if not rid.startswith("/"):
            rid = f"/{rid}"
        version = api_version or api_version_for_resource_id(rid)
        url = f"{BASE}{rid}"
        return _get(url, self._headers(), {"api-version": version})

    def list_network_security_groups(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/virtualnetwork/network-security-groups/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/networkSecurityGroups"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_network_interfaces(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/virtualnetwork/network-interfaces/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/networkInterfaces"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_nat_gateways(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/virtualnetwork/nat-gateways/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/natGateways"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_private_endpoints(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/virtualnetwork/private-endpoints/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/privateEndpoints"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_private_link_services(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/virtualnetwork/private-link-services/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/privateLinkServices"
        return get_all_pages(url, self._headers(), {"api-version": _NETWORK_API_VERSION})

    def list_private_dns_zones(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/dns/privatednszones/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/privateDnsZones"
        return get_all_pages(
            url,
            self._headers(),
            {"api-version": ARM_GET_API_VERSIONS["microsoft.network/privatednszones"]},
        )

    def list_redis_caches(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/redis/redis/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Cache/redis"
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.cache/redis"]})

    # ------------------------------------------------------------------ #
    #  Security                                                           #
    # ------------------------------------------------------------------ #
    def list_keyvaults(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/keyvault/keyvault/vaults/list-by-subscription"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.KeyVault/vaults"
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.keyvault/vaults"]})

    # ------------------------------------------------------------------ #
    #  Container Registry                                                 #
    # ------------------------------------------------------------------ #
    def list_container_registries(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/containerregistry/registries/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.ContainerRegistry/registries"
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.containerregistry/registries"]})

    def list_acr_replications(self, subscription_id: str, resource_group: str, registry_name: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/containerregistry/replications/list"""
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ContainerRegistry/registries/{registry_name}/replications"
        )
        return get_all_pages(url, self._headers(), {"api-version": ARM_GET_API_VERSIONS["microsoft.containerregistry/registries"]})

    # ------------------------------------------------------------------ #
    #  Monitor / Metrics                                                  #
    # ------------------------------------------------------------------ #
    def get_resource_metrics(
        self,
        resource_id: str,
        metric_names: list[str],
        timespan: str = "PT1H",
        interval: str = "PT5M",
        aggregation: str = "Average",
        db=None,
    ) -> dict:
        """Get Azure Monitor metrics for any resource.
        API: https://learn.microsoft.com/en-us/rest/api/monitor/metrics/list
        """
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
        """Convenience: CPU % for a VM."""
        return self.get_resource_metrics(
            resource_id,
            metric_names=["Percentage CPU", "Available Memory Bytes"],
            timespan=timespan,
            db=db,
        )

    def patch_resource_tags(self, resource_id: str, tags: dict, *, db=None) -> dict:
        """Update Azure resource tags via ARM PATCH."""
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
        url = f"{BASE}{rid}"
        return _patch(
            url,
            self._headers(db),
            params={"api-version": api_version},
            payload={"tags": tags or {}},
        )

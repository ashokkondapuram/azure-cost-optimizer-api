"""Azure Resource Manager — typed resource fetchers using official API versions.

All API versions sourced from:
https://learn.microsoft.com/en-us/rest/api/azure/
"""
import structlog
from app.auth import auth_headers
from app.http_client import _get, get_all_pages, BASE

log = structlog.get_logger()


class AzureResourcesClient:

    # ------------------------------------------------------------------ #
    #  Generic resource list (ARM resources API)                          #
    # ------------------------------------------------------------------ #
    def list_resources(self, subscription_id: str, resource_type: str | None = None) -> list:
        """List all resources or filter by type.
        API: https://learn.microsoft.com/en-us/rest/api/resources/resources/list
        """
        params = {"api-version": "2024-03-01"}
        if resource_type:
            params["$filter"] = f"resourceType eq '{resource_type}'"
        url = f"{BASE}/subscriptions/{subscription_id}/resources"
        return get_all_pages(url, auth_headers(), params)

    def list_resource_groups(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/resources/resource-groups/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/resourcegroups"
        return get_all_pages(url, auth_headers(), {"api-version": "2024-03-01"})

    def list_subscriptions(self) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/resources/subscriptions/list"""
        url = f"{BASE}/subscriptions"
        return get_all_pages(url, auth_headers(), {"api-version": "2022-12-01"})

    # ------------------------------------------------------------------ #
    #  Compute                                                             #
    # ------------------------------------------------------------------ #
    def list_vms(self, subscription_id: str) -> list:
        """List VMs with full details including hardware profile, OS, networking.
        API: https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines/list-all
        API version: 2024-03-01 (latest stable)
        """
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute/virtualMachines"
        vms = get_all_pages(url, auth_headers(), {"api-version": "2024-03-01", "$expand": "instanceView"})
        log.info("list_vms", count=len(vms))
        return vms

    def get_vm(self, subscription_id: str, resource_group: str, vm_name: str) -> dict:
        """Get a single VM with full instance view.
        API: https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines/get
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/virtualMachines/{vm_name}"
        )
        return _get(url, auth_headers(), {
            "api-version": "2024-03-01",
            "$expand": "instanceView,userData",
        })

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
        skus = get_all_pages(url, auth_headers(), params)
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
        data = _get(url, auth_headers(), {"api-version": "2024-03-01"})
        return data.get("value", [])

    def list_disks(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/compute/disks/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute/disks"
        return get_all_pages(url, auth_headers(), {"api-version": "2023-10-02"})

    def list_snapshots(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/compute/snapshots/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute/snapshots"
        return get_all_pages(url, auth_headers(), {"api-version": "2023-10-02"})

    def list_availability_sets(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Compute/availabilitySets"
        return get_all_pages(url, auth_headers(), {"api-version": "2024-03-01"})

    # ------------------------------------------------------------------ #
    #  Kubernetes / AKS                                                   #
    # ------------------------------------------------------------------ #
    def list_aks_clusters(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/aks/managed-clusters/list
        API version: 2024-02-01 (latest stable)
        """
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.ContainerService/managedClusters"
        return get_all_pages(url, auth_headers(), {"api-version": "2024-02-01"})

    def get_aks_cluster(self, subscription_id: str, resource_group: str, cluster_name: str) -> dict:
        """Get AKS cluster with full node pool and addon details."""
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ContainerService/managedClusters/{cluster_name}"
        )
        return _get(url, auth_headers(), {"api-version": "2024-02-01"})

    def list_aks_node_pools(self, subscription_id: str, resource_group: str, cluster_name: str) -> list:
        """List all node pools in an AKS cluster.
        API: https://learn.microsoft.com/en-us/rest/api/aks/agent-pools/list
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ContainerService/managedClusters/{cluster_name}/agentPools"
        )
        data = _get(url, auth_headers(), {"api-version": "2024-02-01"})
        return data.get("value", [])

    def list_aks_upgrades(self, subscription_id: str, resource_group: str, cluster_name: str) -> dict:
        """Available Kubernetes upgrades for a cluster."""
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ContainerService/managedClusters/{cluster_name}/upgradeProfiles/default"
        )
        return _get(url, auth_headers(), {"api-version": "2024-02-01"})

    # ------------------------------------------------------------------ #
    #  Storage                                                            #
    # ------------------------------------------------------------------ #
    def list_storage_accounts(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/storagerp/storage-accounts/list
        API version: 2023-05-01 (latest stable)
        """
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Storage/storageAccounts"
        return get_all_pages(url, auth_headers(), {"api-version": "2023-05-01"})

    # ------------------------------------------------------------------ #
    #  App Services / Web                                                 #
    # ------------------------------------------------------------------ #
    def list_app_services(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/appservice/web-apps/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Web/sites"
        return get_all_pages(url, auth_headers(), {"api-version": "2023-12-01"})

    def list_app_service_plans(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/appservice/app-service-plans/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Web/serverfarms"
        return get_all_pages(url, auth_headers(), {"api-version": "2023-12-01"})

    # ------------------------------------------------------------------ #
    #  Databases                                                          #
    # ------------------------------------------------------------------ #
    def list_sql_servers(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/sql/servers/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Sql/servers"
        return get_all_pages(url, auth_headers(), {"api-version": "2023-08-01-preview"})

    def list_sql_databases(self, subscription_id: str, resource_group: str, server_name: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/sql/databases/list-by-server"""
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Sql/servers/{server_name}/databases"
        )
        data = _get(url, auth_headers(), {"api-version": "2023-08-01-preview"})
        return data.get("value", [])

    def list_postgresql_flexible(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/postgresql/flexibleservers/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.DBforPostgreSQL/flexibleServers"
        return get_all_pages(url, auth_headers(), {"api-version": "2023-12-01-preview"})

    def list_mysql_flexible(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/mysql/flexibleservers/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.DBforMySQL/flexibleServers"
        return get_all_pages(url, auth_headers(), {"api-version": "2023-12-30"})

    def list_cosmosdb(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/cosmos-db-resource-provider/database-accounts/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.DocumentDB/databaseAccounts"
        return get_all_pages(url, auth_headers(), {"api-version": "2024-05-15"})

    # ------------------------------------------------------------------ #
    #  Networking                                                         #
    # ------------------------------------------------------------------ #
    def list_public_ips(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/virtualnetwork/public-ip-addresses/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/publicIPAddresses"
        return get_all_pages(url, auth_headers(), {"api-version": "2024-01-01"})

    def list_vnets(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/virtualnetwork/virtual-networks/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/virtualNetworks"
        return get_all_pages(url, auth_headers(), {"api-version": "2024-01-01"})

    def list_load_balancers(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/load-balancer/load-balancers/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/loadBalancers"
        return get_all_pages(url, auth_headers(), {"api-version": "2024-01-01"})

    def list_application_gateways(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/application-gateway/application-gateways/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/applicationGateways"
        return get_all_pages(url, auth_headers(), {"api-version": "2024-01-01"})

    def list_network_security_groups(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/virtualnetwork/network-security-groups/list-all"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/networkSecurityGroups"
        return get_all_pages(url, auth_headers(), {"api-version": "2024-01-01"})

    def list_network_interfaces(self, subscription_id: str) -> list:
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.Network/networkInterfaces"
        return get_all_pages(url, auth_headers(), {"api-version": "2024-01-01"})

    # ------------------------------------------------------------------ #
    #  Security                                                           #
    # ------------------------------------------------------------------ #
    def list_keyvaults(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/keyvault/keyvault/vaults/list-by-subscription"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.KeyVault/vaults"
        return get_all_pages(url, auth_headers(), {"api-version": "2023-07-01"})

    # ------------------------------------------------------------------ #
    #  Container Registry                                                 #
    # ------------------------------------------------------------------ #
    def list_container_registries(self, subscription_id: str) -> list:
        """API: https://learn.microsoft.com/en-us/rest/api/containerregistry/registries/list"""
        url = f"{BASE}/subscriptions/{subscription_id}/providers/Microsoft.ContainerRegistry/registries"
        return get_all_pages(url, auth_headers(), {"api-version": "2023-11-01-preview"})

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
    ) -> dict:
        """Get Azure Monitor metrics for any resource.
        API: https://learn.microsoft.com/en-us/rest/api/monitor/metrics/list
        """
        url = f"{BASE}{resource_id}/providers/Microsoft.Insights/metrics"
        params = {
            "api-version": "2023-10-01",
            "metricnames": ",".join(metric_names),
            "timespan": timespan,
            "interval": interval,
            "aggregation": aggregation,
        }
        return _get(url, auth_headers(), params)

    def get_vm_cpu_metrics(self, resource_id: str, timespan: str = "PT1H") -> dict:
        """Convenience: CPU % for a VM."""
        return self.get_resource_metrics(
            resource_id,
            metric_names=["Percentage CPU", "Available Memory Bytes"],
            timespan=timespan,
        )

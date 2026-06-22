import os
import requests
from azure.identity import DefaultAzureCredential


class AzureResourcesClient:
    def __init__(self):
        self.credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        self.base = "https://management.azure.com"

    def _token(self):
        return self.credential.get_token("https://management.azure.com/.default").token

    def _headers(self):
        return {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"}

    def list_resources(self, subscription_id: str):
        url = f"{self.base}/subscriptions/{subscription_id}/resources?api-version=2021-04-01"
        r = requests.get(url, headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("value", [])

    def list_vms(self, subscription_id: str):
        url = f"{self.base}/subscriptions/{subscription_id}/providers/Microsoft.Compute/virtualMachines?api-version=2023-03-01"
        r = requests.get(url, headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("value", [])

    def list_storage_accounts(self, subscription_id: str):
        url = f"{self.base}/subscriptions/{subscription_id}/providers/Microsoft.Storage/storageAccounts?api-version=2023-01-01"
        r = requests.get(url, headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("value", [])

    def list_aks_clusters(self, subscription_id: str):
        url = f"{self.base}/subscriptions/{subscription_id}/providers/Microsoft.ContainerService/managedClusters?api-version=2023-05-01"
        r = requests.get(url, headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("value", [])

    def list_app_services(self, subscription_id: str):
        url = f"{self.base}/subscriptions/{subscription_id}/providers/Microsoft.Web/sites?api-version=2023-01-01"
        r = requests.get(url, headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("value", [])

    def list_sql_servers(self, subscription_id: str):
        url = f"{self.base}/subscriptions/{subscription_id}/providers/Microsoft.Sql/servers?api-version=2022-05-01-preview"
        r = requests.get(url, headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("value", [])

    def list_resource_groups(self, subscription_id: str):
        url = f"{self.base}/subscriptions/{subscription_id}/resourcegroups?api-version=2021-04-01"
        r = requests.get(url, headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("value", [])

    def list_network_interfaces(self, subscription_id: str):
        url = f"{self.base}/subscriptions/{subscription_id}/providers/Microsoft.Network/networkInterfaces?api-version=2023-05-01"
        r = requests.get(url, headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("value", [])

    def list_public_ips(self, subscription_id: str):
        url = f"{self.base}/subscriptions/{subscription_id}/providers/Microsoft.Network/publicIPAddresses?api-version=2023-05-01"
        r = requests.get(url, headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("value", [])

    def list_disks(self, subscription_id: str):
        url = f"{self.base}/subscriptions/{subscription_id}/providers/Microsoft.Compute/disks?api-version=2023-04-02"
        r = requests.get(url, headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("value", [])

    def list_keyvaults(self, subscription_id: str):
        url = f"{self.base}/subscriptions/{subscription_id}/providers/Microsoft.KeyVault/vaults?api-version=2023-02-01"
        r = requests.get(url, headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("value", [])

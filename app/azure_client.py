"""Azure client factory — builds real ARM SDK clients for all subscriptions.

Authentication (default):
  - Managed Identity when deployed to Azure (system- or user-assigned)
  - Optional user-assigned identity via AZURE_CLIENT_ID / Settings UI

Fallbacks:
  - Service principal via Settings UI or env vars
  - Default credential chain / Azure CLI for local development
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.containerservice import ContainerServiceClient
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.keyvault import KeyVaultManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from azure.mgmt.sql import SqlManagementClient
from azure.mgmt.storage import StorageManagementClient


@lru_cache(maxsize=1)
def _get_credential():
    from app.auth import get_credential
    return get_credential()


@lru_cache(maxsize=1)
def _build_all_clients() -> dict[str, Any]:
    cred = _get_credential()
    sub_client = SubscriptionClient(cred)
    subscription_ids = [s.subscription_id for s in sub_client.subscriptions.list()]

    compute_clients: dict[str, ComputeManagementClient] = {}
    aks_clients: dict[str, ContainerServiceClient] = {}
    network_clients: dict[str, NetworkManagementClient] = {}
    storage_clients: dict[str, StorageManagementClient] = {}
    sql_clients: dict[str, SqlManagementClient] = {}
    keyvault_clients: dict[str, KeyVaultManagementClient] = {}
    monitor_clients: dict[str, MonitorManagementClient] = {}
    resource_clients: dict[str, ResourceManagementClient] = {}
    cost_clients: dict[str, CostManagementClient] = {}

    for sid in subscription_ids:
        compute_clients[sid] = ComputeManagementClient(cred, sid)
        aks_clients[sid] = ContainerServiceClient(cred, sid)
        network_clients[sid] = NetworkManagementClient(cred, sid)
        storage_clients[sid] = StorageManagementClient(cred, sid)
        sql_clients[sid] = SqlManagementClient(cred, sid)
        keyvault_clients[sid] = KeyVaultManagementClient(cred, sid)
        monitor_clients[sid] = MonitorManagementClient(cred, sid)
        resource_clients[sid] = ResourceManagementClient(cred, sid)
        cost_clients[sid] = CostManagementClient(cred)

    return {
        "credential": cred,
        "subscription_client": sub_client,
        "subscription_ids": subscription_ids,
        "compute_clients": compute_clients,
        "aks_clients": aks_clients,
        "network_clients": network_clients,
        "storage_clients": storage_clients,
        "sql_clients": sql_clients,
        "keyvault_clients": keyvault_clients,
        "monitor_clients": monitor_clients,
        "resource_clients": resource_clients,
        "cost_clients": cost_clients,
    }


def reset_client_cache() -> None:
    _get_credential.cache_clear()
    _build_all_clients.cache_clear()


def get_azure_clients() -> dict[str, Any]:
    """FastAPI dependency — returns the shared client registry."""
    return _build_all_clients()

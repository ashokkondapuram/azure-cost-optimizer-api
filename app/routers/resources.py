"""Resources router — real Azure ARM calls, no mocks."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from app.azure_client import get_azure_clients

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("/subscriptions")
async def list_subscriptions(clients=Depends(get_azure_clients)):
    """Return all subscriptions accessible via the service principal."""
    sub_client = clients["subscription_client"]
    subs = [s.as_dict() for s in sub_client.subscriptions.list()]
    return subs


@router.get("/vms")
async def list_vms(
    subscription_id: str = Query(...),
    resource_group: str | None = Query(None),
    clients=Depends(get_azure_clients),
):
    compute = clients["compute_clients"].get(subscription_id)
    if not compute:
        return []
    if resource_group:
        items = list(compute.virtual_machines.list(resource_group))
    else:
        items = list(compute.virtual_machines.list_all())
    return [vm.as_dict() for vm in items]


@router.get("/disks")
async def list_disks(
    subscription_id: str = Query(...),
    clients=Depends(get_azure_clients),
):
    compute = clients["compute_clients"].get(subscription_id)
    if not compute:
        return []
    return [d.as_dict() for d in compute.disks.list()]


@router.get("/aks")
async def list_aks(
    subscription_id: str = Query(...),
    clients=Depends(get_azure_clients),
):
    aks = clients["aks_clients"].get(subscription_id)
    if not aks:
        return []
    return [c.as_dict() for c in aks.managed_clusters.list()]


@router.get("/storage")
async def list_storage(
    subscription_id: str = Query(...),
    clients=Depends(get_azure_clients),
):
    storage = clients["storage_clients"].get(subscription_id)
    if not storage:
        return []
    return [s.as_dict() for s in storage.storage_accounts.list()]


@router.get("/publicips")
async def list_public_ips(
    subscription_id: str = Query(...),
    clients=Depends(get_azure_clients),
):
    net = clients["network_clients"].get(subscription_id)
    if not net:
        return []
    return [ip.as_dict() for ip in net.public_ip_addresses.list_all()]


@router.get("/sql")
async def list_sql(
    subscription_id: str = Query(...),
    clients=Depends(get_azure_clients),
):
    sql = clients["sql_clients"].get(subscription_id)
    if not sql:
        return []
    dbs: list = []
    for server in sql.servers.list():
        for db in sql.databases.list_by_server(
            server.as_dict()["id"].split("/")[4],
            server.name,
        ):
            dbs.append(db.as_dict())
    return dbs


@router.get("/keyvaults")
async def list_keyvaults(
    subscription_id: str = Query(...),
    clients=Depends(get_azure_clients),
):
    kv = clients["keyvault_clients"].get(subscription_id)
    if not kv:
        return []
    return [v.as_dict() for v in kv.vaults.list()]


@router.get("/resource-groups")
async def list_resource_groups(
    subscription_id: str = Query(...),
    clients=Depends(get_azure_clients),
):
    rm = clients["resource_clients"].get(subscription_id)
    if not rm:
        return []
    return [rg.as_dict() for rg in rm.resource_groups.list()]


@router.get("/vm-skus")
async def list_vm_skus(
    subscription_id: str = Query(...),
    location: str = Query("eastus"),
    clients=Depends(get_azure_clients),
):
    compute = clients["compute_clients"].get(subscription_id)
    if not compute:
        return []
    return [
        s.as_dict() for s in compute.resource_skus.list(filter=f"location eq '{location}'")
        if s.resource_type == "virtualMachines"
    ]

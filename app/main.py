"""Azure Cost Optimizer — Production API.

All Azure data is fetched live from official Microsoft ARM/Cost Management APIs.
No mock data. No assumptions.
"""
import uuid
import json
import structlog
from fastapi import FastAPI, HTTPException, Query, Depends, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from app.azure_cost import AzureCostClient
from app.azure_resources import AzureResourcesClient
from app.http_client import AzureAPIError
from app.database import get_db, engine
from app.models import Base, CostRecord, K8sUtilization

Base.metadata.create_all(bind=engine)
log = structlog.get_logger()

app = FastAPI(
    title="Azure Cost Optimizer API",
    version="4.0.0",
    description="Production FinOps platform — 100% Azure official APIs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cost_client = AzureCostClient()
resource_client = AzureResourcesClient()


# ─── Exception handler ────────────────────────────────────────────────────────
@app.exception_handler(AzureAPIError)
async def azure_error_handler(request, exc: AzureAPIError):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


# ─── Schemas ──────────────────────────────────────────────────────────────────
class K8sUtilizationIn(BaseModel):
    cluster_name: Optional[str] = None
    node_name: str
    pod_name: Optional[str] = None
    namespace: Optional[str] = None
    cpu_usage: Optional[str] = None
    memory_usage: Optional[str] = None


# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "version": "4.0.0"}


# ═══════════════════════════════════════════════════════════════════════════════
#  COST MANAGEMENT
#  All powered by Microsoft.CostManagement API v2024-08-01
#  https://learn.microsoft.com/en-us/rest/api/cost-management/
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/costs", tags=["Cost Management"],
         summary="Query actual costs — grouped by ResourceGroup + ServiceName")
def get_costs(
    subscription_id: str = Query(..., description="Azure Subscription ID (GUID)"),
    timeframe: str = Query("MonthToDate", description="MonthToDate | BillingMonthToDate | TheLastMonth | Custom"),
    granularity: str = Query("Daily", description="Daily | Monthly | None"),
    db: Session = Depends(get_db),
):
    scope = f"/subscriptions/{subscription_id}"
    data = cost_client.query_cost(scope=scope, timeframe=timeframe, granularity=granularity)
    record = CostRecord(
        id=str(uuid.uuid4()), subscription_id=subscription_id,
        timeframe=timeframe, granularity=granularity,
        raw_response=json.dumps(data),
    )
    db.add(record); db.commit()
    return {"id": record.id, "scope": scope, "timeframe": timeframe,
            "granularity": granularity, "data": data}


@app.get("/costs/resource-group", tags=["Cost Management"],
         summary="Query costs scoped to a specific Resource Group")
def get_rg_costs(
    subscription_id: str = Query(...),
    resource_group: str = Query(...),
    timeframe: str = Query("MonthToDate"),
    granularity: str = Query("Daily"),
    db: Session = Depends(get_db),
):
    scope = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
    data = cost_client.query_cost(scope=scope, timeframe=timeframe, granularity=granularity)
    record = CostRecord(
        id=str(uuid.uuid4()), subscription_id=subscription_id,
        resource_group=resource_group, timeframe=timeframe,
        granularity=granularity, raw_response=json.dumps(data),
    )
    db.add(record); db.commit()
    return {"id": record.id, "scope": scope, "data": data}


@app.get("/costs/by-resource", tags=["Cost Management"],
         summary="Cost per resource ID — grouped by ResourceId, ResourceType, ResourceGroup, ServiceName")
def get_costs_by_resource(
    subscription_id: str = Query(...),
    timeframe: str = Query("MonthToDate"),
):
    return cost_client.query_cost_by_resource(subscription_id, timeframe)


@app.get("/costs/by-service", tags=["Cost Management"],
         summary="Cost grouped by ServiceName + ServiceTier")
def get_costs_by_service(
    subscription_id: str = Query(...),
    timeframe: str = Query("MonthToDate"),
):
    return cost_client.query_cost_by_service(subscription_id, timeframe)


@app.get("/costs/forecast", tags=["Cost Management"],
         summary="Forecast costs for the current month")
def get_cost_forecast(
    subscription_id: str = Query(...),
    timeframe: str = Query("MonthToDate"),
):
    return cost_client.query_forecast(subscription_id, timeframe)


@app.get("/costs/budgets", tags=["Cost Management"],
         summary="List all cost budgets for a subscription")
def get_budgets(subscription_id: str = Query(...)):
    return cost_client.list_budgets(subscription_id)


@app.get("/costs/dimensions", tags=["Cost Management"],
         summary="List available Cost Management dimension values")
def get_dimensions(subscription_id: str = Query(...)):
    return cost_client.list_dimensions(subscription_id)


@app.get("/costs/history", tags=["Cost Management"],
         summary="Query audit log from PostgreSQL")
def cost_history(db: Session = Depends(get_db)):
    records = db.query(CostRecord).order_by(CostRecord.created_at.desc()).limit(100).all()
    return [{"id": r.id, "subscription_id": r.subscription_id,
             "resource_group": r.resource_group, "timeframe": r.timeframe,
             "granularity": r.granularity, "created_at": str(r.created_at)}
            for r in records]


# ═══════════════════════════════════════════════════════════════════════════════
#  RESOURCES — COMPUTE
#  https://learn.microsoft.com/en-us/rest/api/compute/
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/resources/all", tags=["Resources"],
         summary="List all resources in a subscription (ARM resources API v2024-03-01)")
def all_resources(
    subscription_id: str = Query(...),
    resource_type: Optional[str] = Query(None, description="Filter e.g. Microsoft.Compute/virtualMachines"),
):
    return resource_client.list_resources(subscription_id, resource_type)


@app.get("/resources/subscriptions", tags=["Resources"],
         summary="List all subscriptions accessible to this credential")
def list_subscriptions():
    return resource_client.list_subscriptions()


@app.get("/resources/resource-groups", tags=["Resources"],
         summary="List resource groups in a subscription")
def list_resource_groups(subscription_id: str = Query(...)):
    return resource_client.list_resource_groups(subscription_id)


@app.get("/resources/vms", tags=["Compute"],
         summary="List all VMs with full hardware profile, OS disk, network config (API 2024-03-01)")
def list_vms(subscription_id: str = Query(...)):
    return resource_client.list_vms(subscription_id)


@app.get("/resources/vms/{resource_group}/{vm_name}", tags=["Compute"],
         summary="Get single VM with instanceView (power state, extensions, OS details)")
def get_vm(
    resource_group: str = Path(...),
    vm_name: str = Path(...),
    subscription_id: str = Query(...),
):
    return resource_client.get_vm(subscription_id, resource_group, vm_name)


@app.get("/resources/vm-skus", tags=["Compute"],
         summary="All VM SKUs for a location — vCPUs, memory, max disks, capabilities (Resource SKUs API 2021-07-01)")
def list_vm_skus(
    subscription_id: str = Query(...),
    location: str = Query(..., description="Azure region e.g. eastus, canadacentral"),
):
    return resource_client.list_vm_skus(subscription_id, location)


@app.get("/resources/vm-sizes", tags=["Compute"],
         summary="VM sizes in a location with core count and memory (Compute locations API 2024-03-01)")
def list_vm_sizes(
    subscription_id: str = Query(...),
    location: str = Query(...),
):
    return resource_client.list_vm_sizes(subscription_id, location)


@app.get("/resources/disks", tags=["Compute"],
         summary="Managed disks — includes unattached detection (API 2023-10-02)")
def list_disks(subscription_id: str = Query(...)):
    return resource_client.list_disks(subscription_id)


@app.get("/resources/snapshots", tags=["Compute"],
         summary="Disk snapshots (API 2023-10-02)")
def list_snapshots(subscription_id: str = Query(...)):
    return resource_client.list_snapshots(subscription_id)


# ═══════════════════════════════════════════════════════════════════════════════
#  RESOURCES — KUBERNETES / AKS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/resources/aks", tags=["Kubernetes"],
         summary="List AKS clusters — full node pool, networking, addon details (API 2024-02-01)")
def list_aks(subscription_id: str = Query(...)):
    return resource_client.list_aks_clusters(subscription_id)


@app.get("/resources/aks/{resource_group}/{cluster_name}", tags=["Kubernetes"],
         summary="Get single AKS cluster detail")
def get_aks_cluster(
    resource_group: str = Path(...),
    cluster_name: str = Path(...),
    subscription_id: str = Query(...),
):
    return resource_client.get_aks_cluster(subscription_id, resource_group, cluster_name)


@app.get("/resources/aks/{resource_group}/{cluster_name}/node-pools", tags=["Kubernetes"],
         summary="List AKS agent/node pools")
def list_aks_node_pools(
    resource_group: str = Path(...),
    cluster_name: str = Path(...),
    subscription_id: str = Query(...),
):
    return resource_client.list_aks_node_pools(subscription_id, resource_group, cluster_name)


@app.get("/resources/aks/{resource_group}/{cluster_name}/upgrades", tags=["Kubernetes"],
         summary="Available Kubernetes version upgrades")
def get_aks_upgrades(
    resource_group: str = Path(...),
    cluster_name: str = Path(...),
    subscription_id: str = Query(...),
):
    return resource_client.list_aks_upgrades(subscription_id, resource_group, cluster_name)


# ═══════════════════════════════════════════════════════════════════════════════
#  RESOURCES — STORAGE / WEB / DATABASE / NETWORKING / SECURITY
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/resources/storage", tags=["Storage"],
         summary="Storage accounts (API 2023-05-01)")
def list_storage(subscription_id: str = Query(...)):
    return resource_client.list_storage_accounts(subscription_id)


@app.get("/resources/appservices", tags=["App Services"],
         summary="Web apps / Function apps (API 2023-12-01)")
def list_appservices(subscription_id: str = Query(...)):
    return resource_client.list_app_services(subscription_id)


@app.get("/resources/appserviceplans", tags=["App Services"],
         summary="App Service Plans with SKU and worker count (API 2023-12-01)")
def list_appservice_plans(subscription_id: str = Query(...)):
    return resource_client.list_app_service_plans(subscription_id)


@app.get("/resources/sql", tags=["Databases"],
         summary="SQL Servers (API 2023-08-01-preview)")
def list_sql(subscription_id: str = Query(...)):
    return resource_client.list_sql_servers(subscription_id)


@app.get("/resources/sql/{resource_group}/{server_name}/databases", tags=["Databases"],
         summary="Databases on a SQL Server")
def list_sql_databases(
    resource_group: str = Path(...),
    server_name: str = Path(...),
    subscription_id: str = Query(...),
):
    return resource_client.list_sql_databases(subscription_id, resource_group, server_name)


@app.get("/resources/postgresql", tags=["Databases"],
         summary="PostgreSQL Flexible Servers (API 2023-12-01-preview)")
def list_postgresql(subscription_id: str = Query(...)):
    return resource_client.list_postgresql_flexible(subscription_id)


@app.get("/resources/mysql", tags=["Databases"],
         summary="MySQL Flexible Servers (API 2023-12-30)")
def list_mysql(subscription_id: str = Query(...)):
    return resource_client.list_mysql_flexible(subscription_id)


@app.get("/resources/cosmosdb", tags=["Databases"],
         summary="Cosmos DB accounts (API 2024-05-15)")
def list_cosmosdb(subscription_id: str = Query(...)):
    return resource_client.list_cosmosdb(subscription_id)


@app.get("/resources/publicips", tags=["Networking"],
         summary="Public IP addresses — detects unassociated IPs (API 2024-01-01)")
def list_publicips(subscription_id: str = Query(...)):
    return resource_client.list_public_ips(subscription_id)


@app.get("/resources/vnets", tags=["Networking"],
         summary="Virtual Networks (API 2024-01-01)")
def list_vnets(subscription_id: str = Query(...)):
    return resource_client.list_vnets(subscription_id)


@app.get("/resources/loadbalancers", tags=["Networking"],
         summary="Load Balancers (API 2024-01-01)")
def list_load_balancers(subscription_id: str = Query(...)):
    return resource_client.list_load_balancers(subscription_id)


@app.get("/resources/appgateways", tags=["Networking"],
         summary="Application Gateways (API 2024-01-01)")
def list_app_gateways(subscription_id: str = Query(...)):
    return resource_client.list_application_gateways(subscription_id)


@app.get("/resources/nsgs", tags=["Networking"],
         summary="Network Security Groups (API 2024-01-01)")
def list_nsgs(subscription_id: str = Query(...)):
    return resource_client.list_network_security_groups(subscription_id)


@app.get("/resources/keyvaults", tags=["Security"],
         summary="Key Vaults (API 2023-07-01)")
def list_keyvaults(subscription_id: str = Query(...)):
    return resource_client.list_keyvaults(subscription_id)


@app.get("/resources/acr", tags=["Containers"],
         summary="Azure Container Registries (API 2023-11-01-preview)")
def list_acr(subscription_id: str = Query(...)):
    return resource_client.list_container_registries(subscription_id)


# ═══════════════════════════════════════════════════════════════════════════════
#  AZURE MONITOR METRICS
#  https://learn.microsoft.com/en-us/rest/api/monitor/metrics/list
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/metrics/vm-cpu", tags=["Monitor"],
         summary="CPU % + Available Memory for a VM — Azure Monitor (API 2023-10-01)")
def get_vm_cpu(
    resource_id: str = Query(..., description="Full ARM resource ID"),
    timespan: str = Query("PT1H", description="ISO 8601 duration e.g. PT1H, P1D"),
):
    return resource_client.get_vm_cpu_metrics(resource_id, timespan)


@app.get("/metrics/resource", tags=["Monitor"],
         summary="Generic metric query for any ARM resource")
def get_resource_metric(
    resource_id: str = Query(...),
    metric_names: str = Query(..., description="Comma-separated metric names"),
    timespan: str = Query("PT1H"),
    interval: str = Query("PT5M"),
    aggregation: str = Query("Average"),
):
    return resource_client.get_resource_metrics(
        resource_id,
        metric_names=[m.strip() for m in metric_names.split(",")],
        timespan=timespan,
        interval=interval,
        aggregation=aggregation,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  KUBERNETES UTILIZATION  (push from cluster agents)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/k8s/utilization", tags=["Kubernetes"])
def save_k8s(payload: K8sUtilizationIn, db: Session = Depends(get_db)):
    record = K8sUtilization(id=str(uuid.uuid4()), **payload.dict())
    db.add(record); db.commit()
    return {"status": "saved", "id": record.id}


@app.get("/k8s/utilization", tags=["Kubernetes"])
def get_k8s(
    cluster_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(K8sUtilization).order_by(K8sUtilization.recorded_at.desc())
    if cluster_name:
        q = q.filter(K8sUtilization.cluster_name == cluster_name)
    records = q.limit(500).all()
    return [{"id": r.id, "cluster": r.cluster_name, "node": r.node_name,
             "pod": r.pod_name, "namespace": r.namespace,
             "cpu": r.cpu_usage, "memory": r.memory_usage,
             "recorded_at": str(r.recorded_at)}
            for r in records]

"""Azure Cost Optimizer — Production API v5.0

Includes:
  - Full Cost Management API (v2024-08-01)
  - All resource type endpoints (Compute, AKS, Storage, Network, DB, Security)
  - Optimization Engine with configurable rules + profiles
  - Engine config CRUD (enable/disable rules, override thresholds per profile)
  - Finding history + remediation status tracking
"""
import uuid
import json
import structlog
from fastapi import FastAPI, HTTPException, Query, Depends, Path, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from app.azure_cost import AzureCostClient
from app.azure_resources import AzureResourcesClient
from app.http_client import AzureAPIError
from app.database import get_db, engine
from app.models import (
    Base, CostRecord, K8sUtilization,
    OptimizationRun, EngineConfig, OptimizationFinding,
)
from app.optimizer.rules import DEFAULT_RULES, Category, Severity
from app.optimizer.engine import OptimizationEngine
from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.engine_config import get_effective_config, upsert_rule_config, delete_rule_config

Base.metadata.create_all(bind=engine)
log = structlog.get_logger()

app = FastAPI(
    title="Azure Cost Optimizer API",
    version="5.0.0",
    description="Production FinOps platform — real Azure APIs + Optimization Engine",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cost_client     = AzureCostClient()
resource_client = AzureResourcesClient()


@app.exception_handler(AzureAPIError)
async def azure_error_handler(request, exc: AzureAPIError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status,
                        content={"error": {"code": exc.code, "message": exc.message}})


# ─── Schemas ──────────────────────────────────────────────────────────────────

class K8sUtilizationIn(BaseModel):
    cluster_name: Optional[str] = None
    node_name: str
    pod_name: Optional[str] = None
    namespace: Optional[str] = None
    cpu_usage: Optional[str] = None
    memory_usage: Optional[str] = None


class RuleConfigIn(BaseModel):
    rule_id:     str  = Field(..., description="Rule ID e.g. VM_IDLE, AKS_NO_AUTOSCALER")
    enabled:     bool = True
    overrides:   dict = Field(default_factory=dict,
                              description="Threshold overrides e.g. {\"cpu_idle_pct\": 3.0}")
    description: Optional[str] = None


class AnalyzeRequest(BaseModel):
    subscription_id:  str
    profile:          str  = Field("default", description="Engine config profile name")
    engine_version:   str  = Field("standard", description="standard | extended")
    rule_overrides:   dict = Field(
        default_factory=dict,
        description="Per-rule runtime overrides: {\"VM_IDLE\": {\"cpu_idle_pct\": 3.0}}"
    )
    include_metrics:  bool = Field(False, description="Fetch Azure Monitor metrics for deeper analysis")
    timespan_metrics: str  = Field("P7D",  description="ISO 8601 duration for metric lookback e.g. P7D, P1D")


class FindingStatusIn(BaseModel):
    status: str = Field(..., description="open | acknowledged | resolved | ignored")


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "version": "5.0.0"}


# ══════════════════════════════════════════════════════════════════════════════
#  COST MANAGEMENT  (Microsoft.CostManagement v2024-08-01)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/costs", tags=["Cost Management"],
         summary="Query actual costs grouped by ResourceGroup + ServiceName")
def get_costs(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    granularity:     str = Query("Daily"),
    db: Session = Depends(get_db),
):
    scope = f"/subscriptions/{subscription_id}"
    data  = cost_client.query_cost(scope=scope, timeframe=timeframe, granularity=granularity)
    record = CostRecord(
        id=str(uuid.uuid4()), subscription_id=subscription_id,
        timeframe=timeframe, granularity=granularity, raw_response=json.dumps(data),
    )
    db.add(record); db.commit()
    return {"id": record.id, "scope": scope, "timeframe": timeframe, "granularity": granularity, "data": data}


@app.get("/costs/resource-group", tags=["Cost Management"],
         summary="Query costs scoped to a Resource Group")
def get_rg_costs(
    subscription_id: str = Query(...),
    resource_group:  str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    granularity:     str = Query("Daily"),
    db: Session = Depends(get_db),
):
    scope = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
    data  = cost_client.query_cost(scope=scope, timeframe=timeframe, granularity=granularity)
    record = CostRecord(
        id=str(uuid.uuid4()), subscription_id=subscription_id,
        resource_group=resource_group, timeframe=timeframe,
        granularity=granularity, raw_response=json.dumps(data),
    )
    db.add(record); db.commit()
    return {"id": record.id, "scope": scope, "data": data}


@app.get("/costs/by-resource", tags=["Cost Management"],
         summary="Cost per resource ID (ResourceId, ResourceType, ResourceGroup, ServiceName)")
def get_costs_by_resource(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
):
    return cost_client.query_cost_by_resource(subscription_id, timeframe)


@app.get("/costs/by-service", tags=["Cost Management"],
         summary="Cost grouped by ServiceName + ServiceTier")
def get_costs_by_service(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
):
    return cost_client.query_cost_by_service(subscription_id, timeframe)


@app.get("/costs/forecast", tags=["Cost Management"],
         summary="Forecast costs for the current billing period")
def get_cost_forecast(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
):
    return cost_client.query_forecast(subscription_id, timeframe)


@app.get("/costs/budgets", tags=["Cost Management"],
         summary="List all budgets configured on a subscription")
def get_budgets(subscription_id: str = Query(...)):
    return cost_client.list_budgets(subscription_id)


@app.get("/costs/dimensions", tags=["Cost Management"],
         summary="Available Cost Management filter dimensions")
def get_dimensions(subscription_id: str = Query(...)):
    return cost_client.list_dimensions(subscription_id)


@app.get("/costs/history", tags=["Cost Management"],
         summary="Audit log of cost queries from PostgreSQL")
def cost_history(db: Session = Depends(get_db)):
    records = db.query(CostRecord).order_by(CostRecord.created_at.desc()).limit(100).all()
    return [{"id": r.id, "subscription_id": r.subscription_id,
             "resource_group": r.resource_group, "timeframe": r.timeframe,
             "granularity": r.granularity, "created_at": str(r.created_at)}
            for r in records]


# ══════════════════════════════════════════════════════════════════════════════
#  RESOURCES — COMPUTE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/resources/all", tags=["Resources"],
         summary="List all resources (ARM v2024-03-01) with optional type filter")
def all_resources(
    subscription_id: str = Query(...),
    resource_type:   Optional[str] = Query(None, description="e.g. Microsoft.Compute/virtualMachines"),
):
    return resource_client.list_resources(subscription_id, resource_type)


@app.get("/resources/subscriptions", tags=["Resources"],
         summary="List all accessible subscriptions")
def list_subscriptions():
    return resource_client.list_subscriptions()


@app.get("/resources/resource-groups", tags=["Resources"],
         summary="List resource groups in a subscription")
def list_resource_groups(subscription_id: str = Query(...)):
    return resource_client.list_resource_groups(subscription_id)


@app.get("/resources/vms", tags=["Compute"],
         summary="All VMs with hardware profile, OS disk, network (API 2024-03-01 + instanceView)")
def list_vms(subscription_id: str = Query(...)):
    return resource_client.list_vms(subscription_id)


@app.get("/resources/vms/{resource_group}/{vm_name}", tags=["Compute"],
         summary="Single VM with instanceView (power state, extensions, OS)")
def get_vm(
    resource_group: str = Path(...),
    vm_name:        str = Path(...),
    subscription_id: str = Query(...),
):
    return resource_client.get_vm(subscription_id, resource_group, vm_name)


@app.get("/resources/vm-skus", tags=["Compute"],
         summary="All VM SKUs in a region — vCPUs, memory, max disks, capabilities (Resource SKUs API 2021-07-01)")
def list_vm_skus(
    subscription_id: str = Query(...),
    location:        str = Query(..., description="Azure region e.g. eastus, westeurope"),
):
    return resource_client.list_vm_skus(subscription_id, location)


@app.get("/resources/vm-sizes", tags=["Compute"],
         summary="VM sizes in a location — core count and memory (Compute API 2024-03-01)")
def list_vm_sizes(
    subscription_id: str = Query(...),
    location:        str = Query(...),
):
    return resource_client.list_vm_sizes(subscription_id, location)


@app.get("/resources/disks", tags=["Compute"],
         summary="Managed disks incl. unattached detection (API 2023-10-02)")
def list_disks(subscription_id: str = Query(...)):
    return resource_client.list_disks(subscription_id)


@app.get("/resources/snapshots", tags=["Compute"],
         summary="Disk snapshots (API 2023-10-02)")
def list_snapshots(subscription_id: str = Query(...)):
    return resource_client.list_snapshots(subscription_id)


# ══════════════════════════════════════════════════════════════════════════════
#  RESOURCES — KUBERNETES / AKS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/resources/aks", tags=["Kubernetes"],
         summary="All AKS clusters — full node pool, networking, addon config (API 2024-02-01)")
def list_aks(subscription_id: str = Query(...)):
    return resource_client.list_aks_clusters(subscription_id)


@app.get("/resources/aks/{resource_group}/{cluster_name}", tags=["Kubernetes"],
         summary="Single AKS cluster detail")
def get_aks_cluster(
    resource_group: str = Path(...),
    cluster_name:   str = Path(...),
    subscription_id: str = Query(...),
):
    return resource_client.get_aks_cluster(subscription_id, resource_group, cluster_name)


@app.get("/resources/aks/{resource_group}/{cluster_name}/node-pools", tags=["Kubernetes"],
         summary="AKS node pools (agent pools) for a cluster")
def list_aks_node_pools(
    resource_group: str = Path(...),
    cluster_name:   str = Path(...),
    subscription_id: str = Query(...),
):
    return resource_client.list_aks_node_pools(subscription_id, resource_group, cluster_name)


@app.get("/resources/aks/{resource_group}/{cluster_name}/upgrades", tags=["Kubernetes"],
         summary="Available Kubernetes version upgrades for a cluster")
def get_aks_upgrades(
    resource_group: str = Path(...),
    cluster_name:   str = Path(...),
    subscription_id: str = Query(...),
):
    return resource_client.list_aks_upgrades(subscription_id, resource_group, cluster_name)


# ══════════════════════════════════════════════════════════════════════════════
#  RESOURCES — STORAGE / WEB / DATABASE / NETWORKING / SECURITY
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/resources/storage",        tags=["Storage"],      summary="Storage accounts (API 2023-05-01)")
def list_storage(subscription_id: str = Query(...)): return resource_client.list_storage_accounts(subscription_id)

@app.get("/resources/appservices",    tags=["App Services"], summary="Web/Function apps (API 2023-12-01)")
def list_appservices(subscription_id: str = Query(...)): return resource_client.list_app_services(subscription_id)

@app.get("/resources/appserviceplans", tags=["App Services"], summary="App Service Plans (API 2023-12-01)")
def list_asp(subscription_id: str = Query(...)): return resource_client.list_app_service_plans(subscription_id)

@app.get("/resources/sql",            tags=["Databases"],    summary="SQL Servers (API 2023-08-01-preview)")
def list_sql(subscription_id: str = Query(...)): return resource_client.list_sql_servers(subscription_id)

@app.get("/resources/sql/{resource_group}/{server_name}/databases", tags=["Databases"],
         summary="Databases on a SQL Server")
def list_sql_databases(resource_group: str = Path(...), server_name: str = Path(...),
                       subscription_id: str = Query(...)):
    return resource_client.list_sql_databases(subscription_id, resource_group, server_name)

@app.get("/resources/postgresql",     tags=["Databases"],    summary="PostgreSQL Flexible Servers")
def list_postgresql(subscription_id: str = Query(...)): return resource_client.list_postgresql_flexible(subscription_id)

@app.get("/resources/mysql",          tags=["Databases"],    summary="MySQL Flexible Servers")
def list_mysql(subscription_id: str = Query(...)): return resource_client.list_mysql_flexible(subscription_id)

@app.get("/resources/cosmosdb",       tags=["Databases"],    summary="Cosmos DB accounts (API 2024-05-15)")
def list_cosmosdb(subscription_id: str = Query(...)): return resource_client.list_cosmosdb(subscription_id)

@app.get("/resources/publicips",      tags=["Networking"],   summary="Public IPs — unassociated detection (API 2024-01-01)")
def list_publicips(subscription_id: str = Query(...)): return resource_client.list_public_ips(subscription_id)

@app.get("/resources/vnets",          tags=["Networking"],   summary="Virtual Networks (API 2024-01-01)")
def list_vnets(subscription_id: str = Query(...)): return resource_client.list_vnets(subscription_id)

@app.get("/resources/loadbalancers",  tags=["Networking"],   summary="Load Balancers (API 2024-01-01)")
def list_lbs(subscription_id: str = Query(...)): return resource_client.list_load_balancers(subscription_id)

@app.get("/resources/appgateways",    tags=["Networking"],   summary="Application Gateways (API 2024-01-01)")
def list_agws(subscription_id: str = Query(...)): return resource_client.list_application_gateways(subscription_id)

@app.get("/resources/nsgs",           tags=["Networking"],   summary="Network Security Groups (API 2024-01-01)")
def list_nsgs(subscription_id: str = Query(...)): return resource_client.list_network_security_groups(subscription_id)

@app.get("/resources/keyvaults",      tags=["Security"],     summary="Key Vaults (API 2023-07-01)")
def list_kvs(subscription_id: str = Query(...)): return resource_client.list_keyvaults(subscription_id)

@app.get("/resources/acr",            tags=["Containers"],   summary="Container Registries (API 2023-11-01-preview)")
def list_acr(subscription_id: str = Query(...)): return resource_client.list_container_registries(subscription_id)


# ══════════════════════════════════════════════════════════════════════════════
#  AZURE MONITOR METRICS  (API 2023-10-01)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/metrics/vm-cpu", tags=["Monitor"],
         summary="CPU % + Available Memory for a VM (P7D default)")
def get_vm_cpu(
    resource_id: str = Query(..., description="Full ARM resource ID"),
    timespan:    str = Query("P7D"),
):
    return resource_client.get_vm_cpu_metrics(resource_id, timespan)


@app.get("/metrics/resource", tags=["Monitor"],
         summary="Generic metric query for any ARM resource")
def get_resource_metric(
    resource_id:  str = Query(...),
    metric_names: str = Query(..., description="Comma-separated"),
    timespan:     str = Query("PT1H"),
    interval:     str = Query("PT5M"),
    aggregation:  str = Query("Average"),
):
    return resource_client.get_resource_metrics(
        resource_id,
        metric_names=[m.strip() for m in metric_names.split(",")],
        timespan=timespan, interval=interval, aggregation=aggregation,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  OPTIMIZATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/optimize/analyze", tags=["Optimization Engine"],
          summary="Run full optimization analysis — fetches live Azure data, applies all rules, returns findings + savings")
def run_analysis(req: AnalyzeRequest, db: Session = Depends(get_db)):
    """
    Full optimization scan. For 500+ clusters and 1000+ resources:
    - Fetches all resource types in parallel
    - Optionally pulls 7-day Azure Monitor metrics per VM
    - Applies all configured rules (from DB profile + runtime overrides)
    - Persists findings for trending and remediation tracking
    - Returns: summary, top savings, all findings sorted by severity
    """
    sub = req.subscription_id

    # 1. Fetch all resources in parallel
    import concurrent.futures
    fetch_tasks = {
        "vms":            lambda: resource_client.list_vms(sub),
        "disks":          lambda: resource_client.list_disks(sub),
        "snapshots":      lambda: resource_client.list_snapshots(sub),
        "aks":            lambda: resource_client.list_aks_clusters(sub),
        "storage":        lambda: resource_client.list_storage_accounts(sub),
        "public_ips":     lambda: resource_client.list_public_ips(sub),
        "load_balancers": lambda: resource_client.list_load_balancers(sub),
        "app_gateways":   lambda: resource_client.list_application_gateways(sub),
        "sql_servers":    lambda: resource_client.list_sql_servers(sub),
        "cosmosdb":       lambda: resource_client.list_cosmosdb(sub),
        "keyvaults":      lambda: resource_client.list_keyvaults(sub),
        "budgets":        lambda: cost_client.list_budgets(sub),
    }

    fetched: dict = {}
    errors:  dict = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futs = {pool.submit(fn): key for key, fn in fetch_tasks.items()}
        for fut in concurrent.futures.as_completed(futs):
            key = futs[fut]
            try:
                fetched[key] = fut.result()
            except Exception as exc:
                log.warning("fetch.failed", resource=key, error=str(exc))
                errors[key]  = str(exc)
                fetched[key] = []

    # 2. Fetch AKS node pools for each cluster (batched)
    aks_node_pools: dict[str, list] = {}
    clusters = fetched.get("aks", [])
    def _fetch_pools(cluster):
        cid = cluster.get("id", "")
        rg  = cid.split("/resourceGroups/")[1].split("/")[0] if "/resourceGroups/" in cid else ""
        cname = cluster.get("name", "")
        try:
            pools = resource_client.list_aks_node_pools(sub, rg, cname)
            return cid, pools
        except Exception:
            return cid, cluster.get("properties", {}).get("agentPoolProfiles", [])

    if clusters:
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            for cid, pools in pool.map(_fetch_pools, clusters):
                aks_node_pools[cid] = pools

    # 3. Optionally fetch VM metrics (costly for 1000+ VMs — off by default)
    vm_metrics: dict = {}
    if req.include_metrics:
        def _fetch_vm_metrics(vm):
            rid = vm.get("id", "")
            try:
                m = resource_client.get_vm_cpu_metrics(rid, req.timespan_metrics)
                return rid.lower(), m
            except Exception:
                return rid.lower(), {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            for rid, m in pool.map(_fetch_vm_metrics, fetched.get("vms", [])):
                if m:
                    vm_metrics[rid] = m

    # 4. Cost by resource for savings estimates
    cost_by_resource: dict = {}
    try:
        cost_resp = cost_client.query_cost_by_resource(sub, "MonthToDate")
        rows = cost_resp.get("properties", {}).get("rows", [])
        cols = [c.get("name") for c in cost_resp.get("properties", {}).get("columns", [])]
        if "ResourceId" in cols and "PreTaxCost" in cols:
            ri_idx   = cols.index("ResourceId")
            cost_idx = cols.index("PreTaxCost")
            for row in rows:
                cost_by_resource[row[ri_idx].lower()] = float(row[cost_idx])
    except Exception as exc:
        log.warning("cost_by_resource.failed", error=str(exc))

    # 5. Build engine with DB profile + runtime overrides merged
    db_overrides      = get_effective_config(db, req.profile)
    merged_overrides  = {**db_overrides, **req.rule_overrides}
    engine_version = req.engine_version.lower()
    if engine_version not in {"standard", "extended"}:
        raise HTTPException(400, "engine_version must be 'standard' or 'extended'")
    eng = (
        ExtendedOptimizationEngine(rule_overrides=merged_overrides)
        if engine_version == "extended"
        else OptimizationEngine(rule_overrides=merged_overrides)
    )

    # 6. Run analysis
    if engine_version == "extended":
        result = eng.analyze(
            subscription_id=sub,
            vms=fetched.get("vms", []),
            disks=fetched.get("disks", []),
            snapshots=fetched.get("snapshots", []),
            aks_clusters=clusters,
            aks_node_pools=aks_node_pools,
            storage=fetched.get("storage", []),
            public_ips=fetched.get("public_ips", []),
            load_balancers=fetched.get("load_balancers", []),
            app_gateways=fetched.get("app_gateways", []),
            sql_databases=[],
            cosmosdb=fetched.get("cosmosdb", []),
            keyvaults=fetched.get("keyvaults", []),
            vm_metrics=vm_metrics,
            cost_by_resource=cost_by_resource,
            budgets=fetched.get("budgets", []),
        )
    else:
        result = eng.analyze(
            vms=fetched.get("vms", []),
            disks=fetched.get("disks", []),
            snapshots=fetched.get("snapshots", []),
            aks_clusters=clusters,
            aks_node_pools=aks_node_pools,
            storage=fetched.get("storage", []),
            public_ips=fetched.get("public_ips", []),
            load_balancers=fetched.get("load_balancers", []),
            app_gateways=fetched.get("app_gateways", []),
            sql_servers=fetched.get("sql_servers", []),
            cosmosdb=fetched.get("cosmosdb", []),
            keyvaults=fetched.get("keyvaults", []),
            vm_metrics=vm_metrics,
            cost_by_resource=cost_by_resource,
            budgets=fetched.get("budgets", []),
        )
        result["engine_version"] = "standard"

    # 7. Persist run
    run_id = str(uuid.uuid4())
    sev    = result["summary"].get("by_severity", {})
    run    = OptimizationRun(
        id=run_id,
        subscription_id=sub,
        profile=req.profile,
        total_findings=result["summary"]["total_findings"],
        critical_count=sev.get("CRITICAL", 0),
        high_count=sev.get("HIGH", 0),
        medium_count=sev.get("MEDIUM", 0),
        low_count=sev.get("LOW", 0),
        total_savings_usd=result["summary"]["total_estimated_monthly_savings_usd"],
        findings_json=json.dumps(result["findings"]),
    )
    db.add(run)

    # Persist individual findings
    for f in result["findings"]:
        db.add(OptimizationFinding(
            id=str(uuid.uuid4()), run_id=run_id,
            rule_id=f["rule_id"], rule_name=f["rule_name"],
            category=f["category"], severity=f["severity"],
            resource_id=f["resource_id"], resource_name=f["resource_name"],
            resource_type=f["resource_type"],
            subscription_id=f["subscription_id"],
            resource_group=f["resource_group"], location=f["location"],
            detail=f["detail"], recommendation=f["recommendation"],
            estimated_savings_usd=f["estimated_savings_usd"],
            waste_score=f["waste_score"],
        ))
    db.commit()

    result["run_id"]         = run_id
    result["fetch_errors"]   = errors
    result["resources_analyzed"] = {k: len(v) for k, v in fetched.items()}
    return result


@app.get("/optimize/runs", tags=["Optimization Engine"],
         summary="List past optimization runs with savings totals")
def list_runs(
    subscription_id: Optional[str] = Query(None),
    limit:           int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(OptimizationRun).order_by(OptimizationRun.analyzed_at.desc())
    if subscription_id:
        q = q.filter(OptimizationRun.subscription_id == subscription_id)
    runs = q.limit(limit).all()
    return [{
        "id": r.id, "subscription_id": r.subscription_id,
        "profile": r.profile,
        "total_findings": r.total_findings,
        "critical": r.critical_count, "high": r.high_count,
        "medium": r.medium_count, "low": r.low_count,
        "total_savings_usd": r.total_savings_usd,
        "analyzed_at": str(r.analyzed_at),
    } for r in runs]


@app.get("/optimize/runs/{run_id}", tags=["Optimization Engine"],
         summary="Full findings for a specific optimization run")
def get_run(run_id: str = Path(...), db: Session = Depends(get_db)):
    run = db.query(OptimizationRun).filter(OptimizationRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    return {
        "id": run.id, "subscription_id": run.subscription_id,
        "profile": run.profile,
        "total_findings": run.total_findings,
        "total_savings_usd": run.total_savings_usd,
        "analyzed_at": str(run.analyzed_at),
        "findings": json.loads(run.findings_json or "[]"),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  ENGINE CONFIGURATION (Rules + Profiles)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/optimize/rules", tags=["Engine Config"],
         summary="List all available rules with default thresholds")
def list_rules():
    """Returns the full catalogue of built-in rules and their configurable thresholds."""
    rules = list(DEFAULT_RULES.values()) + list(ADVANCED_RULES.values())
    return [
        {
            "id":          r.id,
            "name":        r.name,
            "description": r.description,
            "category":    r.category.value,
            "severity":    r.severity.value,
            "enabled":     r.enabled,
            "thresholds":  {
                k: getattr(r, k)
                for k in [
                    "cpu_idle_pct", "cpu_oversize_pct", "mem_idle_pct",
                    "node_cpu_idle", "node_mem_idle", "node_count_min",
                    "cluster_dev_hours", "storage_days_unused",
                    "db_dtu_idle_pct", "budget_warn_pct", "budget_crit_pct",
                    "reserved_savings_threshold", "rightsizing_memory_buffer",
                    "evaluation_window_days", "min_monthly_savings_usd",
                    "memory_idle_pct", "node_cpu_idle_pct", "node_memory_idle_pct",
                    "max_unattached_disk_days", "snapshot_retention_days",
                    "public_ip_idle_days", "min_rightsize_savings_pct",
                    "min_reserved_coverage_hours", "nonprod_shutdown_hours_per_day",
                    "require_tags", "prod_tag_values", "nonprod_tag_values",
                    "spot_allowed_envs", "aks_min_system_nodes",
                    "aks_max_idle_node_ratio", "storage_cool_after_days",
                    "storage_archive_after_days", "sql_serverless_candidate_cpu_pct",
                    "cosmos_autoscale_candidate_utilization_pct",
                    "vm_uptime_hours_candidate",
                ]
                if hasattr(r, k)
            },
        }
        for r in rules
    ]


@app.get("/optimize/config/{profile}", tags=["Engine Config"],
         summary="Get all rule overrides for a named profile")
def get_profile_config(profile: str = Path(...), db: Session = Depends(get_db)):
    rows = db.query(EngineConfig).filter(EngineConfig.profile == profile).all()
    return [
        {
            "rule_id":     r.rule_id,
            "enabled":     r.enabled,
            "overrides":   json.loads(r.overrides_json or "{}"),
            "description": r.description,
            "updated_at":  str(r.updated_at),
        }
        for r in rows
    ]


@app.post("/optimize/config/{profile}", tags=["Engine Config"],
          summary="Create or update a rule override in a profile")
def upsert_config(
    profile: str = Path(..., description="Profile name e.g. default, aggressive, conservative"),
    body:    RuleConfigIn = ...,
    db: Session = Depends(get_db),
):
    known_rules = set(DEFAULT_RULES) | set(ADVANCED_RULES)
    if body.rule_id not in known_rules:
        raise HTTPException(400, f"Unknown rule_id '{body.rule_id}'. Valid: {sorted(known_rules)}")
    row = upsert_rule_config(
        db, profile=profile, rule_id=body.rule_id,
        overrides=body.overrides, enabled=body.enabled,
        description=body.description or "",
    )
    # Assign a UUID if new
    if not row.id:
        row.id = str(uuid.uuid4())
        db.commit()
    return {
        "profile":   profile,
        "rule_id":   row.rule_id,
        "enabled":   row.enabled,
        "overrides": json.loads(row.overrides_json),
        "updated_at": str(row.updated_at),
    }


@app.delete("/optimize/config/{profile}/{rule_id}", tags=["Engine Config"],
            summary="Remove a rule override (resets to default thresholds)")
def delete_config(
    profile: str = Path(...),
    rule_id: str = Path(...),
    db: Session = Depends(get_db),
):
    deleted = delete_rule_config(db, profile=profile, rule_id=rule_id)
    if not deleted:
        raise HTTPException(404, "Config not found")
    return {"deleted": True, "profile": profile, "rule_id": rule_id}


@app.get("/optimize/config", tags=["Engine Config"],
         summary="List all profiles that have been configured")
def list_profiles(db: Session = Depends(get_db)):
    rows = db.query(EngineConfig.profile).distinct().all()
    return {"profiles": [r[0] for r in rows]}


# ══════════════════════════════════════════════════════════════════════════════
#  FINDINGS — Remediation Tracking
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/optimize/findings", tags=["Findings"],
         summary="Query findings with filters — subscription, severity, category, status")
def list_findings(
    subscription_id: Optional[str] = Query(None),
    severity:        Optional[str] = Query(None, description="CRITICAL|HIGH|MEDIUM|LOW|INFO"),
    category:        Optional[str] = Query(None, description="COMPUTE|KUBERNETES|STORAGE|NETWORK|DATABASE|SECURITY|COST"),
    status:          Optional[str] = Query(None, description="open|acknowledged|resolved|ignored"),
    rule_id:         Optional[str] = Query(None),
    limit:           int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    q = db.query(OptimizationFinding).order_by(
        OptimizationFinding.detected_at.desc()
    )
    if subscription_id: q = q.filter(OptimizationFinding.subscription_id == subscription_id)
    if severity:        q = q.filter(OptimizationFinding.severity  == severity.upper())
    if category:        q = q.filter(OptimizationFinding.category  == category.upper())
    if status:          q = q.filter(OptimizationFinding.status    == status.lower())
    if rule_id:         q = q.filter(OptimizationFinding.rule_id   == rule_id.upper())
    findings = q.limit(limit).all()
    return [{
        "id": f.id, "run_id": f.run_id,
        "rule_id": f.rule_id, "rule_name": f.rule_name,
        "category": f.category, "severity": f.severity,
        "resource_id": f.resource_id, "resource_name": f.resource_name,
        "resource_group": f.resource_group, "location": f.location,
        "detail": f.detail, "recommendation": f.recommendation,
        "estimated_savings_usd": f.estimated_savings_usd,
        "waste_score": f.waste_score,
        "status": f.status, "detected_at": str(f.detected_at),
        "resolved_at": str(f.resolved_at) if f.resolved_at else None,
    } for f in findings]


@app.patch("/optimize/findings/{finding_id}/status", tags=["Findings"],
           summary="Update remediation status of a finding")
def update_finding_status(
    finding_id: str = Path(...),
    body:       FindingStatusIn = ...,
    db: Session = Depends(get_db),
):
    valid = {"open", "acknowledged", "resolved", "ignored"}
    if body.status not in valid:
        raise HTTPException(400, f"status must be one of: {valid}")
    f = db.query(OptimizationFinding).filter(OptimizationFinding.id == finding_id).first()
    if not f:
        raise HTTPException(404, "Finding not found")
    from datetime import datetime, timezone
    f.status = body.status
    if body.status == "resolved":
        f.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": f.id, "status": f.status, "resolved_at": str(f.resolved_at) if f.resolved_at else None}


@app.get("/optimize/findings/summary", tags=["Findings"],
         summary="Aggregated findings summary by severity and category")
def findings_summary(
    subscription_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(OptimizationFinding).filter(OptimizationFinding.status == "open")
    if subscription_id:
        q = q.filter(OptimizationFinding.subscription_id == subscription_id)
    findings = q.all()
    by_sev = {}; by_cat = {}; total_savings = 0.0
    for f in findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
        by_cat[f.category] = by_cat.get(f.category, 0) + 1
        total_savings += f.estimated_savings_usd or 0.0
    return {
        "open_findings": len(findings),
        "total_estimated_savings_usd": round(total_savings, 2),
        "by_severity": by_sev,
        "by_category": by_cat,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  KUBERNETES UTILIZATION  (push from cluster agents)
# ══════════════════════════════════════════════════════════════════════════════

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

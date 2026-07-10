"""Optimization Engine router — /optimize and /findings prefixes."""
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.analysis import run_db_analysis
from app.analysis_persist import persist_optimization_run
from app.batch_analyzer import (
    create_analysis_job,
    execute_batch_job,
    queue_post_sync_analysis,
    queue_rule_config_reanalysis,
    serialize_job,
)
from app.database import get_db
from app.auth import arm_bearer_token
from app.optimizer.engine import OptimizationEngine
from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.engine_config import (
    GLOBAL_CONFIG_KEY,
    compare_profiles,
    delete_rule_config,
    get_effective_config,
    get_profile_metadata,
    upsert_rule_config,
    validate_profile_config,
)
from app.optimizer.rule_catalog import (
    canonical_resource_rule_catalog,
    list_all_rules,
    list_components,
    list_rules_for_canonical_type,
    resolve_rule_id,
)
from app.optimizer.rule_registry import ALL_KNOWN_RULE_IDS, is_known_rule
from app.optimizer.unified_engine import append_cost_export_findings
from app.ai_analysis import enrich_analysis_with_ai
from app.finding_evidence import disk_inventory_properties_map, enrich_finding_for_api
from app.user_auth import require_admin_user, require_authenticated_user
from app.validators import validate_subscription_id, validate_finding_status
import structlog

log = structlog.get_logger()


from app.azure_cost import AzureCostClient
from app.azure_resources import AzureResourcesClient
from app.focus_mapping import normalize_arm_id
from app.models import AnalysisJob, EngineConfig, OptimizationRun, OptimizationFinding
from app.resources import list_technical_fetch_specs
from app.arm_resource_enrichment import enrich_arm_resources_for_type
from app.http_client import arm_fetch_workers
import json

cost_client = AzureCostClient()
resource_client = AzureResourcesClient()
log = structlog.get_logger()


router = APIRouter(tags=["Optimization Engine"])


class AnalyzeRequest(BaseModel):
    subscription_id:  str
    profile:          str  = Field("default")
    engine_version:   str  = Field("extended", description="standard | extended")
    data_source:      str  = Field("db", description="db | live")
    rule_overrides:   dict = Field(default_factory=dict)
    components:       Optional[list[str]] = None
    include_metrics:  bool = Field(True)
    include_ai:       bool = Field(True)
    timespan_metrics: str  = Field("P7D")

    @field_validator("subscription_id")
    @classmethod
    def _validate_subscription(cls, value: str) -> str:
        return validate_subscription_id(value)

    @field_validator("data_source")
    @classmethod
    def _validate_data_source(cls, value: str) -> str:
        v = (value or "db").strip().lower()
        if v not in {"db", "live"}:
            raise ValueError("data_source must be 'db' or 'live'")
        return v


class FindingStatusIn(BaseModel):
    status: str = Field(..., description="open | acknowledged | resolved | ignored")

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return validate_finding_status(value)


class BulkFindingStatusIn(BaseModel):
    finding_ids: list[str] = Field(..., min_length=1, max_length=500)
    status: str = Field(...)

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        return validate_finding_status(value)


class RuleConfigIn(BaseModel):
    rule_id:     str  = Field(...)
    enabled:     bool = True
    overrides:   dict = Field(default_factory=dict)
    description: Optional[str] = None


class ActionWorkflowIn(BaseModel):
    workflow_status: str | None = Field(None)
    owner: str | None = None
    note: str | None = None
    clear_owner: bool = False

    @field_validator("workflow_status")
    @classmethod
    def _validate_workflow(cls, value: str | None) -> str | None:
        if value is None:
            return None
        v = value.strip().lower()
        valid = {"proposed", "approved", "executed", "rejected", "deferred"}
        if v not in valid:
            raise ValueError(f"workflow_status must be one of: {sorted(valid)}")
        return v


class BulkActionWorkflowIn(BaseModel):
    action_ids: list[str] = Field(..., min_length=1, max_length=500)
    workflow_status: str = Field(...)
    note: str | None = None

    @field_validator("workflow_status")
    @classmethod
    def _validate_workflow(cls, value: str) -> str:
        v = value.strip().lower()
        valid = {"proposed", "approved", "executed", "rejected", "deferred"}
        if v not in valid:
            raise ValueError(f"workflow_status must be one of: {sorted(valid)}")
        return v


class BulkActionAssignIn(BaseModel):
    action_ids: list[str] = Field(..., min_length=1, max_length=500)
    owner: str = Field(..., min_length=1, max_length=200)
    note: str | None = None


class FindingExecutionIn(BaseModel):
    action_type: str = Field(...)
    before_state: dict[str, Any] = Field(default_factory=dict)


class FindingValidationIn(BaseModel):
    after_state: dict[str, Any] = Field(default_factory=dict)
    regressed: bool = False


class BatchResourceLookupIn(BaseModel):
    subscription_id: str
    resource_ids: list[str] = Field(..., min_length=1, max_length=25)
    timespan: str = Field("P7D")
    include_metrics: bool = True
    include_advanced_analysis: bool = True


class BulkResourceTagsIn(BaseModel):
    subscription_id: str
    resource_ids: list[str] = Field(..., min_length=1, max_length=50)
    tags: dict[str, str] = Field(default_factory=dict)


class ResourceTagsIn(BaseModel):
    tags: dict[str, str] = Field(default_factory=dict)

@router.post("/optimize/analyze", tags=["Optimization Engine"],
          summary="Run optimization analysis on DB inventory or live Azure (admin)")
def run_analysis(
    req: AnalyzeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    DB-first analysis (default):
    - Queues a batched background job (one component at a time) to avoid memory spikes
    - Persists findings when the job completes

    Live analysis (data_source=live, admin only):
    - Fetches fresh Azure inventory before analyzing (synchronous)
    """
    require_admin_user(request)
    ensure_subscription_known(db, req.subscription_id)
    if req.data_source == "db":
        scoped = bool(req.components)
        try:
            job = create_analysis_job(
                db,
                subscription_id=req.subscription_id,
                profile=req.profile,
                engine_version=req.engine_version,
                rule_overrides=req.rule_overrides,
                scope_components=req.components,
            )
            background_tasks.add_task(execute_batch_job, job.id)
            return {
                "status": "queued",
                "job_id": job.id,
                "analysis_mode": "scoped" if scoped else "full",
                "message": (
                    "Scoped analysis started in the background using synced database inventory."
                    if scoped
                    else "Analysis started in the background using synced database inventory."
                ),
                "subscription_id": req.subscription_id.lower(),
                "engine_version": req.engine_version.lower(),
                "data_source": "db",
            }
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _run_live_analysis(req, db)


@router.post("/optimize/analyze/batch", tags=["Optimization Engine"],
          summary="Start batched DB analysis (one component per step, admin)")
def start_batch_analysis(
    req: AnalyzeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Queue a background job that analyzes synced inventory component-by-component."""
    require_admin_user(request)
    ensure_subscription_known(db, req.subscription_id)
    if req.data_source != "db":
        raise HTTPException(400, "Batch analysis only supports data_source=db")

    try:
        job = create_analysis_job(
            db,
            subscription_id=req.subscription_id,
            profile=req.profile,
            engine_version=req.engine_version,
            rule_overrides=req.rule_overrides,
            scope_components=req.components,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(execute_batch_job, job.id)
    return serialize_job(job)


@router.get("/optimize/jobs/{job_id}", tags=["Optimization Engine"],
         summary="Get batch analysis job status and per-component progress")
def get_analysis_job(
    job_id: str = Path(...),
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_job_accessible, ensure_subscription_known, require_subscription_id

    ensure_subscription_known(db, require_subscription_id(subscription_id))
    from app.batch_analyzer import expire_stale_analysis_jobs

    sub = require_subscription_id(subscription_id)
    expire_stale_analysis_jobs(db, subscription_id=sub)
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    ensure_job_accessible(db, job, subscription_id)
    return serialize_job(job)


@router.post("/optimize/jobs/{job_id}/cancel", tags=["Optimization Engine"],
          summary="Cancel a queued or running analysis job (admin)")
def cancel_analysis_job_endpoint(
    request: Request,
    job_id: str = Path(...),
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    from app.batch_analyzer import cancel_analysis_job, expire_stale_analysis_jobs, serialize_job
    from app.validators import ensure_subscription_known, require_subscription_id

    require_admin_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    expire_stale_analysis_jobs(db, subscription_id=sub)
    try:
        job = cancel_analysis_job(db, job_id, sub)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return serialize_job(job)


@router.get("/optimize/jobs", tags=["Optimization Engine"],
         summary="List recent batch analysis jobs")
def list_analysis_jobs(
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    limit: int = Query(20, ge=1, le=100),
    active_only: bool = Query(False, description="Return only queued or running jobs"),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_subscription_known, require_subscription_id

    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    from app.batch_analyzer import expire_stale_analysis_jobs

    expire_stale_analysis_jobs(db, subscription_id=sub)
    q = db.query(AnalysisJob).filter(AnalysisJob.subscription_id == sub)
    if active_only:
        q = q.filter(AnalysisJob.status.in_(["queued", "running"]))
    q = q.order_by(AnalysisJob.created_at.desc())
    jobs = q.limit(limit).all()
    return [serialize_job(j) for j in jobs]
def _run_live_analysis(req: AnalyzeRequest, db: Session) -> dict:
    """Fetch live Azure data, analyze, and persist results to the database."""
    from app.auth import arm_auth_context, get_token

    sub = req.subscription_id

    # 1. Fetch all resources in parallel
    import concurrent.futures
    fetch_tasks = {
        "vms":            lambda: resource_client.list_vms(sub, include_instance_view=False),
        "vmss":           lambda: resource_client.list_vm_scale_sets(sub),
        "disks":          lambda: resource_client.list_disks(sub),
        "snapshots":      lambda: resource_client.list_snapshots(sub),
        "aks":            lambda: resource_client.list_aks_clusters(sub),
        "storage":        lambda: resource_client.list_storage_accounts(sub),
        "public_ips":     lambda: resource_client.list_public_ips(sub),
        "load_balancers": lambda: resource_client.list_load_balancers(sub),
        "app_gateways":   lambda: resource_client.list_application_gateways(sub),
        "app_services":   lambda: resource_client.list_app_services(sub),
        "app_service_plans": lambda: resource_client.list_app_service_plans(sub),
        "network_interfaces": lambda: resource_client.list_network_interfaces(sub),
        "nat_gateways":   lambda: resource_client.list_nat_gateways(sub),
        "redis_caches":   lambda: resource_client.list_redis_caches(sub),
        "sql_servers":    lambda: resource_client.list_sql_servers(sub),
        "cosmosdb":       lambda: resource_client.list_cosmosdb(sub),
        "keyvaults":      lambda: resource_client.list_keyvaults(sub),
        "nsgs":           lambda: resource_client.list_network_security_groups(sub),
        "postgresql":     lambda: resource_client.list_postgresql_flexible(sub),
        "acr":            lambda: resource_client.list_container_registries(sub),
        "budgets":        lambda: cost_client.list_budgets(sub),
    }

    fetched: dict = {}
    errors:  dict = {}
    with arm_auth_context(db=db, token=get_token(db)):
        with concurrent.futures.ThreadPoolExecutor(max_workers=arm_fetch_workers()) as pool:
            futs = {pool.submit(fn): key for key, fn in fetch_tasks.items()}
            for fut in concurrent.futures.as_completed(futs):
                key = futs[fut]
                try:
                    fetched[key] = fut.result()
                except Exception as exc:
                    log.warning("fetch.failed", resource=key, error=str(exc))
                    errors[key]  = str(exc)
                    fetched[key] = []

    LIVE_FETCH_ENRICH: dict[str, str] = {
        "vms": "compute/vm",
        "vmss": "compute/vmss",
        "disks": "compute/disk",
        "snapshots": "compute/snapshot",
        "aks": "containers/aks",
        "storage": "storage/account",
        "public_ips": "network/publicip",
        "load_balancers": "network/loadbalancer",
        "app_gateways": "network/appgateway",
        "app_services": "appservice/webapp",
        "app_service_plans": "appservice/plan",
        "network_interfaces": "network/nic",
        "nat_gateways": "network/nat",
        "redis_caches": "database/redis",
        "sql_servers": "database/sql",
        "cosmosdb": "database/cosmosdb",
        "keyvaults": "security/keyvault",
        "nsgs": "network/nsg",
        "postgresql": "database/postgresql",
        "acr": "containers/acr",
    }
    for key, canonical in LIVE_FETCH_ENRICH.items():
        if not fetched.get(key):
            continue
        try:
            fetched[key] = enrich_arm_resources_for_type(
                resource_client, sub, fetched[key], canonical,
            )
        except Exception as exc:
            log.warning("fetch.arm_enrich_failed", resource=key, error=str(exc))

    try:
        from app.vm_uptime import enrich_vmss_list_with_instance_uptime
        if fetched.get("vmss"):
            fetched["vmss"] = enrich_vmss_list_with_instance_uptime(
                resource_client, sub, fetched["vmss"],
            )
    except Exception as exc:
        log.warning("fetch.vmss_uptime_enrich_failed", error=str(exc))

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
        with concurrent.futures.ThreadPoolExecutor(max_workers=arm_fetch_workers()) as pool:
            for cid, pools in pool.map(_fetch_pools, clusters):
                aks_node_pools[cid] = pools

    # 2b. Fetch SQL databases for each server
    sql_databases: list[dict] = []
    sql_servers = fetched.get("sql_servers", [])

    def _fetch_sql_dbs(server):
        sid = server.get("id", "")
        rg  = sid.split("/resourceGroups/")[1].split("/")[0] if "/resourceGroups/" in sid else ""
        sname = server.get("name", "")
        try:
            return resource_client.list_sql_databases(sub, rg, sname)
        except Exception:
            return []

    if sql_servers:
        with concurrent.futures.ThreadPoolExecutor(max_workers=arm_fetch_workers()) as pool:
            for dbs in pool.map(_fetch_sql_dbs, sql_servers):
                sql_databases.extend(dbs)

    # 3. Cost by resource for savings estimates and monitor fetch prioritization
    from app.cost_db import resource_cost_map_from_db

    cost_by_resource: dict = {}
    try:
        cost_map = resource_cost_map_from_db(db, sub, "MonthToDate")
        if cost_map:
            cost_by_resource = {
                rid: {
                    "pretax": d.get("pretax", 0),
                    "usd": d.get("usd", 0),
                    "currency": d.get("currency", "USD"),
                }
                for rid, d in cost_map.items()
            }
        else:
            log.info("cost_by_resource.empty_db", subscription_id=sub)
    except Exception as exc:
        log.warning("cost_by_resource.failed", error=str(exc))

    # 4. Fetch Azure Monitor metrics (spec-driven for all resource types with profiles)
    vm_metrics: dict = {}
    node_metrics: dict = {}
    resource_metrics: dict = {}
    resource_facts: dict = {}
    monitor_stats: dict = {}
    if req.include_metrics:
        from app.metrics_loader import (
            analysis_inventory_buckets,
            group_resources_by_canonical_type,
            load_k8s_node_metrics,
        )
        from app.monitor_metrics import load_azure_monitor_metrics

        inventory_buckets = analysis_inventory_buckets(
            vms=fetched.get("vms", []),
            vmss=fetched.get("vmss", []),
            disks=fetched.get("disks", []),
            snapshots=fetched.get("snapshots", []),
            aks_clusters=clusters,
            container_registries=fetched.get("acr", []),
            storage=fetched.get("storage", []),
            public_ips=fetched.get("public_ips", []),
            load_balancers=fetched.get("load_balancers", []),
            app_gateways=fetched.get("app_gateways", []),
            nat_gateways=fetched.get("nat_gateways", []),
            sql_servers=fetched.get("sql_servers", []),
            sql_databases=sql_databases,
            cosmosdb=fetched.get("cosmosdb", []),
            postgresql=fetched.get("postgresql", []),
            redis_caches=fetched.get("redis_caches", []),
            app_services=fetched.get("app_services", []),
            app_service_plans=fetched.get("app_service_plans", []),
            keyvaults=fetched.get("keyvaults", []),
            network_interfaces=fetched.get("network_interfaces", []),
            nsgs=fetched.get("nsgs", []),
        )
        grouped = group_resources_by_canonical_type(inventory_buckets)
        resource_metrics, resource_facts, monitor_stats = load_azure_monitor_metrics(
            grouped,
            cost_by_resource,
            timespan=req.timespan_metrics,
            db=db,
        )
        try:
            node_metrics = load_k8s_node_metrics(db, clusters)
        except Exception as exc:
            log.warning("live_analysis.k8s_metrics_failed", error=str(exc))
        vm_metrics = {
            rid: payload
            for rid, payload in resource_metrics.items()
            if "/virtualmachines/" in rid or "/virtualmachinescalesets/" in rid
        }

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
            vmss=fetched.get("vmss", []),
            disks=fetched.get("disks", []),
            snapshots=fetched.get("snapshots", []),
            aks_clusters=clusters,
            aks_node_pools=aks_node_pools,
            storage=fetched.get("storage", []),
            public_ips=fetched.get("public_ips", []),
            load_balancers=fetched.get("load_balancers", []),
            app_gateways=fetched.get("app_gateways", []),
            app_services=fetched.get("app_services", []),
            app_service_plans=fetched.get("app_service_plans", []),
            network_interfaces=fetched.get("network_interfaces", []),
            nat_gateways=fetched.get("nat_gateways", []),
            redis_caches=fetched.get("redis_caches", []),
            sql_databases=sql_databases,
            cosmosdb=fetched.get("cosmosdb", []),
            keyvaults=fetched.get("keyvaults", []),
            nsgs=fetched.get("nsgs", []),
            postgresql=fetched.get("postgresql", []),
            container_registries=fetched.get("acr", []),
            vm_metrics=vm_metrics,
            node_metrics=node_metrics,
            resource_metrics=resource_metrics,
            resource_facts=resource_facts,
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
            app_services=fetched.get("app_services", []),
            app_service_plans=fetched.get("app_service_plans", []),
            network_interfaces=fetched.get("network_interfaces", []),
            nat_gateways=fetched.get("nat_gateways", []),
            redis_caches=fetched.get("redis_caches", []),
            sql_servers=fetched.get("sql_servers", []),
            sql_databases=sql_databases,
            cosmosdb=fetched.get("cosmosdb", []),
            keyvaults=fetched.get("keyvaults", []),
            vm_metrics=vm_metrics,
            cost_by_resource=cost_by_resource,
            budgets=fetched.get("budgets", []),
        )
        result["engine_version"] = "standard"

    result = append_cost_export_findings(
        db,
        sub,
        result,
        profile=req.profile,
        rule_overrides=req.rule_overrides,
        engine_version=engine_version,
    )

    result = enrich_analysis_with_ai(db, result, include_ai=req.include_ai)

    if engine_version == "extended":
        from app.analysis_summary import summarize_findings
        from app.commitment_findings import dedupe_commitment_findings

        findings = result.get("findings") or []
        if fetched.get("vms"):
            from app.vm_sizing_persist import supplement_vm_rightsizing_findings

            merged_overrides = {**get_effective_config(db, req.profile), **req.rule_overrides}
            findings = supplement_vm_rightsizing_findings(
                findings,
                subscription_id=sub,
                vms=fetched.get("vms") or [],
                vm_metrics=vm_metrics or {},
                cost_by_resource={
                    normalize_arm_id(rid_key): float(d.get("usd") or d.get("pretax") or 0)
                    for rid_key, d in (cost_by_resource or {}).items()
                } if cost_by_resource else {},
                rule_overrides=merged_overrides,
            )
        findings = dedupe_commitment_findings(findings)
        result["findings"] = findings
        result["summary"] = summarize_findings(
            findings,
            engine_version,
            metrics_context=result.get("metrics_context"),
        )

    run_id = persist_optimization_run(
        db,
        subscription_id=sub,
        profile=req.profile,
        engine_version=engine_version,
        result=result,
        data_source="live",
    )

    result["run_id"]         = run_id
    result["data_source"]    = "live"
    result["fetch_errors"]   = errors
    result["resources_analyzed"] = {k: len(v) for k, v in fetched.items()}
    if req.include_metrics:
        from app.metrics_loader import analysis_metrics_summary
        result["metrics_context"] = analysis_metrics_summary(
            vm_metrics, node_metrics, resource_metrics, resource_facts, monitor_stats,
        )
    return result

@router.get("/optimize/runs", tags=["Optimization Engine"],
         summary="List past optimization runs with savings totals")
def list_runs(
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    limit:           int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_subscription_known, require_subscription_id

    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    q = db.query(OptimizationRun).filter(OptimizationRun.subscription_id == sub).order_by(OptimizationRun.analyzed_at.desc())
    runs = q.limit(limit).all()
    from app.batch_analyzer import job_history_snapshot, jobs_by_run_ids

    job_map = jobs_by_run_ids(db, sub, [r.id for r in runs])
    return [{
        "id": r.id, "subscription_id": r.subscription_id,
        "profile": r.profile,
        "engine_version": getattr(r, "engine_version", None) or "standard",
        "total_findings": r.total_findings,
        "critical": r.critical_count,
        "high": r.high_count,
        "critical_count": r.critical_count,
        "high_count": r.high_count,
        "medium": r.medium_count, "low": r.low_count,
        "total_savings_usd": r.total_savings_usd,
        "analyzed_at": str(r.analyzed_at),
        "job": job_history_snapshot(job_map.get(r.id)),
    } for r in runs]


def _coerce_evidence_dict(value: Any) -> dict:
    """Normalize persisted evidence payloads for API enrichment."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


@router.get("/optimize/runs/{run_id}", tags=["Optimization Engine"],
         summary="Full findings for a specific optimization run")
def get_run(
    run_id: str = Path(...),
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_run_accessible, ensure_subscription_known, require_subscription_id

    ensure_subscription_known(db, require_subscription_id(subscription_id))
    run = db.query(OptimizationRun).filter(OptimizationRun.id == run_id).first()
    ensure_run_accessible(db, run, subscription_id)
    from app.batch_analyzer import job_for_run, job_history_snapshot

    job_row = job_for_run(db, run.subscription_id or "", run.id)
    raw_findings = json.loads(run.findings_json or "[]")
    disk_props = disk_inventory_properties_map(
        db,
        run.subscription_id or "",
        [f.get("resource_id") for f in raw_findings if f.get("resource_id")],
    )
    findings = [
        enrich_finding_for_api({
            "rule_id": f.get("rule_id"),
            "rule_name": f.get("rule_name"),
            "category": f.get("category"),
            "severity": f.get("severity"),
            "resource_id": f.get("resource_id"),
            "resource_name": f.get("resource_name"),
            "resource_type": f.get("resource_type"),
            "resource_group": f.get("resource_group"),
            "location": f.get("location"),
            "detail": f.get("detail"),
            "recommendation": f.get("recommendation"),
            "estimated_savings_usd": f.get("estimated_savings_usd"),
            "annualized_savings_usd": f.get("annualized_savings_usd"),
            "waste_score": f.get("waste_score"),
            "confidence_score": f.get("confidence_score"),
            "action_priority": f.get("action_priority"),
            "impact": f.get("impact"),
            "evidence": _coerce_evidence_dict(f.get("evidence")),
            "status": f.get("status", "open"),
        }, inventory_properties=disk_props.get(normalize_arm_id(f.get("resource_id") or "")))
        for f in raw_findings
    ]
    return {
        "id": run.id, "subscription_id": run.subscription_id,
        "profile": run.profile,
        "engine_version": getattr(run, "engine_version", None) or "standard",
        "total_findings": run.total_findings,
        "total_savings_usd": run.total_savings_usd,
        "analyzed_at": str(run.analyzed_at),
        "findings": findings,
        "job": job_history_snapshot(job_row),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  ENGINE CONFIGURATION (Rules + Profiles)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/optimize/rules", tags=["Engine Config"],
         summary="List all rules with component-specific settings")
def list_rules():
    """Returns every rule with only the settings that apply to it."""
    return list_all_rules()


@router.get("/optimize/rules/by-component", tags=["Engine Config"],
         summary="Rules grouped by Azure component")
def list_rules_by_component():
    return list_components()


@router.get("/optimize/rules/by-resource", tags=["Engine Config"],
         summary="Applicable rules per canonical resource type")
def list_rules_by_resource(
    canonical_type: Optional[str] = Query(None, description="Filter by canonical type, e.g. compute/vm"),
):
    if canonical_type:
        rule_ids = list_rules_for_canonical_type(canonical_type)
        return {
            "canonical_type": canonical_type.strip().lower(),
            "rule_count": len(rule_ids),
            "rule_ids": rule_ids,
        }
    return {"count": len(canonical_resource_rule_catalog()), "resources": canonical_resource_rule_catalog()}


@router.get("/optimize/technical-fetch-specs", tags=["Engine Config"],
         summary="Technical fetch definitions per Azure resource type")
def get_technical_fetch_specs(
    canonical_type: Optional[str] = Query(None, description="Filter by canonical type, e.g. compute/vm"),
):
    """Returns ARM properties to sync, technical fields, and usage metrics per resource type."""
    specs = list_technical_fetch_specs()
    if canonical_type:
        key = canonical_type.strip().lower()
        specs = [s for s in specs if s["canonical_type"] == key]
    return {"count": len(specs), "specs": specs}


@router.get("/optimize/sub-engines", tags=["Engine Config"],
         summary="Per-resource optimization sub-engines aligned to analysis batches")
def get_sub_engines():
    from app.optimizer.resource_engines import list_sub_engines

    engines = list_sub_engines()
    return {"count": len(engines), "sub_engines": engines}


@router.get("/optimize/config/{profile}", tags=["Engine Config"],
         summary="Get all rule overrides for a named profile (admin)")
def get_profile_config(
    request: Request,
    profile: str = Path(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
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


@router.post("/optimize/config/{profile}", tags=["Engine Config"],
          summary="Create or update a rule override in a profile")
def upsert_config(
    request: Request,
    profile: str = Path(..., description="Profile name e.g. default, aggressive, conservative"),
    body:    RuleConfigIn = ...,
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    if body.rule_id != GLOBAL_CONFIG_KEY and not is_known_rule(body.rule_id):
        raise HTTPException(400, f"Unknown rule_id '{body.rule_id}'. Valid: {sorted(ALL_KNOWN_RULE_IDS)}")
    row = upsert_rule_config(
        db, profile=profile, rule_id=body.rule_id,
        overrides=body.overrides, enabled=body.enabled,
        description=body.description or "",
    )
    return {
        "profile":   profile,
        "rule_id":   row.rule_id,
        "enabled":   row.enabled,
        "overrides": json.loads(row.overrides_json),
        "updated_at": str(row.updated_at),
    }


@router.delete("/optimize/config/{profile}/{rule_id}", tags=["Engine Config"],
            summary="Remove a rule override (resets to default thresholds)")
def delete_config(
    request: Request,
    profile: str = Path(...),
    rule_id: str = Path(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    deleted = delete_rule_config(db, profile=profile, rule_id=rule_id)
    if not deleted:
        raise HTTPException(404, "Config not found")
    return {"deleted": True, "profile": profile, "rule_id": rule_id}


@router.post("/optimize/config/{profile}/reanalyze", tags=["Engine Config"],
          summary="Re-run recommendations after rule changes (DB inventory + cached metrics, no Azure fetch)")
def reanalyze_after_rule_config(
    request: Request,
    profile: str = Path(..., description="Profile whose rule overrides should be applied"),
    background_tasks: BackgroundTasks = ...,
    db: Session = Depends(get_db),
    engine_version: str = Query("extended", description="standard or extended"),
):
    require_admin_user(request)
    return queue_rule_config_reanalysis(
        db,
        background_tasks,
        profile=profile,
        engine_version=engine_version.lower(),
    )


@router.get("/optimize/config", tags=["Engine Config"],
         summary="List all profiles that have been configured (admin)")
def list_profiles(request: Request, db: Session = Depends(get_db)):
    require_admin_user(request)
    rows = db.query(EngineConfig.profile).distinct().all()
    return {"profiles": [r[0] for r in rows]}


class ProfileValidateIn(BaseModel):
    draft_overrides: dict[str, dict] = Field(
        default_factory=dict,
        description="Optional unsaved rule overrides to validate before save",
    )


@router.post("/optimize/config/{profile}/validate", tags=["Engine Config"],
          summary="Validate rule overrides for a profile (admin)")
def validate_config(
    request: Request,
    profile: str = Path(...),
    body: ProfileValidateIn | None = None,
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    draft = body.draft_overrides if body else None
    return validate_profile_config(db, profile, draft=draft)


@router.get("/optimize/config/compare", tags=["Engine Config"],
         summary="Compare effective rule overrides across profiles (admin)")
def compare_config_profiles(
    request: Request,
    profiles: str = Query(
        "default,aggressive,conservative",
        description="Comma-separated profile names",
    ),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    names = tuple(p.strip() for p in profiles.split(",") if p.strip())
    payload = compare_profiles(db, *names)
    payload["metadata"] = {name: get_profile_metadata(db, name) for name in names}
    return payload


@router.get("/optimize/config/global/defaults", tags=["Engine Config"],
         summary="Default global filter and severity settings")
def global_config_defaults(request: Request):
    require_authenticated_user(request)
    from app.optimizer.engine_filters import DEFAULT_GLOBAL_CONFIG

    return {"rule_id": GLOBAL_CONFIG_KEY, "defaults": DEFAULT_GLOBAL_CONFIG}


@router.get("/optimize/workflows/templates", tags=["Engine Config"],
         summary="Workflow routing templates linked to optimization rules")
def list_workflow_templates(request: Request):
    require_authenticated_user(request)
    from app.optimizer.workflow_rules import DEFAULT_WORKFLOW_TEMPLATES

    return {"count": len(DEFAULT_WORKFLOW_TEMPLATES), "templates": DEFAULT_WORKFLOW_TEMPLATES}


# ══════════════════════════════════════════════════════════════════════════════
#  FINDINGS — Remediation Tracking
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/optimize/findings/cleanup", tags=["Findings"],
          summary="Clean duplicate or supersede stale open recommendations (admin only)")
def cleanup_findings(
    request: Request,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    mode: str = Query(
        "dedupe",
        description="dedupe — collapse duplicate open rows; supersede — resolve all open (use before re-analyze)",
    ),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_subscription_known, require_subscription_id
    from app.analysis_persist import cleanup_duplicate_open_findings, supersede_open_findings

    require_admin_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    mode_norm = (mode or "dedupe").strip().lower()
    if mode_norm not in {"dedupe", "supersede"}:
        raise HTTPException(400, "mode must be dedupe or supersede")

    duplicates_resolved = cleanup_duplicate_open_findings(db, sub, commit=False)
    superseded = 0
    if mode_norm == "supersede":
        superseded = supersede_open_findings(db, sub, commit=False)

    db.commit()
    return {
        "status": "ok",
        "subscription_id": sub,
        "mode": mode_norm,
        "duplicates_resolved": duplicates_resolved,
        "open_superseded": superseded,
    }


@router.get("/optimize/findings", tags=["Findings"],
         summary="Query findings with filters — subscription, severity, category, status")
def list_findings(
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    severity:        Optional[str] = Query(None, description="CRITICAL|HIGH|MEDIUM|LOW|INFO"),
    category:        Optional[str] = Query(None, description="COMPUTE|KUBERNETES|STORAGE|NETWORK|DATABASE|SECURITY|COST"),
    status:          Optional[str] = Query(None, description="open|acknowledged|implemented|resolved|ignored"),
    rule_id:         Optional[str] = Query(None),
    resource_id:     Optional[str] = Query(None, description="Filter by Azure resource ID (case-insensitive)"),
    limit:           int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    from app.validators import ensure_subscription_known, require_subscription_id
    from sqlalchemy import func

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    if not status or status.lower() == "open":
        from app.analysis_persist import cleanup_duplicate_open_findings
        cleanup_duplicate_open_findings(db, subscription_id)
    q = db.query(OptimizationFinding).order_by(
        OptimizationFinding.detected_at.desc()
    )
    if subscription_id: q = q.filter(func.lower(OptimizationFinding.subscription_id) == subscription_id)
    if severity:        q = q.filter(OptimizationFinding.severity  == severity.upper())
    if category:        q = q.filter(OptimizationFinding.category  == category.upper())
    status_norm = (status or "").lower()
    if status and status_norm not in {"implemented"}:
        q = q.filter(OptimizationFinding.status == status_norm)
    if rule_id:         q = q.filter(OptimizationFinding.rule_id   == rule_id.upper())
    if resource_id:     q = q.filter(func.lower(OptimizationFinding.resource_id) == resource_id.lower())

    if status_norm == "implemented":
        from app.recommendation_execution import implemented_findings_for_subscription

        findings = implemented_findings_for_subscription(db, subscription_id or "")
        if severity:
            findings = [f for f in findings if f.severity == severity.upper()]
        if category:
            findings = [f for f in findings if f.category == category.upper()]
        if rule_id:
            findings = [f for f in findings if f.rule_id == rule_id.upper()]
        if resource_id:
            rid = resource_id.lower()
            findings = [f for f in findings if (f.resource_id or "").lower() == rid]
        findings = findings[:limit]
    elif status_norm == "resolved":
        from app.finding_dedupe import actionable_resolved_rows, collect_open_identity_keys

        open_rows = (
            db.query(OptimizationFinding)
            .filter(
                func.lower(OptimizationFinding.subscription_id) == subscription_id,
                OptimizationFinding.status == "open",
            )
            .all()
        )
        open_keys = collect_open_identity_keys(open_rows)
        resolved_rows = q.all()
        findings = actionable_resolved_rows(resolved_rows, open_keys)[:limit]
    else:
        findings = q.limit(limit).all()
        if not status or status_norm == "open":
            from app.analysis_persist import dedupe_open_findings_for_display
            findings = dedupe_open_findings_for_display(findings)
    disk_props = disk_inventory_properties_map(
        db,
        subscription_id or "",
        [f.resource_id for f in findings],
    )
    enriched_list = [
        enrich_finding_for_api({
            "id": f.id, "run_id": f.run_id,
            "rule_id": f.rule_id, "rule_name": f.rule_name,
            "category": f.category, "severity": f.severity,
            "resource_id": f.resource_id, "resource_name": f.resource_name,
            "resource_type": f.resource_type,
            "resource_group": f.resource_group, "location": f.location,
            "detail": f.detail, "recommendation": f.recommendation,
            "estimated_savings_usd": f.estimated_savings_usd,
            "annualized_savings_usd": getattr(f, "annualized_savings_usd", None),
            "waste_score": f.waste_score,
            "confidence_score": getattr(f, "confidence_score", None),
            "action_priority": getattr(f, "action_priority", None),
            "impact": getattr(f, "impact", None),
            "evidence": _coerce_evidence_dict(json.loads(getattr(f, "evidence_json", None) or "{}")),
            "status": f.status, "detected_at": str(f.detected_at),
            "resolved_at": str(f.resolved_at) if f.resolved_at else None,
            "chain_id": getattr(f, "chain_id", None),
            "chain_step": getattr(f, "chain_step", None),
            "chain_total": getattr(f, "chain_total", None),
        }, inventory_properties=disk_props.get(normalize_arm_id(f.resource_id or "")))
        for f in findings
    ]

    def _attach_ai_flags(payload: dict) -> dict:
        ev = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
        ai_block = ev.get("ai_insight") if isinstance(ev.get("ai_insight"), dict) else {}
        payload["ai_enriched"] = bool(ai_block)
        if ai_block.get("risk_level"):
            payload["ai_risk_level"] = ai_block["risk_level"]
        return payload

    return [_attach_ai_flags(item) for item in enriched_list]


@router.patch("/optimize/findings/{finding_id}/status", tags=["Findings"],
           summary="Update remediation status of a finding")
def update_finding_status(
    request: Request,
    finding_id: str = Path(...),
    body:       FindingStatusIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    user = require_authenticated_user(request)
    sub = ensure_subscription_known(db, subscription_id)
    valid = {"open", "acknowledged", "resolved", "ignored"}
    if body.status not in valid:
        raise HTTPException(400, f"status must be one of: {valid}")
    if body.status in {"resolved", "open"} and user.get("role") != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    f = db.query(OptimizationFinding).filter(OptimizationFinding.id == finding_id).first()
    if not f:
        raise HTTPException(404, "Finding not found")
    if (f.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Finding not found")
    from app.analysis_persist import refresh_resource_analysis_summary

    _apply_finding_status_update(db, f, body.status, user=user)
    db.commit()
    refresh_resource_analysis_summary(
        db,
        subscription_id=f.subscription_id,
        resource_id=f.resource_id or "",
    )
    return {"id": f.id, "status": f.status, "resolved_at": str(f.resolved_at) if f.resolved_at else None}


def _apply_finding_status_update(
    db: Session,
    finding: OptimizationFinding,
    status: str,
    *,
    user: dict | None = None,
) -> None:
    from datetime import datetime, timezone
    from app.finding_activity import log_finding_status_change

    previous = (finding.status or "").lower()
    normalized = status.lower()
    finding.status = normalized
    if normalized == "resolved":
        finding.resolved_at = datetime.now(timezone.utc)
    elif normalized == "open":
        finding.resolved_at = None
    if previous != normalized:
        log_finding_status_change(
            db,
            finding_id=finding.id,
            subscription_id=finding.subscription_id or "",
            from_status=previous or None,
            to_status=normalized,
            user=user,
        )


@router.patch("/optimize/findings/bulk-status", tags=["Findings"],
           summary="Update remediation status for multiple findings")
def bulk_update_finding_status(
    request: Request,
    body: BulkFindingStatusIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    user = require_authenticated_user(request)
    sub = ensure_subscription_known(db, subscription_id)
    valid = {"open", "acknowledged", "resolved", "ignored"}
    if body.status not in valid:
        raise HTTPException(400, f"status must be one of: {valid}")
    if body.status in {"resolved", "open"} and user.get("role") != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    unique_ids = list(dict.fromkeys(body.finding_ids))
    rows = (
        db.query(OptimizationFinding)
        .filter(OptimizationFinding.id.in_(unique_ids))
        .all()
    )
    if len(rows) != len(unique_ids):
        found = {row.id for row in rows}
        missing = [fid for fid in unique_ids if fid not in found]
        raise HTTPException(404, f"Finding(s) not found: {', '.join(missing[:5])}")

    for row in rows:
        if (row.subscription_id or "").lower() != sub:
            raise HTTPException(404, f"Finding not found: {row.id}")

    for row in rows:
        _apply_finding_status_update(db, row, body.status, user=user)
    db.commit()

    from app.analysis_persist import refresh_resource_analysis_summary

    resource_ids = {row.resource_id or "" for row in rows if row.resource_id}
    for resource_id in resource_ids:
        refresh_resource_analysis_summary(
            db,
            subscription_id=sub,
            resource_id=resource_id,
        )
    return {
        "updated": len(rows),
        "status": body.status,
        "finding_ids": unique_ids,
    }


@router.get("/optimize/findings/{finding_id}/activity", tags=["Findings"],
         summary="Activity log for a finding")
def finding_activity(
    finding_id: str = Path(...),
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    from app.finding_activity import list_finding_activity
    from app.validators import ensure_subscription_known, require_subscription_id

    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    f = db.query(OptimizationFinding).filter(OptimizationFinding.id == finding_id).first()
    if not f or (f.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Finding not found")
    return {"items": list_finding_activity(db, finding_id=finding_id, limit=limit)}


@router.post("/optimize/findings/{finding_id}/execute", tags=["Findings"],
          summary="Log execution of a recommendation")
def log_finding_execution(
    request: Request,
    finding_id: str = Path(...),
    body: FindingExecutionIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    from app.recommendation_execution import log_execution, serialize_execution
    from app.validators import ensure_subscription_known, require_subscription_id

    user = require_authenticated_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    f = db.query(OptimizationFinding).filter(OptimizationFinding.id == finding_id).first()
    if not f or (f.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Finding not found")
    row = log_execution(
        db,
        finding_id=finding_id,
        executed_by=user.get("display_name") or user.get("username") or user.get("id", "user"),
        action_type=body.action_type,
        before_state=body.before_state,
    )
    db.commit()
    return serialize_execution(row)


@router.post("/optimize/findings/{finding_id}/validate", tags=["Findings"],
          summary="Validate a logged recommendation execution")
def validate_finding_execution(
    request: Request,
    finding_id: str = Path(...),
    body: FindingValidationIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    from app.recommendation_execution import serialize_execution, validate_execution
    from app.models import RecommendationExecution
    from app.validators import ensure_subscription_known, require_subscription_id

    require_authenticated_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    f = db.query(OptimizationFinding).filter(OptimizationFinding.id == finding_id).first()
    if not f or (f.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Finding not found")
    row = (
        db.query(RecommendationExecution)
        .filter(RecommendationExecution.finding_id == finding_id)
        .order_by(RecommendationExecution.executed_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(404, "No execution record found for this finding")
    validate_execution(db, row, after_state=body.after_state, regressed=body.regressed)
    db.commit()
    return serialize_execution(row)


@router.get("/optimize/findings/summary", tags=["Findings"],
         summary="Aggregated findings summary by status, severity, and category")
def findings_summary(
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    from app.findings_summary import build_findings_summary
    from app.validators import ensure_subscription_known, require_subscription_id
    from app.analysis_persist import cleanup_duplicate_open_findings

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    cleanup_duplicate_open_findings(db, subscription_id)
    from app.perf_cache import cached_findings_summary

    return cached_findings_summary(
        subscription_id,
        lambda: build_findings_summary(db, subscription_id),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  AZURE ADVISOR  (Microsoft.Advisor snapshots — distinct from GET /advisor)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/optimize/advisor/generate", tags=["Azure Advisor"],
          summary="Trigger Azure Advisor recommendation generation (admin)")
def trigger_advisor_generate(
    request: Request,
    subscription_id: str = Query(...),
    wait: bool = Query(False, description="Poll until recommendations refresh or timeout"),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    require_admin_user(request)
    from app.advisor_sync import sync_azure_advisor_recommendations
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    try:
        return sync_azure_advisor_recommendations(
            subscription_id,
            db,
            token,
            trigger_generate=True,
            wait_for_generate=wait,
        )
    except Exception as exc:
        log.exception("advisor_generate_failed", subscription_id=subscription_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/optimize/advisor/sync", tags=["Azure Advisor"],
          summary="Sync Azure Advisor recommendations into the database (admin)")
def trigger_advisor_sync(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    require_admin_user(request)
    from app.advisor_sync import sync_azure_advisor_recommendations
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    try:
        return sync_azure_advisor_recommendations(subscription_id, db, token)
    except Exception as exc:
        log.exception("advisor_sync_failed", subscription_id=subscription_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/optimize/advisor/list", tags=["Azure Advisor"],
         summary="List stored Azure Advisor recommendations")
def list_azure_advisor_recommendations(
    subscription_id: str = Query(...),
    category: str | None = Query(None, description="Cost, Performance, Security, etc."),
    impact: str | None = Query(None),
    status: str | None = Query("Active"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    from app.advisor_sync import list_stored_advisor_recommendations
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    return list_stored_advisor_recommendations(
        db,
        subscription_id,
        category=category,
        impact=impact,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/optimize/actions/list", tags=["Optimization actions"],
         summary="List synthesized optimization actions")
def list_optimization_actions_route(
    subscription_id: str = Query(...),
    workflow_status: str | None = Query(None),
    action_type: str | None = Query(None),
    confidence: str | None = Query(None),
    resource_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    from app.optimization_actions import list_optimization_actions
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    return list_optimization_actions(
        db,
        subscription_id,
        workflow_status=workflow_status,
        action_type=action_type,
        confidence=confidence,
        resource_type=resource_type,
        limit=limit,
        offset=offset,
    )


@router.post("/optimize/actions/decide", tags=["Optimization actions"],
          summary="Run decision engine and synthesize actions (admin)")
def decide_optimization_actions(
    request: Request,
    subscription_id: str = Query(...),
    force_refresh: bool = Query(False),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.optimizer.decision_engine import generate_optimization_actions
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    try:
        return generate_optimization_actions(db, subscription_id, force_refresh=force_refresh)
    except Exception as exc:
        log.exception("decision_engine_failed", subscription_id=subscription_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/optimize/actions/{action_id}", tags=["Optimization actions"],
           summary="Update workflow status or owner for an action")
def patch_optimization_action(
    request: Request,
    action_id: str = Path(...),
    body: ActionWorkflowIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    user = require_authenticated_user(request)
    from app.optimization_actions import serialize_action, update_optimization_action
    from app.validators import ensure_subscription_known, require_subscription_id

    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    if body.workflow_status in {"approved", "executed", "rejected"} and user.get("role") != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.models import OptimizationAction

    row = db.query(OptimizationAction).filter(OptimizationAction.id == action_id).first()
    if not row or (row.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Action not found")

    try:
        update_optimization_action(
            db,
            row,
            workflow_status=body.workflow_status,
            owner=body.owner,
            note=body.note,
            user=user,
            unset_owner=body.clear_owner,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    db.commit()
    return serialize_action(row)


@router.patch("/optimize/actions/bulk-status", tags=["Optimization actions"],
           summary="Bulk update workflow status for actions")
def bulk_patch_optimization_actions(
    request: Request,
    body: BulkActionWorkflowIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    user = require_authenticated_user(request)
    from app.optimization_actions import bulk_update_optimization_actions
    from app.validators import ensure_subscription_known, require_subscription_id

    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    if body.workflow_status in {"approved", "executed", "rejected"} and user.get("role") != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        return bulk_update_optimization_actions(
            db,
            subscription_id=sub,
            action_ids=body.action_ids,
            workflow_status=body.workflow_status,
            user=user,
            note=body.note,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.patch("/optimize/actions/bulk-assign", tags=["Optimization actions"],
           summary="Bulk assign owner to optimization actions")
def bulk_assign_optimization_actions_route(
    request: Request,
    body: BulkActionAssignIn = ...,
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    user = require_authenticated_user(request)
    from app.optimization_actions import bulk_assign_optimization_actions
    from app.validators import ensure_subscription_known, require_subscription_id

    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    try:
        return bulk_assign_optimization_actions(
            db,
            subscription_id=sub,
            action_ids=body.action_ids,
            owner=body.owner,
            user=user,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/optimize/engine/score", tags=["Advanced engine"],
          summary="Score all resources with the advanced optimization engine (admin)")
def score_subscription_advanced(
    request: Request,
    subscription_id: str = Query(...),
    force_rescore: bool = Query(False),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.advanced_scoring import score_subscription
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    try:
        return score_subscription(db, subscription_id, force_rescore=force_rescore)
    except Exception as exc:
        log.exception("advanced_engine_score_failed", subscription_id=subscription_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/optimize/engine/scoreboard", tags=["Advanced engine"],
         summary="List multi-dimensional optimization scorecards")
def get_optimization_scoreboard(
    subscription_id: str = Query(...),
    tier: str | None = Query(None, description="tier1_safe | tier2_balanced | tier3_risky | blocked"),
    resource_type: str | None = Query(None),
    min_score: float | None = Query(None, ge=0, le=100),
    evaluation_date: str | None = Query(None, description="YYYY-MM-DD, defaults to today"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    from app.advanced_scoring import list_scoreboard
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    return list_scoreboard(
        db,
        subscription_id,
        tier=tier,
        resource_type=resource_type,
        min_score=min_score,
        evaluation_date=evaluation_date,
        limit=limit,
        offset=offset,
    )


@router.post("/optimize/rollout/plan", tags=["Advanced engine"],
          summary="Plan rollout stages from tiered optimization actions (admin)")
def plan_rollout(
    request: Request,
    subscription_id: str = Query(...),
    replace_existing: bool = Query(False),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.optimizer.rollout_orchestrator import plan_rollout_stages
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    return plan_rollout_stages(db, subscription_id, replace_existing=replace_existing)


@router.get("/optimize/rollout/stages", tags=["Advanced engine"],
         summary="List optimization rollout stages")
def get_rollout_stages(
    subscription_id: str = Query(...),
    status: str | None = Query(None),
    tier: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.optimizer.rollout_orchestrator import list_rollout_stages
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    return list_rollout_stages(db, subscription_id, status=status, tier=tier)


@router.post("/optimize/rollout/stages/{stage_id}/start", tags=["Advanced engine"],
          summary="Start rollout stage and capture baseline metrics (admin)")
def start_rollout_stage_route(
    request: Request,
    stage_id: str = Path(...),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.models import OptimizationRolloutStage
    from app.optimizer.rollout_orchestrator import serialize_rollout_stage, start_rollout_stage
    from app.validators import ensure_subscription_known, require_subscription_id

    user = require_authenticated_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    stage = db.query(OptimizationRolloutStage).filter(OptimizationRolloutStage.id == stage_id).first()
    if not stage or (stage.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Rollout stage not found")
    if stage.status not in {"proposed"}:
        raise HTTPException(400, "Stage has already started")
    start_rollout_stage(db, stage, user=user)
    db.commit()
    return serialize_rollout_stage(stage)


@router.post("/optimize/rollout/stages/{stage_id}/expand", tags=["Advanced engine"],
          summary="Complete rollout stage after observation window (admin)")
def expand_rollout_stage_route(
    request: Request,
    stage_id: str = Path(...),
    subscription_id: str = Query(...),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.models import OptimizationRolloutStage
    from app.validators import ensure_subscription_known, require_subscription_id

    user = require_authenticated_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    stage = db.query(OptimizationRolloutStage).filter(OptimizationRolloutStage.id == stage_id).first()
    if not stage or (stage.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Rollout stage not found")
    from app.optimizer.rollout_orchestrator import expand_rollout_stage

    try:
        return expand_rollout_stage(db, stage, user=user, force=force)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/optimize/rollout/stages/{stage_id}/rollback", tags=["Advanced engine"],
          summary="Rollback rollout stage and reject linked actions (admin)")
def rollback_rollout_stage_route(
    request: Request,
    stage_id: str = Path(...),
    subscription_id: str = Query(...),
    reason: str = Query(..., min_length=3, max_length=500),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.models import OptimizationRolloutStage
    from app.optimizer.rollout_orchestrator import rollback_rollout_stage
    from app.validators import ensure_subscription_known, require_subscription_id

    user = require_authenticated_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
    stage = db.query(OptimizationRolloutStage).filter(OptimizationRolloutStage.id == stage_id).first()
    if not stage or (stage.subscription_id or "").lower() != sub:
        raise HTTPException(404, "Rollout stage not found")
    return rollback_rollout_stage(db, stage, reason=reason, user=user)


@router.get("/optimize/trends", tags=["Advanced engine"],
         summary="Optimization trends and rollout health summary")
def get_optimization_trends_route(
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    from app.optimization_trends import get_optimization_trends
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    return get_optimization_trends(db, subscription_id)


@router.get("/optimize/resources/analysis", tags=["Advanced engine"],
         summary="Advanced engine deep-dive for one resource")
def get_resource_advanced_analysis_route(
    subscription_id: str = Query(...),
    resource_id: str = Query(..., description="ARM resource ID"),
    db: Session = Depends(get_db),
):
    from app.resource_advanced_analysis import get_resource_advanced_analysis
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(subscription_id))
    if not (resource_id or "").strip():
        raise HTTPException(400, "resource_id is required")
    return get_resource_advanced_analysis(db, subscription_id, resource_id)


@router.post("/optimize/resources/batch-lookup", tags=["Advanced engine"],
          summary="Batch metrics and advanced analysis for multiple resources")
def batch_resource_lookup_route(
    request: Request,
    payload: BatchResourceLookupIn,
    db: Session = Depends(get_db),
):
    require_authenticated_user(request)
    from app.metrics_api import fetch_metrics_for_resource
    from app.resource_advanced_analysis import get_resource_advanced_analysis
    from app.validators import ensure_subscription_known, require_subscription_id

    subscription_id = ensure_subscription_known(db, require_subscription_id(payload.subscription_id))
    items: dict[str, dict] = {}
    for raw_id in payload.resource_ids:
        rid = (raw_id or "").strip()
        if not rid:
            continue
        entry: dict = {}
        if payload.include_metrics:
            entry["metrics"] = fetch_metrics_for_resource(rid, timespan=payload.timespan, db=db)
        if payload.include_advanced_analysis:
            entry["advanced_analysis"] = get_resource_advanced_analysis(db, subscription_id, rid)
        items[rid.lower()] = entry
    return {"items": items, "count": len(items)}


@router.post("/optimize/rollout/observe", tags=["Advanced engine"],
          summary="Run rollout observation check (admin)")
def observe_rollout_stages(
    request: Request,
    subscription_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.rollout_observer import check_all_subscriptions, check_rollout_observations
    from app.validators import ensure_subscription_known, require_subscription_id

    if subscription_id:
        sub = ensure_subscription_known(db, require_subscription_id(subscription_id))
        return check_rollout_observations(db, sub)
    return check_all_subscriptions(db)


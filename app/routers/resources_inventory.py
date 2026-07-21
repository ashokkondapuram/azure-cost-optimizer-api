"""Resource inventory list endpoints — migrated from main.py."""
from typing import Any, Literal, Optional
import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.arm_live_reads import fetch_live_resources
from app.auth import arm_bearer_token
from app.azure_resources import AzureResourcesClient
from app.batch_analyzer import queue_post_sync_analysis
from app.billed_resources import list_billed_resources_page
from app.cost_db import resource_cost_map_from_db
from app.database import get_db
from app.db_sync import enrich_aks_arm_clusters, sync_all, sync_scoped
from app.finding_evidence import enrich_finding_for_api
from app.http_client import AzureAPIError
from app.optimizer.engine_config import get_effective_config
from app.resource_store import (
    apply_costs_to_resources,
    get_aks_clusters_db,
    get_resource_counts,
    get_resources_by_type_prefix_db,
    get_resources_db,
    get_resources_db_page,
    list_all_resources_db,
    list_cost_resources_db,
)
from app.subscription_store import list_subscriptions_db, sync_subscription_catalog
from app.user_auth import require_admin_user, require_authenticated_user
from app.validators import coerce_dict, coerce_metric_timespan, coerce_str_dict, ensure_subscription_known
from app.vm_utils import filter_standalone_vms
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/resources", tags=["Resources"])
resource_client = AzureResourcesClient()


def _vm_sizing_timespan(timespan: Any = Query("P7D", description="Azure Monitor lookback e.g. P7D, P30D")) -> str:
    return coerce_metric_timespan(timespan)


class ResourceTagsIn(BaseModel):
    tags: dict[str, str] = Field(default_factory=dict)

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, value: Any) -> dict[str, str]:
        return coerce_str_dict(value)


class BulkResourceTagsIn(BaseModel):
    subscription_id: str
    resource_ids: list[str] = Field(..., min_length=1, max_length=50)
    tags: dict[str, str] = Field(default_factory=dict)

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, value: Any) -> dict[str, str]:
        return coerce_str_dict(value)


class SubscriptionValidateIn(BaseModel):
    subscription_id: str = Field(..., description="Azure subscription GUID")


class SubscriptionAddIn(BaseModel):
    subscription_id: str = Field(..., description="Azure subscription GUID")
    display_name: Optional[str] = Field(None, description="Optional label for the sidebar")
    set_as_default: bool = Field(False, description="Save as default subscription for sync workers")


def _scoped_subscription(db: Session, subscription_id: str) -> str:
    return ensure_subscription_known(db, subscription_id)


def _require_admin_live_arm(
    request: Request,
    db: Session,
    subscription_id: str,
) -> str:
    """Gate live Azure Resource Manager reads behind admin + subscription scope."""
    require_admin_user(request)
    return _scoped_subscription(db, subscription_id)


def _db_or_live(
    subscription_id: str,
    db: Session,
    resource_type: str,
    live_fn,
    source: Literal["db", "live"] = "db",
    *,
    request: Request,
    limit: int | None = None,
    offset: int = 0,
):
    subscription_id = _scoped_subscription(db, subscription_id)
    if source == "live":
        require_admin_user(request)
        return fetch_live_resources(
            subscription_id, db, resource_client, resource_type, live_fn,
            limit=limit, offset=offset,
        )
    include_properties = request.query_params.get("include_properties", "").lower() in {"1", "true", "yes"}
    if "include_properties" not in request.query_params and resource_type in {
        "containers/aks", "network/vnet", "network/appgateway", "network/privateendpoint",
        "network/privatelinkservice", "network/privatedns",
        "appservice/webapp", "appservice/plan",
    }:
        include_properties = True
    from app.perf_cache import cached_cost_map
    from app.pagination import validate_pagination

    cost_map = cached_cost_map(
        f"cost_map:{subscription_id.lower()}",
        lambda: resource_cost_map_from_db(db, subscription_id),
    )
    if limit is not None:
        cursor = (request.query_params.get("cursor") or "").strip() or None
        pg = validate_pagination(limit, offset, cursor=cursor)
        return get_resources_db_page(
            db, subscription_id, resource_type,
            limit=pg.limit, offset=pg.offset, cursor=pg.cursor,
            include_properties=include_properties,
            cost_map=cost_map,
        )
    return get_resources_db(
        db, subscription_id, resource_type,
        include_properties=include_properties,
        cost_map=cost_map,
    )


@router.get("/counts", tags=["Resources"],
         summary="Resource counts by category (single DB query for dashboard)")
def resource_counts(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return get_resource_counts(db, _scoped_subscription(db, subscription_id))


@router.get("/from-cost", tags=["Resources"],
         summary="Azure inventory merged with MTD costs (lazy-loaded)")
def list_resources_from_cost(
    subscription_id: str = Query(...),
    limit: int | None = Query(None, ge=1, le=200, description="Page size for lazy loading"),
    offset: int = Query(0, ge=0),
    inventory_only: bool = Query(
        False,
        description="When true, exclude cost-export-only rows (no Azure inventory match)",
    ),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    if limit is not None:
        return list_billed_resources_page(
            db,
            subscription_id,
            limit=limit,
            offset=offset,
            inventory_only=inventory_only,
        )
    return list_cost_resources_db(db, subscription_id)


@router.get("/billed", tags=["Resources"],
         summary="Azure inventory merged with MTD costs (paginated)")
def list_billed_resources(
    subscription_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    return list_billed_resources_page(db, subscription_id, limit=limit, offset=offset)


@router.get("/billed/properties", tags=["Resources"],
         summary="Lazy-load ARM properties for a billed resource")
def get_billed_resource_properties(
    resource_id: str = Query(..., description="Full ARM resource ID"),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    from app.arm_resource_probe import probe_billed_resource

    subscription_id = _scoped_subscription(db, subscription_id)
    try:
        return probe_billed_resource(db, subscription_id, resource_id, token)
    except Exception as exc:
        log.exception("billed_resource_probe_failed", resource_id=resource_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.patch("/{resource_id:path}/tags", tags=["Resources"],
           summary="Update Azure resource tags (admin)")
def patch_resource_tags(
    request: Request,
    resource_id: str = Path(..., description="Full ARM resource ID"),
    body: ResourceTagsIn = ...,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    from app.http_client import AzureAPIError
    from app.models import ResourceSnapshot

    require_admin_user(request)
    sub = _scoped_subscription(db, subscription_id)
    rid = (resource_id or "").strip()
    if not rid.startswith("/"):
        rid = f"/{rid}"
    rid_lower = rid.lower()
    if sub not in rid_lower:
        raise HTTPException(400, "resource_id does not match subscription_id")

    tags = {str(k): str(v) for k, v in (body.tags or {}).items()}
    try:
        arm_result = resource_client.patch_resource_tags(rid, tags, db=db)
    except AzureAPIError as exc:
        raise HTTPException(status_code=exc.status or 502, detail=exc.message) from exc

    row = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.resource_id == rid_lower,
        )
        .first()
    )
    if row:
        row.tags_json = json.dumps(tags)
        db.commit()

    return {
        "resource_id": rid,
        "tags": arm_result.get("tags") or tags,
        "updated": True,
    }


@router.patch("/bulk-tags", tags=["Resources"],
           summary="Apply the same tags to multiple resources (admin)")
def bulk_resource_tags(
    request: Request,
    body: BulkResourceTagsIn,
    db: Session = Depends(get_db),
):
    from app.http_client import AzureAPIError
    from app.models import ResourceSnapshot
    from app.validators import ensure_subscription_known, require_subscription_id

    require_admin_user(request)
    sub = ensure_subscription_known(db, require_subscription_id(body.subscription_id))
    tags = {str(k): str(v) for k, v in (body.tags or {}).items()}
    if not tags:
        raise HTTPException(400, "tags are required")

    updated = []
    errors = []
    for raw_id in body.resource_ids:
        rid = (raw_id or "").strip()
        if not rid.startswith("/"):
            rid = f"/{rid}"
        rid_lower = rid.lower()
        if sub not in rid_lower:
            errors.append({"resource_id": rid, "error": "subscription mismatch"})
            continue
        try:
            arm_result = resource_client.patch_resource_tags(rid, tags, db=db)
            row = (
                db.query(ResourceSnapshot)
                .filter(
                    ResourceSnapshot.subscription_id == sub,
                    ResourceSnapshot.resource_id == rid_lower,
                )
                .first()
            )
            if row:
                row.tags_json = json.dumps(arm_result.get("tags") or tags)
            updated.append(rid_lower)
        except AzureAPIError as exc:
            errors.append({"resource_id": rid, "error": exc.message})

    if updated:
        db.commit()

    return {
        "updated": len(updated),
        "resource_ids": updated,
        "errors": errors,
    }


@router.post(
    "/sync",
    tags=["Resources"],
    summary="Pull fresh Azure inventory and run the unified sync pipeline",
    status_code=202,
    responses={
        200: {"description": "Sync completed (wait=true only)"},
        202: {"description": "Unified sync pipeline accepted"},
    },
)
def trigger_resource_sync(
    request: Request,
    background_tasks: BackgroundTasks,
    subscription_id: str = Query(...),
    types: Optional[str] = Query(
        None,
        description="Comma-separated canonical types or API paths (scoped sync). Omit for full inventory.",
    ),
    include_costs: bool = Query(
        True,
        description="Run cost sync after inventory (default true for unified pipeline).",
    ),
    components: Optional[str] = Query(
        None,
        description="Comma-separated optimization components for scoped analysis after sync",
    ),
    wait: bool = Query(
        False,
        description="Block until sync completes. May time out behind gateways; default is async.",
    ),
    force: bool = Query(
        False,
        description="Cancel any active pipeline and start a new sync.",
    ),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from fastapi.responses import JSONResponse
    from app.sync_orchestrator import request_full_sync
    from app.sync_scope import normalize_sync_types

    subscription_id = subscription_id.strip().lower()
    type_list = None
    scope_resource_types = None
    if types:
        type_list = [t.strip() for t in types.split(",") if t.strip()]
        types_set = normalize_sync_types(type_list)
        if types_set:
            scope_resource_types = sorted(types_set)

    scope_components = None
    if components:
        scope_components = [c.strip() for c in components.split(",") if c.strip()] or None

    if not wait:
        enqueued, payload = request_full_sync(
            subscription_id,
            token=None,
            type_list=type_list,
            include_costs=include_costs,
            scope_components=scope_components,
            scope_resource_types=scope_resource_types,
            reason="resources_sync_api",
            force=force,
        )
        log.info(
            "resources_sync.enqueued",
            subscription_id=subscription_id,
            enqueued=enqueued,
            scoped_types=scope_resource_types,
            include_costs=include_costs,
        )
        return JSONResponse(status_code=202, content=payload)

    token = arm_bearer_token(db)
    try:
        from app.sync_orchestrator import assert_inventory_persisted

        if type_list:
            synced = sync_scoped(
                subscription_id,
                db,
                token,
                type_list,
                include_costs=include_costs,
            )
            assert_inventory_persisted(synced, scoped=True)
        else:
            synced = sync_all(subscription_id, db, token)
            assert_inventory_persisted(synced, scoped=False)
        analysis = queue_post_sync_analysis(
            db,
            background_tasks,
            subscription_id=subscription_id,
            type_list=type_list,
            components=components,
        )
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "async": False, "synced": synced, "analysis": analysis},
        )
    except Exception as exc:
        log.exception("sync_failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/sync/enrich",
    tags=["Resources"],
    summary="Run enrichment stages for a subscription or single resource",
)
def trigger_resource_enrichment(
    request: Request,
    subscription_id: str = Query(...),
    resource_id: Optional[str] = Query(
        None,
        description="ARM resource id for single-resource enrichment. Omit for subscription batch.",
    ),
    async_enrich: bool = Query(
        True,
        description="Queue subscription enrichment in background when resource_id is omitted.",
    ),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    require_admin_user(request)
    from app.sync.resource_sync_orchestrator import (
        enrichment_async_enabled,
        queue_subscription_enrichment_after_sync,
        sync_resource_full,
        sync_subscription_full,
    )

    sub = subscription_id.strip().lower()
    try:
        if resource_id:
            return sync_resource_full(
                db,
                sub,
                resource_id=resource_id.strip(),
                token=token,
            )
        if async_enrich and enrichment_async_enabled():
            return queue_subscription_enrichment_after_sync(db, sub, token=token)
        return sync_subscription_full(db, sub, token=token)
    except Exception as exc:
        log.exception("enrichment_sync_failed", subscription_id=sub)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/all", tags=["Resources"],
         summary="List all resources with optional type filter (DB-first)")
def all_resources(
    request: Request,
    subscription_id: str = Query(...),
    resource_type:   Optional[str] = Query(None, description="e.g. compute/vm"),
    source:          str = Query("db", description="db (default) or live"),
    db:              Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    if source == "live":
        require_admin_user(request)
        arm_type = None
        if resource_type:
            _arm_map = {
                "compute/vm": "Microsoft.Compute/virtualMachines",
                "compute/vmss": "Microsoft.Compute/virtualMachineScaleSets",
                "compute/disk": "Microsoft.Compute/disks",
            }
            arm_type = _arm_map.get(resource_type, resource_type)
        return resource_client.list_resources(subscription_id, arm_type)
    return list_all_resources_db(db, subscription_id, resource_type)


@router.get("/subscriptions", tags=["Resources"],
         summary="List subscriptions from database (cache + synced data)")
def list_subscriptions(db: Session = Depends(get_db)):
    from app.subscription_store import subscriptions_list_payload
    return subscriptions_list_payload(db)


@router.post("/subscriptions/sync", tags=["Resources"],
          summary="Refresh subscription list from Azure into the database (admin)")
def refresh_subscriptions(
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.subscription_store import subscriptions_list_payload, sync_subscription_catalog
    try:
        count = sync_subscription_catalog(db)
        payload = subscriptions_list_payload(db)
        return {
            "status": "ok",
            "synced": count,
            **payload,
        }
    except Exception as exc:
        log.exception("subscription_sync_failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/subscriptions/validate", tags=["Resources"],
          summary="Validate service principal access to a subscription (admin)")
def validate_subscription(
    request: Request,
    body: SubscriptionValidateIn,
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.services.subscription_validation import validate_subscription_access

    return validate_subscription_access(db, body.subscription_id)


@router.post("/subscriptions", tags=["Resources"],
          summary="Add a subscription after validating Azure access (admin)")
def add_subscription(
    request: Request,
    body: SubscriptionAddIn,
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    import app.auth as azure_auth
    from app.services.subscription_validation import validate_subscription_access
    from app.services.system_settings import save_category_settings
    from app.subscription_store import subscriptions_list_payload, upsert_subscription_cache

    result = validate_subscription_access(db, body.subscription_id)
    if not result.get("connected"):
        status_code = 403 if result.get("error_code") in {"forbidden", "creds_missing"} else 400
        raise HTTPException(
            status_code=status_code,
            detail=result.get("message") or result.get("error") or "Subscription validation failed.",
        )

    display_name = (body.display_name or "").strip() or result.get("display_name") or result["subscription_id"]
    upsert_subscription_cache(
        db,
        {
            "subscriptionId": result["subscription_id"],
            "displayName": display_name,
            "state": result.get("state") or "Enabled",
            "tenantId": result.get("tenant_id"),
        },
    )

    if body.set_as_default:
        save_category_settings(db, "azure", {"default_subscription_id": result["subscription_id"]})
        azure_auth.reload_credential(db)

    db.commit()
    payload = subscriptions_list_payload(db)
    return {
        "status": "ok",
        "message": f"Added {display_name}.",
        "subscription_id": result["subscription_id"],
        **payload,
    }


@router.get("/resource-groups", tags=["Resources"],
         summary="List resource groups in a subscription (admin, live Azure)")
def list_resource_groups(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_resource_groups(sub)


@router.get("/vms", tags=["Compute"],
         summary="Virtual machines (DB-first; source=live for ARM)")
def list_vms(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "compute/vm",
        lambda: filter_standalone_vms(
            resource_client.list_vms(subscription_id, include_instance_view=False),
        ),
        source,
        request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/vmss", tags=["Compute"],
         summary="Virtual machine scale sets (embedded under AKS only)")
def list_vmss(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Standalone VMSS inventory is disabled; scale sets appear under AKS node pools."""
    subscription_id = _scoped_subscription(db, subscription_id)
    if limit is not None:
        from app.pagination import page_envelope
        from app.resource_store import DEFAULT_RESOURCE_PAGE_SIZE, MAX_RESOURCE_PAGE_SIZE

        pg_limit = min(max(1, int(limit)), MAX_RESOURCE_PAGE_SIZE)
        return page_envelope(
            [],
            total=0,
            limit=pg_limit,
            offset=max(0, int(offset)),
            has_more=False,
            page_count=0,
            next_cursor=None,
            recommended_page_size=DEFAULT_RESOURCE_PAGE_SIZE,
            max_page_size=MAX_RESOURCE_PAGE_SIZE,
        )
    return []


@router.get("/vms/{resource_group}/{vm_name}", tags=["Compute"],
         summary="Single VM with instanceView (power state, extensions, OS)")
def get_vm(
    request: Request,
    resource_group: str = Path(...),
    vm_name:        str = Path(...),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.get_vm(sub, resource_group, vm_name)


@router.get("/vms/{resource_group}/{vm_name}/sizing", tags=["Compute"],
         summary="VM CPU/memory utilization and SKU rightsizing recommendation")
def get_vm_sizing(
    request: Request,
    resource_group: str = Path(...),
    vm_name: str = Path(...),
    subscription_id: str = Query(...),
    timespan: str = Depends(_vm_sizing_timespan),
    db: Session = Depends(get_db),
):
    from app.vm_sizing import parse_vm_sku
    from app.vm_sizing_persist import compute_vm_sizing_recommendation
    from app.cost_db import resource_cost_map_from_db
    from app.cost_utils import resource_cost_billing_from_map

    sub = _require_admin_live_arm(request, db, subscription_id)
    vm = resource_client.get_vm(sub, resource_group, vm_name)
    props = vm.get("properties") or {}
    sku = (props.get("hardwareProfile") or {}).get("vmSize") or ""
    location = vm.get("location") or ""
    catalog = resource_client.list_vm_sizes(sub, location) if location else []
    catalog_entry = next((row for row in catalog if row.get("name") == sku), None)
    parsed = parse_vm_sku(sku, catalog_entry=catalog_entry)

    metrics: dict = {}
    rid = vm.get("id") or ""
    if rid:
        try:
            metrics = resource_client.get_vm_cpu_metrics(rid, timespan) or {}
        except Exception as exc:
            log.warning("vm_sizing.metrics_failed", vm=vm_name, error=str(exc))

    rule_overrides = get_effective_config(db, "default")
    cost_map = resource_cost_map_from_db(db, sub)
    monthly_cost = resource_cost_billing_from_map(cost_map, rid)
    util, recommendation, pricing = compute_vm_sizing_recommendation(
        vm=vm,
        catalog=catalog,
        metrics=metrics,
        timespan=timespan,
        rule_overrides=rule_overrides,
        monthly_cost=monthly_cost,
    )

    return {
        "subscription_id": sub,
        "resource_id": rid,
        "resource_name": vm_name,
        "resource_group": resource_group,
        "location": location,
        "current_sku": sku,
        "sku_profile": {
            "family": parsed.family if parsed else None,
            "family_label": parsed.family_label if parsed else None,
            "vcpus": parsed.vcpus if parsed else None,
            "memory_gb": parsed.memory_gb if parsed else None,
            "variant": parsed.variant if parsed else None,
            "version": parsed.version if parsed else None,
        } if parsed else None,
        "utilization": util.as_dict(),
        "recommendation": recommendation.as_dict() if recommendation else None,
        "pricing": pricing,
        "timespan": timespan,
    }


@router.post("/vms/{resource_group}/{vm_name}/sizing/open-finding", tags=["Compute"],
          summary="Persist live VM sizing recommendation as an open optimization finding")
def persist_vm_sizing_open_finding(
    request: Request,
    resource_group: str = Path(...),
    vm_name: str = Path(...),
    subscription_id: str = Query(...),
    timespan: str = Depends(_vm_sizing_timespan),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.validators import ensure_subscription_known, validate_subscription_id
    from app.vm_sizing_persist import compute_vm_sizing_recommendation, upsert_vm_sizing_open_finding

    sub = ensure_subscription_known(db, validate_subscription_id(subscription_id))
    vm = resource_client.get_vm(sub, resource_group, vm_name)
    location = vm.get("location") or ""
    catalog = resource_client.list_vm_sizes(sub, location) if location else []

    metrics: dict = {}
    rid = vm.get("id") or ""
    if rid:
        try:
            metrics = resource_client.get_vm_cpu_metrics(rid, timespan) or {}
        except Exception as exc:
            log.warning("vm_sizing.metrics_failed", vm=vm_name, error=str(exc))

    rule_overrides = get_effective_config(db, "default")
    from app.cost_db import resource_cost_map_from_db
    from app.cost_utils import resource_cost_billing_from_map

    cost_map = resource_cost_map_from_db(db, sub)
    monthly_cost = resource_cost_billing_from_map(cost_map, rid)
    util, recommendation, pricing = compute_vm_sizing_recommendation(
        vm=vm,
        catalog=catalog,
        metrics=metrics,
        timespan=timespan,
        rule_overrides=rule_overrides,
        monthly_cost=monthly_cost,
    )
    if not recommendation or not recommendation.suggested_sku or recommendation.action not in {"downgrade", "cross_family", "upgrade"}:
        raise HTTPException(404, "No VM rightsizing recommendation available for this VM.")

    vm_metrics = {rid.lower(): metrics} if rid and metrics else {}
    row = upsert_vm_sizing_open_finding(
        db,
        subscription_id=sub,
        vm=vm,
        recommendation=recommendation.as_dict(),
        utilization=util.as_dict(),
        pricing=pricing,
        monthly_cost=monthly_cost or 0.0,
        rule_overrides=rule_overrides,
        vm_metrics=vm_metrics,
    )
    if not row:
        raise HTTPException(422, "Could not create an open finding from the sizing recommendation.")

    evidence = json.loads(row.evidence_json or "{}")
    return enrich_finding_for_api({
        "id": row.id,
        "run_id": row.run_id,
        "rule_id": row.rule_id,
        "rule_name": row.rule_name,
        "category": row.category,
        "severity": row.severity,
        "resource_id": row.resource_id,
        "resource_name": row.resource_name,
        "resource_type": row.resource_type,
        "resource_group": row.resource_group,
        "location": row.location,
        "detail": row.detail,
        "recommendation": row.recommendation,
        "estimated_savings_usd": row.estimated_savings_usd,
        "annualized_savings_usd": row.annualized_savings_usd,
        "waste_score": row.waste_score,
        "confidence_score": row.confidence_score,
        "action_priority": row.action_priority,
        "impact": row.impact,
        "evidence": evidence,
        "status": row.status,
        "detected_at": str(row.detected_at),
        "resolved_at": str(row.resolved_at) if row.resolved_at else None,
    })


@router.get("/vm-skus", tags=["Compute"],
         summary="All VM SKUs in a region — vCPUs, memory, max disks, capabilities (Resource SKUs API 2021-07-01)")
def list_vm_skus(
    request: Request,
    subscription_id: str = Query(...),
    location:        str = Query(..., description="Azure region e.g. eastus, westeurope"),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_vm_skus(sub, location)


@router.get("/vm-sizes", tags=["Compute"],
         summary="VM sizes in a location — core count and memory (Compute API 2024-03-01)")
def list_vm_sizes(
    request: Request,
    subscription_id: str = Query(...),
    location:        str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_vm_sizes(sub, location)


def _enrich_disk_list_result(result: Any, *, include_metrics: bool, db: Session | None = None) -> Any:
    """Apply disk list shape to plain lists and paginated envelopes."""
    from app.resource_list_enrichment import enrich_resource_list_result

    return enrich_resource_list_result(
        result,
        resource_type="compute/disk",
        include_metrics=include_metrics,
        db=db,
    )


@router.get("/disks", tags=["Compute"],
         summary="Managed disks (DB-first; source=live for ARM)")
def list_disks(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_metrics: bool = Query(False, description="Include computed disk metrics (IOPS %, throughput %, etc)"),
    db: Session = Depends(get_db),
):
    result = _db_or_live(
        subscription_id, db, "compute/disk",
        lambda: resource_client.list_disks(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )

    return _enrich_disk_list_result(result, include_metrics=include_metrics, db=db)


@router.get("/snapshots", tags=["Compute"],
         summary="Disk snapshots (DB-first; source=live for ARM)")
def list_snapshots(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "compute/snapshot",
        lambda: resource_client.list_snapshots(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  RESOURCES — KUBERNETES / AKS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/aks", tags=["Kubernetes"],
         summary="AKS clusters (DB-first; source=live for ARM)")
def list_aks(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    if source == "live":
        require_admin_user(request)

        def _fetch_aks() -> list:
            clusters = resource_client.list_aks_clusters(subscription_id)
            return enrich_aks_arm_clusters(resource_client, subscription_id, clusters)

        return fetch_live_resources(
            subscription_id, db, resource_client, "containers/aks", _fetch_aks,
            limit=limit, offset=offset,
        )

    # Version/Network columns need kubernetesVersion & networkProfile from properties_json.
    include_properties = request.query_params.get("include_properties", "").lower() in {"1", "true", "yes"}
    if "include_properties" not in request.query_params:
        include_properties = True

    from app.cost_db import resource_cost_map_from_db
    from app.perf_cache import cached_cost_map

    cost_map = cached_cost_map(
        f"cost_map:{subscription_id.lower()}",
        lambda: resource_cost_map_from_db(db, subscription_id),
    )

    if limit is not None:
        return get_resources_db_page(
            db, subscription_id, "containers/aks",
            limit=limit, offset=offset,
            cost_map=cost_map,
            include_properties=include_properties,
        )
    return get_aks_clusters_db(db, subscription_id)


@router.get("/aks/{resource_group}/{cluster_name}", tags=["Kubernetes"],
         summary="Single AKS cluster detail (admin, live Azure)")
def get_aks_cluster(
    request: Request,
    resource_group: str = Path(...),
    cluster_name:   str = Path(...),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.get_aks_cluster(sub, resource_group, cluster_name)


@router.get("/aks/{resource_group}/{cluster_name}/node-pools", tags=["Kubernetes"],
         summary="AKS node pools (agent pools) for a cluster (admin, live Azure)")
def list_aks_node_pools(
    request: Request,
    resource_group: str = Path(...),
    cluster_name:   str = Path(...),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_aks_node_pools(sub, resource_group, cluster_name)


@router.get(
    "/containers/aks/pool-instances",
    tags=["Kubernetes"],
    summary="VMSS instances and per-node metrics for an AKS agent pool (lazy load)",
)
def get_aks_pool_instances(
    request: Request,
    resource_id: str = Query(..., description="AKS cluster ARM resource ID"),
    subscription_id: str = Query(...),
    pool: str | None = Query(None, description="Agent pool name; omit for all pools"),
    timespan: str = Depends(_vm_sizing_timespan),
    db: Session = Depends(get_db),
):
    """List VMSS backing instances for AKS node pools with CPU/memory metrics."""
    require_authenticated_user(request)
    from app.metrics_api import _aks_pools_from_inventory, _fetch_aks_node_instances, _load_inventory_row
    from app.auth import arm_auth_context, get_token
    from it_services.containers_aks.pool_instances import fetch_aks_pool_instances

    sub = ensure_subscription_known(db, subscription_id)
    rid = (resource_id or "").strip()
    if not rid.startswith("/"):
        rid = f"/{rid}"
    inv_row = _load_inventory_row(db, rid)
    if not inv_row:
        raise HTTPException(404, "AKS cluster not found in inventory")
    pools = _aks_pools_from_inventory(inv_row)
    if not pools:
        return {"resource_id": rid, "pools": {}}
    inv_props = (inv_row or {}).get("properties") or {}
    cluster_name = rid.rsplit("/", 1)[-1]
    k8s_instances = _fetch_aks_node_instances(db, cluster_name, pools)
    client = AzureResourcesClient(db=db)
    with arm_auth_context(db=db, token=get_token(db)):
        pool_instances = fetch_aks_pool_instances(
            client,
            sub,
            cluster_name=cluster_name,
            pools=pools,
            pool_name=pool,
            k8s_instances=k8s_instances,
            timespan=timespan,
            db=db,
            vmss_by_pool=inv_props.get("_vmssByPool") or {},
            node_resource_group=str(inv_props.get("nodeResourceGroup") or "").strip(),
        )
    return {"resource_id": rid, "pool": pool, "pools": pool_instances}


@router.get("/aks/{resource_group}/{cluster_name}/upgrades", tags=["Kubernetes"],
         summary="Available Kubernetes version upgrades for a cluster (admin, live Azure)")
def get_aks_upgrades(
    request: Request,
    resource_group: str = Path(...),
    cluster_name:   str = Path(...),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_aks_upgrades(sub, resource_group, cluster_name)


@router.get("/aks/kubernetes-versions", tags=["Kubernetes"],
         summary="Supported Kubernetes versions for an Azure region (live ARM)")
def list_aks_kubernetes_versions(
    request: Request,
    subscription_id: str = Query(...),
    location: str = Query(..., description="Azure region name, e.g. eastus"),
    refresh: bool = Query(False, description="Bypass cache and fetch from Azure"),
    db: Session = Depends(get_db),
):
    """Returns full version metadata from Azure Container Service for the region."""
    require_admin_user(request)
    from app.aks_versions import fetch_kubernetes_versions_for_location
    return fetch_kubernetes_versions_for_location(
        subscription_id.lower(),
        location,
        db=db,
        force_refresh=refresh,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  RESOURCES — STORAGE / WEB / DATABASE / NETWORKING / SECURITY
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/storage", tags=["Storage"], summary="Storage accounts (DB-first)")
def list_storage(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "storage/account",
        lambda: resource_client.list_storage_accounts(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/appservices", tags=["App Services"], summary="Web/Function apps (DB-first)")
def list_appservices(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "appservice/webapp",
        lambda: resource_client.list_app_services(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/appserviceplans", tags=["App Services"], summary="App Service plans (DB-first)")
def list_asp(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "appservice/plan",
        lambda: resource_client.list_app_service_plans(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/sql", tags=["Databases"], summary="SQL Servers (DB-first)")
def list_sql(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "database/sql",
        lambda: resource_client.list_sql_servers(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/sql/{resource_group}/{server_name}/databases", tags=["Databases"],
         summary="Databases on a SQL Server (admin, live Azure)")
def list_sql_databases(
    request: Request,
    resource_group: str = Path(...),
    server_name: str = Path(...),
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_sql_databases(sub, resource_group, server_name)


@router.get("/postgresql", tags=["Databases"], summary="PostgreSQL Flexible Servers (DB-first)")
def list_postgresql(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "database/postgresql",
        lambda: resource_client.list_postgresql_flexible(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/mysql", tags=["Databases"], summary="MySQL Flexible Servers (admin, live Azure)")
def list_mysql(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    sub = _require_admin_live_arm(request, db, subscription_id)
    return resource_client.list_mysql_flexible(sub)


@router.get("/cosmosdb", tags=["Databases"], summary="Cosmos DB accounts (DB-first)")
def list_cosmosdb(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "database/cosmosdb",
        lambda: resource_client.list_cosmosdb(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/publicips", tags=["Networking"], summary="Public IPs (DB-first)")
def list_publicips(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/publicip",
        lambda: resource_client.list_public_ips(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/vnets", tags=["Networking"], summary="Virtual networks (DB-first)")
def list_vnets(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/vnet",
        lambda: resource_client.list_vnets(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/nics", tags=["Networking"], summary="Network interfaces (DB-first)")
def list_nics(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/nic",
        lambda: resource_client.list_network_interfaces(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/natgateways", tags=["Networking"], summary="NAT gateways (DB-first)")
def list_nat_gateways(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/nat",
        lambda: resource_client.list_nat_gateways(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/redis", tags=["Databases"], summary="Azure Cache for Redis (DB-first)")
def list_redis(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "database/redis",
        lambda: resource_client.list_redis_caches(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/loadbalancers", tags=["Networking"], summary="Load Balancers (DB-first)")
def list_lbs(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/loadbalancer",
        lambda: resource_client.list_load_balancers(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/appgateways", tags=["Networking"], summary="Application Gateways (DB-first)")
def list_agws(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/appgateway",
        lambda: resource_client.list_application_gateways(subscription_id),
        source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/nsgs", tags=["Networking"], summary="Network Security Groups (DB-first)")
def list_nsgs(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/nsg",
        lambda: resource_client.list_network_security_groups(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/privateendpoints", tags=["Networking"], summary="Private endpoints (DB-first)")
def list_private_endpoints(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/privateendpoint",
        lambda: resource_client.list_private_endpoints(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/privatelinkservices", tags=["Networking"], summary="Private link services (DB-first)")
def list_private_link_services(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/privatelinkservice",
        lambda: resource_client.list_private_link_services(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/privatedns", tags=["Networking"], summary="Private DNS zones (DB-first)")
def list_private_dns_zones(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "network/privatedns",
        lambda: resource_client.list_private_dns_zones(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/keyvaults", tags=["Security"], summary="Key Vaults (DB-first)")
def list_kvs(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "security/keyvault",
        lambda: resource_client.list_keyvaults(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


@router.get("/acr", tags=["Containers"], summary="Container Registries (DB-first)")
def list_acr(
    request: Request,
    subscription_id: str = Query(...),
    source: str = Query("db"),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return _db_or_live(
        subscription_id, db, "containers/acr",
        lambda: resource_client.list_container_registries(subscription_id), source, request=request,
        limit=limit,
        offset=offset,
    )


def _inventory_type_list_handler(canonical_type: str):
    def handler(
        request: Request,
        subscription_id: str = Query(...),
        source: str = Query("db"),
        limit: Optional[int] = Query(None, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
    ):
        return _db_or_live(
            subscription_id,
            db,
            canonical_type,
            lambda: [],
            source,
            request=request,
            limit=limit,
            offset=offset,
        )

    return handler


from app.resource_page_registry import inventory_pages as _inventory_pages  # noqa: E402

for _page in _inventory_pages():
    _handler = _inventory_type_list_handler(_page.canonical_type)
    router.add_api_route(
        f"/{_page.api_slug}",
        _handler,
        methods=["GET"],
        tags=[_page.openapi_tag],
        summary=f"{_page.title} (DB-first)",
    )
    router.add_api_route(
        f"/{_page.canonical_type}",
        _handler,
        methods=["GET"],
        tags=[_page.openapi_tag],
        summary=f"{_page.title} (canonical path, DB-first)",
    )


@router.get("/pages", tags=["Resources"], summary="Per-type inventory page catalog")
def list_inventory_page_catalog():
    from app.resource_page_registry import pages_catalog

    return pages_catalog()


@router.get("/monitoring", tags=["Monitoring"], summary="[Legacy] Log Analytics and Application Insights")
def list_monitoring(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_resources_by_type_prefix_db(db, subscription_id, "monitoring")


@router.get("/integration", tags=["Integration"], summary="[Legacy] API Management, Data Factory, Logic Apps")
def list_integration(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_resources_by_type_prefix_db(db, subscription_id, "integration")


@router.get("/messaging", tags=["Messaging"], summary="[Legacy] Event Hubs and Service Bus")
def list_messaging(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_resources_by_type_prefix_db(db, subscription_id, "messaging")


@router.get("/analytics", tags=["Analytics"], summary="[Legacy] Databricks, Synapse, ADX, ML")
def list_analytics(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_resources_by_type_prefix_db(db, subscription_id, "analytics")


@router.get("/backup", tags=["Backup"], summary="[Legacy] Recovery Services vaults")
def list_backup(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_resources_by_type_prefix_db(db, subscription_id, "backup")


@router.get("/search", tags=["Search"], summary="[Legacy] Azure AI Search")
def list_search(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    subscription_id = _scoped_subscription(db, subscription_id)
    return get_resources_by_type_prefix_db(db, subscription_id, "search")


# Canonical-path aliases for core inventory list routes (enrichment table alignment).
_CANONICAL_LIST_ROUTES: dict[str, Any] = {
    "compute/vm": list_vms,
    "compute/vmss": list_vmss,
    "compute/disk": list_disks,
    "compute/snapshot": list_snapshots,
    "containers/aks": list_aks,
    "containers/acr": list_acr,
    "storage/account": list_storage,
    "appservice/webapp": list_appservices,
    "appservice/plan": list_asp,
    "database/sql": list_sql,
    "database/cosmosdb": list_cosmosdb,
    "database/postgresql": list_postgresql,
    "database/redis": list_redis,
    "network/publicip": list_publicips,
    "network/vnet": list_vnets,
    "network/nic": list_nics,
    "network/nat": list_nat_gateways,
    "network/loadbalancer": list_lbs,
    "network/appgateway": list_agws,
    "network/nsg": list_nsgs,
    "network/privateendpoint": list_private_endpoints,
    "network/privatelinkservice": list_private_link_services,
    "network/privatedns": list_private_dns_zones,
    "security/keyvault": list_kvs,
}

for _canonical, _handler in _CANONICAL_LIST_ROUTES.items():
    router.add_api_route(
        f"/{_canonical}",
        _handler,
        methods=["GET"],
        tags=["Resources"],
        summary=f"List {_canonical} (canonical path)",
    )

router.add_api_route(
    "/compute/vm/{resource_group}/{vm_name}/sizing",
    get_vm_sizing,
    methods=["GET"],
    tags=["Compute"],
    summary="VM sizing (canonical path)",
)
router.add_api_route(
    "/compute/vm/{resource_group}/{vm_name}/sizing/open-finding",
    persist_vm_sizing_open_finding,
    methods=["POST"],
    tags=["Compute"],
    summary="Persist VM sizing finding (canonical path)",
)
router.add_api_route(
    "/containers/aks/kubernetes-versions",
    list_aks_kubernetes_versions,
    methods=["GET"],
    tags=["Kubernetes"],
    summary="AKS Kubernetes versions (canonical path)",
)


# ══════════════════════════════════════════════════════════════════════════════
#  AZURE MONITOR METRICS  (API 2023-10-01)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/monitor-plan", tags=["Monitor"],
         summary="Azure Monitor metric definitions per resource type (from technical fetch specs)")
def list_monitor_plan():
    from app.monitor_metrics import monitor_fetch_plan
    return monitor_fetch_plan()


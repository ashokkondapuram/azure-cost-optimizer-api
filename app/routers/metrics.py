"""Azure Monitor metrics endpoints — migrated from main.py."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from app.azure_resources import AzureResourcesClient
from app.database import get_db
from app.user_auth import require_admin_user, require_authenticated_user
from app.validators import ensure_subscription_known

router = APIRouter(prefix="/metrics", tags=["Monitor"])
resource_client = AzureResourcesClient()


def _scoped_subscription(db: Session, subscription_id: str) -> str:
    return ensure_subscription_known(db, subscription_id)

@router.get("/profiles", tags=["Monitor"],
         summary="Catalog of monitor profiles and metric names per ARM resource type")
def metrics_profiles(request: Request):
    require_authenticated_user(request)
    from app.metrics_api import monitor_profiles_catalog
    return monitor_profiles_catalog()


@router.get("/resource/plan", tags=["Monitor"],
         summary="Metric names that apply to one resource (by ARM type)")
def metrics_resource_plan(
    request: Request,
    resource_id: str = Query(..., description="Full ARM resource ID"),
):
    require_authenticated_user(request)
    from app.metrics_api import plan_for_resource
    return plan_for_resource(resource_id)


@router.get("/resource/auto", tags=["Monitor"],
         summary="Fetch Azure Monitor metrics for one resource (profile-driven)")
def metrics_resource_auto(
    request: Request,
    resource_id: str = Query(..., description="Full ARM resource ID"),
    timespan: str = Query("P7D"),
    db: Session = Depends(get_db),
):
    require_authenticated_user(request)
    from app.metrics_api import fetch_metrics_for_resource
    return fetch_metrics_for_resource(resource_id, timespan=timespan, db=db)


@router.get("/triggers", tags=["Monitor"],
         summary="Metric trigger registry — thresholds and cost vs performance effects")
def metrics_triggers_catalog(request: Request):
    require_authenticated_user(request)
    from app.metrics_api import triggers_catalog
    return triggers_catalog()


@router.get("/resource-cost-mapping", tags=["Monitor"],
         summary="Resource type → cost-driving properties and metrics")
def metrics_resource_cost_mapping(
    request: Request,
    canonical_type: str | None = Query(None, description="Filter by canonical type, e.g. compute/vm"),
    resource_id: str | None = Query(None, description="ARM resource ID for resource-specific mapping"),
):
    require_authenticated_user(request)
    from app.metrics_api import resource_cost_mapping_catalog
    return resource_cost_mapping_catalog(canonical_type, resource_id=resource_id)


@router.get("/by-type", tags=["Monitor"],
         summary="Fetch metrics for all synced resources of one type in a subscription (admin)")
def metrics_by_type(
    request: Request,
    subscription_id: str = Query(...),
    canonical_type: str = Query(..., description="e.g. compute/vm, storage/account"),
    timespan: str = Query("P7D"),
    limit: int = Query(0, ge=0, le=500, description="Max resources per type (0 = all)"),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.metrics_api import fetch_metrics_by_canonical_type
    subscription_id = _scoped_subscription(db, subscription_id)
    return fetch_metrics_by_canonical_type(
        db, subscription_id, canonical_type.strip().lower(),
        timespan=timespan,
        limit_per_type=limit,
    )


@router.get("/subscription", tags=["Monitor"],
         summary="Fetch metrics for synced inventory (admin; all types or one canonical type)")
def metrics_subscription(
    request: Request,
    subscription_id: str = Query(...),
    canonical_type: Optional[str] = Query(None, description="Optional filter, e.g. compute/vm"),
    timespan: str = Query("P7D"),
    limit: int = Query(0, ge=0, le=500, description="Max resources per type (0 = all)"),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.metrics_api import fetch_metrics_for_subscription
    subscription_id = _scoped_subscription(db, subscription_id)
    return fetch_metrics_for_subscription(
        db, subscription_id,
        canonical_type=canonical_type.strip().lower() if canonical_type else None,
        timespan=timespan,
        limit_per_type=limit,
    )


@router.get("/vm-cpu", tags=["Monitor"],
         summary="CPU % + Available Memory for a VM (P7D default, admin)")
def get_vm_cpu(
    request: Request,
    resource_id: str = Query(..., description="Full ARM resource ID"),
    timespan:    str = Query("P7D"),
):
    require_admin_user(request)
    return resource_client.get_vm_cpu_metrics(resource_id, timespan)


@router.get("/resource", tags=["Monitor"],
         summary="Generic metric query for any ARM resource (admin)")
def get_resource_metric(
    request: Request,
    resource_id:  str = Query(...),
    metric_names: str = Query(..., description="Comma-separated"),
    timespan:     str = Query("PT1H"),
    interval:     str = Query("PT5M"),
    aggregation:  str = Query("Average"),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    return resource_client.get_resource_metrics(
        resource_id,
        metric_names=[m.strip() for m in metric_names.split(",")],
        timespan=timespan, interval=interval, aggregation=aggregation,
        db=db,
    )


@router.get("/diagnostics", tags=["Monitor"],
         summary="Probe Azure Monitor access for one resource (admin)")
def probe_monitor_access(
    request: Request,
    resource_id: str = Query(..., description="Full ARM resource ID"),
    metric_names: str = Query("Percentage CPU", description="Comma-separated metric names"),
    timespan: str = Query("P7D"),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    from app.monitor_metrics import probe_monitor_metrics

    names = [m.strip() for m in metric_names.split(",") if m.strip()]
    return probe_monitor_metrics(resource_id, names or None, timespan=timespan, db=db)


# ══════════════════════════════════════════════════════════════════════════════
#  OPTIMIZATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════


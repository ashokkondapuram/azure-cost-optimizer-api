"""Resources router — /resources prefix."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.arm_live_reads import fetch_live_resources
from app.azure_resources import AzureResourcesClient
from app.cost_db import resource_cost_map_from_db
from app.database import get_db
from app.resource_store import (
    get_resources_db,
    get_resources_db_page,
)
from app.auth import arm_bearer_token
from app.user_auth import require_admin_user
from app.validators import ensure_subscription_known
import structlog

log = structlog.get_logger()

router = APIRouter(prefix="/resources", tags=["Resources"])

resource_client = AzureResourcesClient()


def _scoped_subscription(db: Session, subscription_id: str) -> str:
    return ensure_subscription_known(db, subscription_id)


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
    """DB reads by default; live ARM only for admins with source=live."""
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
    cost_map = cached_cost_map(
        f"cost_map:{subscription_id.lower()}",
        lambda: resource_cost_map_from_db(db, subscription_id),
    )
    if limit is not None:
        return get_resources_db_page(
            db, subscription_id, resource_type,
            limit=limit, offset=offset,
            include_properties=include_properties,
            cost_map=cost_map,
        )
    return get_resources_db(
        db, subscription_id, resource_type,
        include_properties=include_properties,
        cost_map=cost_map,
    )


@router.get("/discovery/sync", summary="Discover all subscription resources from ARM list API", tags=["Resources"])
def trigger_resource_discovery_sync(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    from app.resource_discovery_sync import sync_resource_discovery
    require_admin_user(request)
    try:
        subscription_id = subscription_id.strip().lower()
        result = sync_resource_discovery(subscription_id, db, token)
        return {"status": "ok", **result}
    except Exception as exc:
        log.exception("resource_discovery_sync_failed", subscription_id=subscription_id)
        raise HTTPException(500, str(exc)) from exc


@router.get("/cost-audit", summary="Cost-bearing resource types")
def get_resource_cost_audit(
    request: Request,
    subscription_id: str = Query(...),
    live: bool = Query(False),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    from app.auth import arm_auth_context
    from app.http_client import arm_patient_sync
    from app.resource_cost_audit import audit_from_arm_items, audit_from_cost_db
    require_admin_user(request)
    subscription_id = subscription_id.strip().lower()
    if live:
        with arm_auth_context(db=db, token=token):
            client = AzureResourcesClient(db=db)
            with arm_patient_sync():
                items = client.list_resources(subscription_id)
        audit = audit_from_arm_items(db, subscription_id, items)
        audit["source"] = "arm_resources_list"
    else:
        audit = audit_from_cost_db(db, subscription_id)
    return {"status": "ok", **audit}


@router.get("/azure-service-cost-catalog", summary="Azure services and resource types with cost classification")
def get_azure_service_cost_catalog(request: Request):
    from app.azure_service_cost_catalog import (
        arm_type_catalog_rows,
        canonical_type_catalog_rows,
        catalog_aliases,
        catalog_metadata,
        catalog_table_rows,
    )
    from app.free_tier_reference import official_free_services_catalog, reference_metadata
    from app.resource_pricing import sku_pricing_table_rows
    require_admin_user(request)
    return {
        "status": "ok",
        "catalog": catalog_metadata(),
        "services": catalog_table_rows(),
        "aliases": catalog_aliases(),
        "canonical_types": canonical_type_catalog_rows(),
        "arm_types": arm_type_catalog_rows(),
        "free_tier_reference": reference_metadata(),
        "official_free_services": official_free_services_catalog(),
        "sku_tiers": sku_pricing_table_rows(),
    }


@router.get("/pricing-profiles", summary="Per-resource SKU and pricing model profiles")
def get_resource_pricing_profiles(
    request: Request,
    subscription_id: str = Query(...),
    resource_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    from app.resource_pricing import list_pricing_profiles_db
    require_admin_user(request)
    return {
        "status": "ok",
        **list_pricing_profiles_db(db, subscription_id, canonical_type=resource_type, limit=limit, offset=offset),
    }

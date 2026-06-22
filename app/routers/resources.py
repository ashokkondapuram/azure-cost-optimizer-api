"""
Resources router — DB-first reads.

All GET endpoints read from the local database (resource_snapshots).
POST /sync triggers a full Azure → DB sync for a given subscription.

This means:
  - Dashboard loads instantly from DB (no Azure round-trip per page load)
  - Sync runs on demand or on a schedule (cron / background task)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ResourceSnapshot, SubscriptionCache
from ..auth import get_token
from ..db_sync import sync_all

log = logging.getLogger(__name__)
router = APIRouter(prefix="/resources", tags=["resources"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _rows_to_list(rows):
    result = []
    for r in rows:
        try:
            import json
            props = json.loads(r.properties_json or "{}")
            tags  = json.loads(r.tags_json or "{}")
        except Exception:
            props, tags = {}, {}
        result.append({
            "id":              r.resource_id,
            "name":            r.resource_name,
            "type":            r.resource_type,
            "resourceGroup":   r.resource_group,
            "location":        r.location,
            "sku":             r.sku,
            "state":           r.state,
            "tags":            tags,
            "properties":      props,
            "monthlyCostUsd":  r.monthly_cost_usd,
            "syncedAt":        r.synced_at.isoformat() if r.synced_at else None,
        })
    return result


def _get_resources(db: Session, subscription_id: str, resource_type: str):
    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == subscription_id,
            ResourceSnapshot.resource_type   == resource_type,
            ResourceSnapshot.is_active       == True,
        )
        .order_by(ResourceSnapshot.resource_name)
        .all()
    )
    return _rows_to_list(rows)


# ---------------------------------------------------------------------------
# Sync endpoint
# ---------------------------------------------------------------------------

@router.post("/sync")
def trigger_sync(
    subscription_id: str = Query(...),
    db: Session  = Depends(get_db),
    token: str   = Depends(get_token),
):
    """
    Pull fresh data from Azure and write to DB.
    Call this manually or set up a cron job / Azure Function timer.
    """
    try:
        result = sync_all(subscription_id, db, token)
        return {"status": "ok", "synced": result}
    except Exception as e:
        log.exception("Sync failed")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Subscriptions (from cache)
# ---------------------------------------------------------------------------

@router.get("/subscriptions")
def list_subscriptions(db: Session = Depends(get_db), token: str = Depends(get_token)):
    rows = db.query(SubscriptionCache).order_by(SubscriptionCache.display_name).all()
    if rows:
        return [{"subscriptionId": r.subscription_id, "displayName": r.display_name,
                 "state": r.state, "tenantId": r.tenant_id} for r in rows]
    # Fall back to live Azure if cache is empty
    try:
        from ..azure_client import AzureClient
        client = AzureClient(token)
        return client.list_subscriptions()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ---------------------------------------------------------------------------
# Resource type endpoints — all DB-first
# ---------------------------------------------------------------------------

@router.get("/vms")
def list_vms(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "compute/vm")


@router.get("/disks")
def list_disks(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "compute/disk")


@router.get("/aks")
def list_aks(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "containers/aks")


@router.get("/acr")
def list_acr(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "containers/acr")


@router.get("/storage")
def list_storage(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "storage/account")


@router.get("/publicips")
def list_public_ips(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "network/publicip")


@router.get("/loadbalancers")
def list_lbs(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "network/loadbalancer")


@router.get("/appgateways")
def list_agw(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "network/appgateway")


@router.get("/nsgs")
def list_nsgs(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "network/nsg")


@router.get("/sql")
def list_sql(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "database/sql")


@router.get("/cosmosdb")
def list_cosmos(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "database/cosmosdb")


@router.get("/postgresql")
def list_pg(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "database/postgresql")


@router.get("/appservices")
def list_apps(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "appservice/webapp")


@router.get("/keyvaults")
def list_keyvaults(subscription_id: str = Query(...), db: Session = Depends(get_db)):
    return _get_resources(db, subscription_id, "security/keyvault")


@router.get("/all")
def list_all_resources(
    subscription_id: str = Query(...),
    resource_type:   Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Returns all active resources, optionally filtered by resource_type."""
    q = db.query(ResourceSnapshot).filter(
        ResourceSnapshot.subscription_id == subscription_id,
        ResourceSnapshot.is_active == True,
    )
    if resource_type:
        q = q.filter(ResourceSnapshot.resource_type == resource_type)
    rows = q.order_by(ResourceSnapshot.resource_type, ResourceSnapshot.resource_name).all()
    return _rows_to_list(rows)

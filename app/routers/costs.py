"""Cost Management router — /costs prefix."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.azure_cost import AzureCostClient, CostExportNotConfiguredError, CostExportReadError
from app.cost_db import (
    cost_by_resource_from_db,
    cost_by_resource_type_from_db,
    cost_by_service_from_db,
    cost_summary_from_db,
    daily_cost_response_from_db,
    daily_cost_by_resource_group_from_db,
    empty_cost_by_resource_response,
    empty_cost_by_service_response,
    empty_cost_summary_response,
    empty_daily_cost_response,
    get_latest_cost_changes,
    list_cost_records,
    mtd_period_for_timeframe,
)
from app.cost_live_query import (
    query_cost_by_resource_live,
    query_cost_by_service_live,
    query_cost_summary_live,
    query_daily_costs_live,
)
from app.cost_resolve import live_range_kw, resolve_cost_db_then_live
from app.cost_timeframes import list_timeframe_catalog
from app.database import get_db
from app.db_sync import sync_costs
from app.auth import arm_bearer_token
from app.user_auth import require_admin_user
from app.validators import ensure_subscription_known
import structlog

log = structlog.get_logger()

router = APIRouter(prefix="/costs", tags=["Cost Management"])

cost_client = AzureCostClient()


# ── helpers ──────────────────────────────────────────────────────────────────

def _scoped_subscription(db: Session, subscription_id: str) -> str:
    return ensure_subscription_known(db, subscription_id)


def _cost_range_kwargs(
    timeframe: str,
    from_date: str | None,
    to_date: str | None,
    *,
    resource_types: str | None = None,
) -> dict:
    from app.resource_type_catalog import parse_resource_types_param
    kw: dict = {"timeframe": timeframe}
    if (from_date or "").strip():
        kw["from_date"] = from_date.strip()[:10]
    if (to_date or "").strip():
        kw["to_date"] = to_date.strip()[:10]
    if timeframe == "Custom" and (not kw.get("from_date") or not kw.get("to_date")):
        raise HTTPException(422, "from_date and to_date are required when timeframe is Custom")
    types = parse_resource_types_param(resource_types)
    if types:
        kw["resource_types"] = types
    return kw


def _live_cost_token(db: Session) -> str | None:
    from app.auth import get_token
    try:
        return get_token(db)
    except Exception as exc:
        log.warning("cost_api.token_unavailable", error=str(exc)[:300])
        return None


def _enqueue_cost_sync(subscription_id: str, *, reason: str) -> None:
    from app.cost_explorer_worker import request_cost_sync
    request_cost_sync(subscription_id, reason=reason)


def _cost_api_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CostExportNotConfiguredError):
        log.error("cost_api.not_configured", error=str(exc))
        return HTTPException(503, str(exc))
    if isinstance(exc, CostExportReadError):
        detail = str(exc)
        status = 403 if "authorization" in detail.lower() or "403" in detail else 502
        log.error("cost_api.read_failed", error=detail, status=status)
        return HTTPException(status, detail)
    log.exception("cost_api.unexpected_error")
    return HTTPException(500, str(exc))


# ── routes ───────────────────────────────────────────────────────────────────

@router.get("/timeframes", summary="Supported cost explorer timeframes")
def list_cost_timeframes():
    return {"timeframes": list_timeframe_catalog()}


@router.get("", summary="Query actual costs from the database (synced from Azure Cost Management)")
def get_costs(
    request: Request,
    subscription_id: Optional[str] = Query(None),
    timeframe:       str = Query("MonthToDate"),
    from_date:       Optional[str] = Query(None, description="YYYY-MM-DD (required for Custom)"),
    to_date:         Optional[str] = Query(None, description="YYYY-MM-DD (required for Custom)"),
    granularity:     str = Query("Daily"),
    resource_types:  Optional[str] = Query(None, description="Comma-separated canonical resource types"),
    db: Session = Depends(get_db),
):
    from app.spa_utils import should_serve_spa, spa_index_response
    if should_serve_spa(request, api_query_present=bool(subscription_id)):
        spa = spa_index_response()
        if spa:
            return spa
    if not subscription_id:
        raise HTTPException(422, "subscription_id is required")
    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, from_date, to_date, resource_types=resource_types)
    live_kw = live_range_kw(range_kw)
    token = _live_cost_token(db)
    scope = f"/subscriptions/{subscription_id}"
    db_data, source = resolve_cost_db_then_live(
        db_call=lambda: daily_cost_response_from_db(db, subscription_id, **range_kw),
        live_call=lambda: query_daily_costs_live(db, subscription_id, token=token, **live_kw),
    )
    if db_data:
        if source != "database":
            _enqueue_cost_sync(subscription_id, reason="live_fallback_daily")
        log.info("cost_api.get_costs", subscription_id=subscription_id, timeframe=timeframe,
                 source=source, rows=len(db_data.get("properties", {}).get("rows", [])))
        return {"id": None, "scope": scope, "timeframe": timeframe,
                "granularity": granularity, "data": db_data, "source": source}
    _enqueue_cost_sync(subscription_id, reason="no_synced_rows")
    return {"id": None, "scope": scope, "timeframe": timeframe, "granularity": granularity,
            "data": empty_daily_cost_response(), "source": "database", "sync_required": True}


@router.get("/resource-group", summary="Daily costs for a resource group (database after sync)")
def get_rg_costs(
    subscription_id: str = Query(...),
    resource_group:  str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    from_date:       Optional[str] = Query(None),
    to_date:         Optional[str] = Query(None),
    granularity:     str = Query("Daily"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, from_date, to_date)
    scope = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
    db_data = daily_cost_by_resource_group_from_db(db, subscription_id, resource_group, **range_kw)
    if db_data:
        return {"id": None, "scope": scope, "data": db_data, "source": "database"}
    return {"id": None, "scope": scope, "data": empty_daily_cost_response(),
            "source": "database", "sync_required": True}


@router.get("/by-resource", summary="Cost per resource ID (database after sync)")
def get_costs_by_resource(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    resource_types:  Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, None, None, resource_types=resource_types)
    live_kw = live_range_kw(range_kw)
    token = _live_cost_token(db)

    def _live_by_resource() -> dict | None:
        if range_kw.get("resource_types"):
            return None
        return query_cost_by_resource_live(db, subscription_id, token=token, **live_kw)

    db_data, source = resolve_cost_db_then_live(
        db_call=lambda: cost_by_resource_from_db(db, subscription_id, **range_kw),
        live_call=_live_by_resource,
    )
    if db_data:
        if source != "database":
            _enqueue_cost_sync(subscription_id, reason="live_fallback_by_resource")
        return {**db_data, "source": source}
    _enqueue_cost_sync(subscription_id, reason="no_synced_rows")
    return empty_cost_by_resource_response()


@router.get("/by-resource-type", summary="MTD cost by ARM resource type (cost explorer worker)")
def get_costs_by_resource_type(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    resource_types:  Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, None, None, resource_types=resource_types)
    db_data = cost_by_resource_type_from_db(db, subscription_id, **range_kw)
    if db_data:
        return db_data
    return {
        "properties": {
            "columns": [
                {"name": "ResourceType"}, {"name": "DisplayName"}, {"name": "PreTaxCost"},
                {"name": "CostUSD"}, {"name": "Currency"},
            ],
            "rows": [],
        },
        "billing_currency": "CAD",
        "source": "database",
        "sync_required": True,
    }


@router.get("/by-service", summary="Cost by Azure service (database after sync)")
def get_costs_by_service(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    from_date:       Optional[str] = Query(None),
    to_date:         Optional[str] = Query(None),
    resource_types:  Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, from_date, to_date, resource_types=resource_types)
    live_kw = live_range_kw(range_kw)
    token = _live_cost_token(db)
    db_data, source = resolve_cost_db_then_live(
        db_call=lambda: cost_by_service_from_db(db, subscription_id, **range_kw),
        live_call=lambda: query_cost_by_service_live(db, subscription_id, token=token, **live_kw),
    )
    if db_data:
        if source != "database":
            _enqueue_cost_sync(subscription_id, reason="live_fallback_by_service")
        return {**db_data, "source": source}
    _enqueue_cost_sync(subscription_id, reason="no_synced_rows")
    return empty_cost_by_service_response()


@router.get("/summary", summary="Subscription totals (database after sync)")
def get_costs_summary(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    from_date:       Optional[str] = Query(None),
    to_date:         Optional[str] = Query(None),
    resource_types:  Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, from_date, to_date, resource_types=resource_types)
    live_kw = live_range_kw(range_kw)
    token = _live_cost_token(db)
    db_summary, source = resolve_cost_db_then_live(
        db_call=lambda: cost_summary_from_db(db, subscription_id, **range_kw),
        live_call=lambda: query_cost_summary_live(db, subscription_id, token=token, **live_kw),
    )
    if db_summary:
        if source != "database":
            _enqueue_cost_sync(subscription_id, reason="live_fallback_summary")
        return {"subscription_id": subscription_id, "timeframe": timeframe,
                "api_version": source or "database", **db_summary, "source": source}
    _enqueue_cost_sync(subscription_id, reason="no_synced_rows")
    empty = empty_cost_summary_response(**range_kw)
    return {"subscription_id": subscription_id, "timeframe": timeframe,
            "api_version": "database", **empty}


@router.get("/changes", summary="MTD cost increases since the previous Fetch costs run")
def get_costs_changes(
    subscription_id: str = Query(...),
    month: Optional[str] = Query(None, description="YYYY-MM (defaults to current month)"),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    data = get_latest_cost_changes(db, subscription_id, month)
    if not data:
        period = mtd_period_for_timeframe("MonthToDate")
        return {"subscription_id": subscription_id, "has_previous": False, "services": [], **period,
                "source": "database"}
    return {"subscription_id": subscription_id, **data}


@router.get("/forecast", summary="Forecast costs for the current billing period (admin, live Azure)")
def get_cost_forecast(
    request: Request,
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    sub = _scoped_subscription(db, subscription_id)
    return cost_client.query_forecast(sub, timeframe)


@router.get("/budgets", summary="List all budgets configured on a subscription")
def get_budgets(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    from app.dashboard import list_budgets_from_db
    subscription_id = _scoped_subscription(db, subscription_id)
    cached = list_budgets_from_db(db, subscription_id)
    if cached:
        return cached
    require_admin_user(request)
    return cost_client.list_budgets(subscription_id)


@router.get("/dimensions", summary="Available Cost Management filter dimensions (admin, live Azure)")
def get_dimensions(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    sub = _scoped_subscription(db, subscription_id)
    return cost_client.list_dimensions(sub)


@router.get("/history", summary="100 most recent synced CostRecord rows for a subscription")
def cost_history(
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    """Returns the 100 most recent synced cost data rows for the subscription."""
    sub = _scoped_subscription(db, subscription_id)
    records = list_cost_records(db, sub, limit=100)
    return [
        {
            "id": r.id,
            "subscription_id": r.subscription_id,
            "resource_group": r.resource_group,
            "timeframe": r.timeframe,
            "granularity": r.granularity,
            "created_at": str(r.created_at),
        }
        for r in records
    ]


@router.post("/sync", summary="Refresh Dashboard and Cost explorer costs")
def trigger_cost_sync(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
    token: str = Depends(arm_bearer_token),
):
    require_admin_user(request)
    try:
        subscription_id = subscription_id.strip().lower()
        log.info("cost_api.sync_start", subscription_id=subscription_id)
        synced = sync_costs(subscription_id, db, token)
        log.info("cost_api.sync_done", subscription_id=subscription_id, synced=synced)
        return {"status": "ok", "synced": synced, "source": "azure_cost_management"}
    except CostExportReadError as exc:
        raise _cost_api_http_error(exc) from exc
    except Exception as exc:
        log.exception("cost_sync_failed", subscription_id=subscription_id)
        raise HTTPException(500, str(exc)) from exc

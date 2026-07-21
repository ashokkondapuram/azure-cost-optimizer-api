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
    mtd_period_for_timeframe,
)
from app.models import CostRecord
from app.cost_live_query import (
    query_demand_forecast_live,
    query_forecast_daily_live,
    query_forecast_summary_live,
)
from app.cost_resolve import resolve_cost_db_only
from app.cost_timeframes import list_timeframe_catalog
from app.database import get_db
from app.db_sync import sync_costs
from app.auth import arm_bearer_token
from app.user_auth import require_admin_user
from app.validators import ensure_subscription_known
import structlog

log = structlog.get_logger()

router = APIRouter(prefix="/costs", tags=["Cost Management"])

cost_client = AzureCostClient()  # legacy fallback; prefer _live_cost_client(db, token)



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
    from app.auth import get_azure_token
    try:
        return get_azure_token(db)
    except Exception as exc:
        log.warning("cost_api.token_unavailable", error=str(exc)[:300])
        return None


def _live_cost_client(db: Session, token: str | None = None) -> AzureCostClient:
    """Cost client bound to the request DB session and shared bearer token."""
    bearer = token or _live_cost_token(db)
    return AzureCostClient(db=db, token=bearer)


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


def _attach_cost_sync_diagnostics(payload: dict, subscription_id: str) -> dict:
    """Surface recent cost sync failures instead of silent zero totals."""
    from app.cost_explorer_worker import last_cost_sync_error

    err = last_cost_sync_error(subscription_id)
    if not err:
        return payload
    out = {**payload, "cost_sync_error": err}
    lowered = err.lower()
    if "403" in err or "authorization" in lowered or "forbidden" in lowered:
        out["hint"] = (
            "Azure returned an authorization error for Cost Management. "
            "Assign Cost Management Reader on the subscription scope for the service principal."
        )
    return out


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
    scope = f"/subscriptions/{subscription_id}"
    has_type_filter = bool(range_kw.get("resource_types"))
    db_data, source = resolve_cost_db_only(
        db_call=lambda: daily_cost_response_from_db(db, subscription_id, **range_kw),
    )
    if db_data:
        log.info("cost_api.get_costs", subscription_id=subscription_id, timeframe=timeframe,
                 source=source, rows=len(db_data.get("properties", {}).get("rows", [])))
        return {"id": None, "scope": scope, "timeframe": timeframe,
                "granularity": granularity, "data": db_data, "source": source}
    _enqueue_cost_sync(subscription_id, reason="no_synced_rows")
    return {"id": None, "scope": scope, "timeframe": timeframe, "granularity": granularity,
            "data": _attach_cost_sync_diagnostics(empty_daily_cost_response(), subscription_id),
            "source": "database", "sync_required": True}


@router.get("/resource-group", summary="Daily costs for a resource group (database after sync)")
def get_rg_costs(
    subscription_id: str = Query(...),
    resource_group:  str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    from_date:       Optional[str] = Query(None),
    to_date:         Optional[str] = Query(None),
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


@router.get("/resource-daily", summary="Estimated daily spend for one resource (database after sync)")
def get_resource_daily_cost(
    subscription_id: str = Query(...),
    resource_id: str = Query(...),
    days: int = Query(28, ge=7, le=90),
    db: Session = Depends(get_db),
):
    from app.cost_db import resource_daily_cost_series

    subscription_id = _scoped_subscription(db, subscription_id)
    points = resource_daily_cost_series(db, subscription_id, resource_id, days=days)
    has_spend = any(float(p.get("cost") or 0) > 0 for p in points)
    if not has_spend:
        _enqueue_cost_sync(subscription_id, reason="resource_daily_empty")
    return {
        "resource_id": resource_id,
        "days": days,
        "points": points,
        "source": "database" if has_spend else "database",
        "sync_required": not has_spend,
    }


@router.get("/by-resource", summary="Cost per resource ID (database after sync)")
def get_costs_by_resource(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    resource_types:  Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, None, None, resource_types=resource_types)
    db_data, source = resolve_cost_db_only(
        db_call=lambda: cost_by_resource_from_db(db, subscription_id, **range_kw),
    )
    if db_data:
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
    db_data, source = resolve_cost_db_only(
        db_call=lambda: cost_by_service_from_db(db, subscription_id, **range_kw),
    )
    if db_data:
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
    db_summary, source = resolve_cost_db_only(
        db_call=lambda: cost_summary_from_db(db, subscription_id, **range_kw),
    )
    if db_summary:
        return {"subscription_id": subscription_id, "timeframe": timeframe,
                "api_version": source or "database", **db_summary, "source": source}
    _enqueue_cost_sync(subscription_id, reason="no_synced_rows")
    empty = _attach_cost_sync_diagnostics(empty_cost_summary_response(**range_kw), subscription_id)
    return {"subscription_id": subscription_id, "timeframe": timeframe,
            "api_version": "database", **empty, "sync_required": True}


@router.get("/explorer", summary="Batched Cost Explorer payload (database-backed)")
def get_cost_explorer_bundle(
    subscription_id: str = Query(...),
    timeframe: str = Query("MonthToDate"),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD (required for Custom)"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD (required for Custom)"),
    resource_types: Optional[str] = Query(None, description="Comma-separated canonical resource types"),
    compare_enabled: bool = Query(False),
    compare_timeframe: Optional[str] = Query(None),
    compare_from_date: Optional[str] = Query(None),
    compare_to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Single round trip for Cost Explorer summary, daily, by-service, and optional compare."""
    from app.cost_explorer_bundle import build_cost_explorer_bundle

    subscription_id = _scoped_subscription(db, subscription_id)
    range_kw = _cost_range_kwargs(timeframe, from_date, to_date, resource_types=resource_types)
    compare_range_kw = None
    cmp_tf = None
    if compare_enabled and compare_timeframe:
        compare_range_kw = _cost_range_kwargs(
            compare_timeframe, compare_from_date, compare_to_date,
        )
        cmp_tf = compare_timeframe
    return build_cost_explorer_bundle(
        db,
        subscription_id=subscription_id,
        timeframe=timeframe,
        range_kw=range_kw,
        prefer_live=False,
        token=None,
        db_only=True,
        compare_range_kw=compare_range_kw,
        compare_timeframe=cmp_tf,
    )


@router.get("/comparison", summary="Compare two cost periods side-by-side")
def get_cost_comparison(
    subscription_id: str = Query(...),
    current_timeframe: str = Query("MonthToDate", description="Primary period timeframe"),
    compare_timeframe: str = Query("TheLastMonth", description="Comparison period timeframe"),
    current_from_date: Optional[str] = Query(None, description="YYYY-MM-DD for Custom current period"),
    current_to_date: Optional[str] = Query(None),
    compare_from_date: Optional[str] = Query(None, description="YYYY-MM-DD for Custom compare period"),
    compare_to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    from app.cost_comparison import build_cost_comparison

    subscription_id = _scoped_subscription(db, subscription_id)
    current_kw = _cost_range_kwargs(current_timeframe, current_from_date, current_to_date)
    compare_kw = _cost_range_kwargs(compare_timeframe, compare_from_date, compare_to_date)
    current_summary = cost_summary_from_db(db, subscription_id, **current_kw) or empty_cost_summary_response(
        current_timeframe,
        from_date=current_kw.get("from_date"),
        to_date=current_kw.get("to_date"),
    )
    compare_summary = cost_summary_from_db(db, subscription_id, **compare_kw) or empty_cost_summary_response(
        compare_timeframe,
        from_date=compare_kw.get("from_date"),
        to_date=compare_kw.get("to_date"),
    )
    current_services = cost_by_service_from_db(db, subscription_id, **current_kw) or empty_cost_by_service_response()
    compare_services = cost_by_service_from_db(db, subscription_id, **compare_kw) or empty_cost_by_service_response()
    comparison = build_cost_comparison(
        current_summary=current_summary,
        compare_summary=compare_summary,
        current_services=current_services,
        compare_services=compare_services,
    )
    return {
        "subscription_id": subscription_id,
        "current": {"timeframe": current_timeframe, **current_summary},
        "compare": {"timeframe": compare_timeframe, **compare_summary},
        **comparison,
        "source": current_summary.get("source") or "database",
    }


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


@router.get("/forecast", summary="Forecast costs for the current billing period (live Azure)")
def get_cost_forecast(
    subscription_id: str = Query(...),
    timeframe:       str = Query("MonthToDate"),
    db: Session = Depends(get_db),
):
    sub = _scoped_subscription(db, subscription_id)
    token = _live_cost_token(db)
    payload = query_forecast_summary_live(db, sub, timeframe, token=token)
    if payload:
        return payload
    try:
        from app.auth import arm_auth_context

        with arm_auth_context(db=db, token=token):
            return _live_cost_client(db, token).query_forecast(sub, timeframe)
    except Exception as exc:
        raise _cost_api_http_error(exc) from exc


@router.get("/demand-forecast", summary="Monthly history and Azure forecast for demand forecaster")
def get_demand_forecast(
    subscription_id: str = Query(...),
    months_back: int = Query(6, ge=3, le=12),
    db: Session = Depends(get_db),
):
    sub = _scoped_subscription(db, subscription_id)
    token = _live_cost_token(db)
    if not token:
        raise HTTPException(503, "Azure credentials unavailable for live cost forecast.")
    return query_demand_forecast_live(db, sub, months_back=months_back, token=token)


@router.get("/budgets", summary="List all budgets configured on a subscription")
def get_budgets(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    from app.budget_service import list_budgets_unified

    subscription_id = _scoped_subscription(db, subscription_id)
    payload = list_budgets_unified(db, subscription_id)
    if payload["budgets"]:
        return payload["budgets"]
    require_admin_user(request)
    token = _live_cost_token(db)
    if not token:
        raise HTTPException(503, "Azure credentials unavailable for live budgets.")
    from app.auth import arm_auth_context

    with arm_auth_context(db=db, token=token):
        return _live_cost_client(db, token).list_budgets(subscription_id)


@router.get("/dimensions", summary="Available Cost Management filter dimensions (admin, live Azure)")
def get_dimensions(
    request: Request,
    subscription_id: str = Query(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    sub = _scoped_subscription(db, subscription_id)
    token = _live_cost_token(db)
    if not token:
        raise HTTPException(503, "Azure credentials unavailable for live cost dimensions.")
    from app.auth import arm_auth_context

    with arm_auth_context(db=db, token=token):
        return _live_cost_client(db, token).list_dimensions(sub)


@router.get("/history", summary="100 most recent synced CostRecord rows for a subscription")
def cost_history(
    subscription_id: str = Query(..., description="Azure subscription ID (required)"),
    db: Session = Depends(get_db),
):
    """Returns the 100 most recent synced cost data rows for the subscription."""
    sub = _scoped_subscription(db, subscription_id)
    records = (
        db.query(CostRecord)
        .filter(CostRecord.subscription_id == sub)
        .order_by(CostRecord.created_at.desc())
        .limit(100)
        .all()
    )
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


@router.post(
    "/sync",
    summary="Refresh Dashboard and Cost explorer costs",
    status_code=202,
    responses={
        200: {"description": "Sync completed (wait=true only)"},
        202: {"description": "Sync accepted and running in the background"},
    },
)
def trigger_cost_sync(
    request: Request,
    subscription_id: str = Query(...),
    wait: bool = Query(
        False,
        description="Block until sync completes. May time out behind gateways; default is async.",
    ),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    subscription_id = subscription_id.strip().lower()

    if wait:
        token = arm_bearer_token(db)
        try:
            log.info("cost_api.sync_start", subscription_id=subscription_id, wait=True)
            synced = sync_costs(subscription_id, db, token)
            log.info("cost_api.sync_done", subscription_id=subscription_id, synced=synced)
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=200,
                content={"status": "ok", "synced": synced, "source": "azure_cost_management", "async": False},
            )
        except CostExportReadError as exc:
            raise _cost_api_http_error(exc) from exc
        except Exception as exc:
            log.exception("cost_sync_failed", subscription_id=subscription_id)
            raise HTTPException(500, str(exc)) from exc

    from app.cost_explorer_worker import (
        cost_explorer_worker_enabled,
        is_cost_sync_pending,
        request_cost_sync,
    )

    already_pending = is_cost_sync_pending(subscription_id)
    enqueued = request_cost_sync(subscription_id, reason="manual_api")
    log.info(
        "cost_api.sync_enqueued",
        subscription_id=subscription_id,
        already_pending=already_pending,
        enqueued=enqueued,
        scheduled_worker_enabled=cost_explorer_worker_enabled(),
    )
    return {
        "status": "accepted",
        "async": True,
        "already_queued": already_pending or not enqueued,
        "pending": is_cost_sync_pending(subscription_id),
        "scheduled_worker_enabled": cost_explorer_worker_enabled(),
        "subscription_id": subscription_id,
        "source": "azure_cost_management",
    }


@router.post(
    "/retail-prices/sync",
    summary="Backfill Azure retail SKU prices into resource_sku_pricing",
    status_code=200,
)
def trigger_retail_price_sync(
    request: Request,
    subscription_id: Optional[str] = Query(
        None,
        description="Scope inventory SKU discovery to one subscription (prices are global).",
    ),
    force: bool = Query(False, description="Re-fetch even when cached rows are still fresh."),
    fetch_retail_api: bool = Query(True, description="Call Azure Retail Prices API (throttled)."),
    seed_catalog: bool = Query(True, description="Seed catalog-fallback disk prices for common SKUs."),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    if subscription_id:
        subscription_id = ensure_subscription_known(db, subscription_id.strip().lower())

    from app.retail_price_sync import distinct_inventory_regions, sync_retail_sku_prices

    regions = distinct_inventory_regions(db, subscription_id)
    stats = sync_retail_sku_prices(
        db,
        subscription_id=subscription_id,
        regions=regions,
        force=force,
        fetch_retail_api=fetch_retail_api,
        seed_catalog=seed_catalog,
    )
    return {
        "status": "ok",
        "subscription_id": subscription_id,
        "regions": regions,
        "stats": stats,
    }

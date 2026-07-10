"""Admin router — /admin prefix."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.admin_overview import build_optimization_overview
from app.api_explorer import build_api_explorer_context
from app.database import get_db
from app.user_auth import require_admin_user
import structlog

log = structlog.get_logger()

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/optimization/overview", summary="Per-component usage, waste, savings, and rule coverage (admin)")
def admin_optimization_overview(
    request: Request,
    subscription_id: str = Query(...),
    profile: str = Query("default"),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    return build_optimization_overview(db, subscription_id=subscription_id, profile=profile)


@router.get("/api-explorer/context", summary="OpenAPI + token cache metadata for in-app API explorer")
def admin_api_explorer_context(request: Request, db: Session = Depends(get_db)):
    require_admin_user(request)
    return build_api_explorer_context(db)


@router.post("/data/clear", summary="Clear synced inventory, costs, findings, and runs (admin only)")
def clear_database_data(
    request: Request,
    subscription_id: Optional[str] = Query(
        None,
        description="Clear one subscription only; omit to clear all synced data",
    ),
    db: Session = Depends(get_db),
):
    from app.db_clear import clear_synced_data

    require_admin_user(request)
    try:
        return {"status": "ok", **clear_synced_data(db, subscription_id=subscription_id)}
    except Exception as exc:
        log.exception("db_clear_failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

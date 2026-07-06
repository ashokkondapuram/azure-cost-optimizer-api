"""Admin router — /admin prefix."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.admin_overview import build_optimization_overview
from app.database import get_db
from app.user_auth import require_admin_user

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/optimization/overview", summary="Optimization overview across all subscriptions (admin)")
def admin_optimization_overview(request: Request, db: Session = Depends(get_db)):
    require_admin_user(request)
    return build_optimization_overview(db)

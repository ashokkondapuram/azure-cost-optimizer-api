"""Reservation / RI coverage — Azure live data + Advisor + engine findings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth import get_token
from app.database import get_db
from app.reservation_advisor_core import build_reservation_advisor, sync_reservation_advisor
from app.user_auth import require_authenticated_user

router = APIRouter(prefix="/reservations", tags=["Reservation Coverage"])


def _auth_dep(request: Request):
    return require_authenticated_user(request)


def _get_db_and_auth(db: Session = Depends(get_db), _=Depends(_auth_dep)):
    return db


def _optional_arm_headers(db: Session) -> dict[str, str] | None:
    try:
        return {"Authorization": f"Bearer {get_token(db)}"}
    except Exception:
        return None


@router.get("/advisor/{subscription_id}")
def reservation_advisor(
    subscription_id: str,
    commitment_type: str = Query("all", description="all, reserved_instance, savings_plan"),
    month: str | None = Query(None, description="Month YYYY-MM for spend context"),
    include_live_azure: bool = Query(True, description="Fetch live reservations from Azure ARM"),
    db: Session = Depends(_get_db_and_auth),
) -> dict:
    """Unified reservation advisor — merges Azure inventory, Advisor, and engine findings."""
    headers = _optional_arm_headers(db) if include_live_azure else None
    return build_reservation_advisor(
        db,
        subscription_id,
        commitment_type=commitment_type,
        month=month,
        headers=headers,
        include_live_azure=include_live_azure,
    )


@router.post("/sync/{subscription_id}")
def reservation_advisor_sync(
    subscription_id: str,
    trigger_advisor_generate: bool = Query(False),
    db: Session = Depends(_get_db_and_auth),
) -> dict:
    """Sync Azure Advisor and refresh live reservation inventory."""
    token = get_token(db)
    return sync_reservation_advisor(
        db,
        subscription_id,
        token,
        trigger_advisor_generate=trigger_advisor_generate,
    )


@router.get("/coverage/{subscription_id}")
def reservation_coverage(
    subscription_id: str,
    month: str | None = Query(None, description="Month YYYY-MM for spend context"),
    db: Session = Depends(_get_db_and_auth),
) -> dict:
    """Backward-compatible coverage summary."""
    payload = build_reservation_advisor(
        db,
        subscription_id,
        month=month,
        headers=_optional_arm_headers(db),
    )
    return {
        "subscription_id": payload["subscription_id"],
        "month": payload["month"],
        "billing_currency": payload["billing_currency"],
        "total_vm_spend": payload["summary"]["total_vm_spend_monthly"],
        "estimated_coverage_pct": payload["summary"]["estimated_coverage_pct"],
        "total_opportunity_savings_usd": payload["summary"]["total_monthly_opportunity"],
        "commitment_opportunities": payload["recommendations"][:25],
        "underutilised_commitments": payload["underutilised_commitments"],
        "active_commitments": payload["active_commitments"],
        "sources": payload["sources"],
        "warnings": payload["warnings"],
        "source": payload["source"],
    }


@router.get("/recommendations/{subscription_id}")
def reservation_recommendations(
    subscription_id: str,
    commitment_type: str = Query("all", description="Filter: all, reserved_instance, savings_plan"),
    db: Session = Depends(_get_db_and_auth),
) -> dict:
    """Backward-compatible recommendations list."""
    payload = build_reservation_advisor(
        db,
        subscription_id,
        commitment_type=commitment_type,
        headers=_optional_arm_headers(db),
    )
    recs = payload["recommendations"]
    return {
        "subscription_id": payload["subscription_id"],
        "commitment_type_filter": commitment_type,
        "total_recommendations": len(recs),
        "total_estimated_annual_savings_usd": payload["summary"]["total_annual_opportunity"],
        "recommendations": [
            {
                **rec,
                "estimated_monthly_savings_usd": rec.get("estimated_monthly_savings"),
                "estimated_annual_savings_usd": rec.get("estimated_annual_savings"),
            }
            for rec in recs[:50]
        ],
        "sources": payload["sources"],
        "warnings": payload["warnings"],
        "source": payload["source"],
    }

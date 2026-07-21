"""Carbon footprint estimator — estimate CO2e emissions from compute/storage/network spend."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.cost_db import cost_by_service_from_db, cost_by_resource_type_from_db

router = APIRouter(prefix="/carbon", tags=["Carbon Footprint"])

# kgCO2e per USD of Azure service spend (simplified industry estimates)
# Sources: Azure Sustainability Calculator & academic estimates
_EMISSION_FACTORS: dict[str, float] = {
    "virtual machines": 0.23,
    "azure kubernetes service": 0.23,
    "container instances": 0.20,
    "app service": 0.18,
    "azure functions": 0.12,
    "sql database": 0.15,
    "azure cosmos db": 0.14,
    "storage": 0.05,
    "bandwidth": 0.08,
    "azure cdn": 0.06,
    "load balancer": 0.10,
    "vpn gateway": 0.10,
    "azure monitor": 0.04,
    "log analytics": 0.04,
    "azure active directory": 0.02,
    "key vault": 0.02,
    "default": 0.10,
}


def _emission_factor(service_name: str) -> float:
    name = (service_name or "").lower()
    for key, factor in _EMISSION_FACTORS.items():
        if key in name:
            return factor
    return _EMISSION_FACTORS["default"]


def _usd_from_row(row: list) -> float:
    """Extract USD cost from a service-row [ServiceName, PreTaxCost, CostUSD, Currency]."""
    try:
        return float(row[2] or row[1] or 0)
    except (IndexError, TypeError, ValueError):
        return 0.0


@router.get("/estimate/{subscription_id}")
def estimate_carbon_footprint(
    subscription_id: str,
    timeframe: str = Query("MonthToDate", description="Cost timeframe"),
    month: str | None = Query(None, description="Specific month YYYY-MM"),
    db: Session = Depends(get_db),
) -> dict:
    """Estimate monthly CO2e emissions from Azure service spend."""
    service_data = cost_by_service_from_db(db, subscription_id, timeframe=timeframe, month=month)
    if not service_data:
        return {
            "subscription_id": subscription_id,
            "message": "No cost data found. Run a cost sync first.",
            "source": "database",
        }

    rows = (service_data.get("properties") or {}).get("rows") or []
    billing_currency = service_data.get("billing_currency", "CAD")

    services: list[dict] = []
    total_co2e = 0.0
    total_spend_usd = 0.0
    for row in rows:
        service_name = row[0] if row else ""
        usd = _usd_from_row(row)
        factor = _emission_factor(service_name)
        co2e = round(usd * factor, 3)
        total_co2e += co2e
        total_spend_usd += usd
        services.append({
            "service_name": service_name,
            "spend_usd": round(usd, 2),
            "emission_factor_kg_per_usd": factor,
            "estimated_kg_co2e": co2e,
        })

    services.sort(key=lambda x: x["estimated_kg_co2e"], reverse=True)

    # Equivalent metrics
    trees_equivalent = round(total_co2e / 21, 1)  # ~21 kg CO2 absorbed per tree/year
    car_km_equivalent = round(total_co2e / 0.21, 0)  # ~0.21 kg CO2/km for average car

    return {
        "subscription_id": subscription_id,
        "timeframe": timeframe,
        "billing_currency": billing_currency,
        "total_spend_usd": round(total_spend_usd, 2),
        "total_estimated_kg_co2e": round(total_co2e, 2),
        "total_estimated_tonnes_co2e": round(total_co2e / 1000, 4),
        "equivalent_trees_to_offset_annual": trees_equivalent,
        "equivalent_car_km": int(car_km_equivalent),
        "methodology": "spend-based estimation using Azure service emission factors",
        "services": services,
        "source": "database",
    }


@router.get("/by-resource-type/{subscription_id}")
def carbon_by_resource_type(
    subscription_id: str,
    month: str | None = Query(None, description="Month YYYY-MM"),
    db: Session = Depends(get_db),
) -> dict:
    """Estimate CO2e emissions broken down by ARM resource type."""
    data = cost_by_resource_type_from_db(db, subscription_id, month=month)
    if not data:
        return {
            "subscription_id": subscription_id,
            "message": "No resource type cost data found.",
            "source": "database",
        }

    rows = (data.get("properties") or {}).get("rows") or []
    result: list[dict] = []
    total_co2e = 0.0
    for row in rows:
        rt = row[1] or row[0] or ""  # DisplayName preferred
        usd = float(row[3] or row[2] or 0)
        factor = _emission_factor(rt)
        co2e = round(usd * factor, 3)
        total_co2e += co2e
        result.append({"resource_type": rt, "spend_usd": round(usd, 2), "estimated_kg_co2e": co2e})

    result.sort(key=lambda x: x["estimated_kg_co2e"], reverse=True)
    return {
        "subscription_id": subscription_id,
        "total_estimated_kg_co2e": round(total_co2e, 2),
        "resource_types": result,
        "source": "database",
    }

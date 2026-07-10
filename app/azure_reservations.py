"""Azure Reservations & Savings Plans REST client (ARM)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import structlog

from app.http_client import BASE, AzureAPIError, get_all_pages

log = structlog.get_logger()

CAPACITY_API_VERSION = "2022-11-01"
CONSUMPTION_API_VERSION = "2023-11-01"
BILLING_BENEFITS_API_VERSION = "2022-11-01"


class ReservationsClient:
    """List reservations, utilization summaries, and savings plans via ARM."""

    def __init__(self, headers: dict[str, str]):
        self._headers = headers

    def _safe_pages(self, url: str, params: dict[str, str], *, label: str) -> list[dict[str, Any]]:
        try:
            return get_all_pages(url, self._headers, params, use_cache=False)
        except AzureAPIError as exc:
            log.warning("azure_reservations.api_error", endpoint=label, status=exc.status, message=exc.message[:160])
            return []
        except Exception as exc:
            log.warning("azure_reservations.request_failed", endpoint=label, error=str(exc)[:160])
            return []

    def list_reservations(self, subscription_id: str) -> list[dict[str, Any]]:
        sub = subscription_id.strip().lower()
        url = f"{BASE}/subscriptions/{sub}/providers/microsoft.capacity/reservations"
        return self._safe_pages(url, {"api-version": CAPACITY_API_VERSION}, label="reservations")

    def list_reservation_summaries(
        self,
        subscription_id: str,
        *,
        start: date | None = None,
        end: date | None = None,
        grain: str = "monthly",
    ) -> list[dict[str, Any]]:
        sub = subscription_id.strip().lower()
        end_d = end or date.today()
        start_d = start or (end_d.replace(day=1))
        url = f"{BASE}/subscriptions/{sub}/providers/Microsoft.Consumption/reservationSummaries"
        params = {
            "api-version": CONSUMPTION_API_VERSION,
            "grain": grain,
            "startDate": start_d.isoformat(),
            "endDate": end_d.isoformat(),
        }
        return self._safe_pages(url, params, label="reservationSummaries")

    def list_savings_plan_summaries(
        self,
        subscription_id: str,
        *,
        start: date | None = None,
        end: date | None = None,
        grain: str = "monthly",
    ) -> list[dict[str, Any]]:
        sub = subscription_id.strip().lower()
        end_d = end or date.today()
        start_d = start or end_d.replace(day=1)
        url = f"{BASE}/subscriptions/{sub}/providers/Microsoft.Consumption/savingsPlanSummaries"
        params = {
            "api-version": CONSUMPTION_API_VERSION,
            "grain": grain,
            "startDate": start_d.isoformat(),
            "endDate": end_d.isoformat(),
        }
        return self._safe_pages(url, params, label="savingsPlanSummaries")

    def list_savings_plans(self) -> list[dict[str, Any]]:
        """Tenant-scoped savings plans (requires BillingBenefits read)."""
        url = f"{BASE}/providers/Microsoft.BillingBenefits/savingsPlans"
        return self._safe_pages(url, {"api-version": BILLING_BENEFITS_API_VERSION}, label="savingsPlans")

    def list_reservation_recommendations(
        self,
        subscription_id: str,
        *,
        scope: str = "Shared",
    ) -> list[dict[str, Any]]:
        """Azure Capacity reservation purchase recommendations for a subscription."""
        sub = subscription_id.strip().lower()
        url = f"{BASE}/subscriptions/{sub}/providers/microsoft.capacity/reservationRecommendations"
        params: dict[str, str] = {"api-version": CAPACITY_API_VERSION}
        if scope:
            params["scope"] = scope
        return self._safe_pages(url, params, label="reservationRecommendations")


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_reservation(item: dict[str, Any]) -> dict[str, Any]:
    props = item.get("properties") or {}
    sku = props.get("sku") or {}
    util = props.get("utilization") or {}
    return {
        "id": item.get("id") or "",
        "name": item.get("name") or "",
        "display_name": props.get("displayName") or item.get("name") or "",
        "commitment_type": "reserved_instance",
        "reserved_resource_type": props.get("reservedResourceType") or props.get("productName") or "",
        "sku_name": sku.get("name") if isinstance(sku, dict) else str(sku or ""),
        "term": props.get("term") or "",
        "quantity": props.get("quantity"),
        "provisioning_state": props.get("provisioningState") or "",
        "expiry_date": (props.get("expiryDate") or "")[:10],
        "purchase_date": (props.get("purchaseDate") or props.get("purchaseDateTime") or "")[:10],
        "utilization_percent": _parse_float(
            util.get("aggregatedUtilization")
            or util.get("utilizationPercentage")
            or props.get("utilizationPercentage")
        ),
        "scope": props.get("appliedScopeType") or props.get("appliedScopes", [{}])[0].get("scopeType") if props.get("appliedScopes") else "",
        "source": "azure_capacity",
    }


def normalize_savings_plan(item: dict[str, Any], subscription_id: str = "") -> dict[str, Any]:
    props = item.get("properties") or {}
    sub = subscription_id.strip().lower()
    applied = props.get("appliedScopes") or props.get("commitmentScopes") or []
    applies_to_sub = not sub or any(
        sub in str(scope.get("subscriptionId") or scope.get("scope") or "").lower()
        for scope in applied
        if isinstance(scope, dict)
    )
    if sub and applied and not applies_to_sub:
        return {}
    return {
        "id": item.get("id") or "",
        "name": item.get("name") or "",
        "display_name": props.get("displayName") or item.get("name") or "",
        "commitment_type": "savings_plan",
        "term": props.get("term") or props.get("billingPlan") or "",
        "provisioning_state": props.get("provisioningState") or props.get("status") or "",
        "expiry_date": (props.get("expiryDate") or props.get("validityEndDate") or "")[:10],
        "purchase_date": (props.get("purchaseDate") or "")[:10],
        "hourly_commitment": _parse_float(props.get("commitmentAmount") or props.get("hourlyCommitment")),
        "utilization_percent": _parse_float(props.get("utilizationPercentage") or props.get("utilization", {}).get("utilizationPercentage")),
        "scope": "shared" if len(applied) > 1 else "single",
        "source": "azure_billing_benefits",
    }


def normalize_reservation_summary(item: dict[str, Any]) -> dict[str, Any]:
    props = item.get("properties") or item
    return {
        "reservation_id": props.get("reservationId") or props.get("reservationOrderId") or "",
        "reserved_resource_type": props.get("reservedResourceType") or "",
        "sku_name": props.get("skuName") or "",
        "utilization_percent": _parse_float(
            props.get("avgUtilizationPercentage")
            or props.get("utilizationPercentage")
            or props.get("usedHours") and props.get("reservedHours")
            and round(100.0 * float(props["usedHours"]) / max(float(props["reservedHours"]), 1), 1)
        ),
        "used_amount": _parse_float(props.get("usedQuantity") or props.get("usedAmount")),
        "total_amount": _parse_float(props.get("reservedQuantity") or props.get("totalAmount")),
        "currency": props.get("billingCurrency") or props.get("currency") or "USD",
        "grain": props.get("grain") or "",
        "source": "azure_consumption",
    }


def _money_value(value: Any) -> float | None:
    if isinstance(value, dict):
        return _parse_float(value.get("value") or value.get("amount"))
    return _parse_float(value)


def _term_years(term: str) -> int:
    raw = (term or "").upper()
    if "3" in raw or raw in {"P3Y", "THREEYEARS", "THREE_YEAR"}:
        return 3
    return 1


def normalize_reservation_recommendation(item: dict[str, Any]) -> dict[str, Any]:
    props = item.get("properties") or {}
    term = props.get("term") or ""
    years = _term_years(str(term))
    cost_no_ri = _money_value(props.get("costWithNoReservedInstances"))
    cost_with_ri = _money_value(props.get("totalCostWithReservedInstances"))
    net_savings = _money_value(props.get("netSavings"))
    period_saving = None
    if cost_no_ri is not None and cost_with_ri is not None:
        period_saving = round(max(0.0, cost_no_ri - cost_with_ri), 2)
    elif net_savings is not None:
        period_saving = round(max(0.0, net_savings), 2)
    lookback = str(props.get("lookBackPeriod") or "Last30Days")
    period_days = 30
    if "7" in lookback:
        period_days = 7
    elif "60" in lookback:
        period_days = 60
    monthly_saving = round((period_saving or 0) * 30 / max(period_days, 1), 2) if period_saving else 0.0
    sku = props.get("skuName") or props.get("sku") or {}
    sku_name = sku.get("name") if isinstance(sku, dict) else str(sku or "")
    return {
        "id": item.get("id") or item.get("name") or "",
        "commitment_type": "reserved_instance",
        "plan_id": f"reserved_instance_{years}yr",
        "title": props.get("displayName") or sku_name or "Reservation recommendation",
        "sku_name": sku_name,
        "reserved_resource_type": props.get("reservedResourceType") or "",
        "term": term,
        "years": years,
        "recommended_quantity": props.get("recommendedQuantity"),
        "lookback_period": lookback,
        "monthly_saving": monthly_saving,
        "annual_saving": round(monthly_saving * 12, 2),
        "scope": props.get("scope") or props.get("appliedScopeType") or "",
        "source": "azure_capacity_recommendations",
    }


def normalize_savings_plan_summary(item: dict[str, Any]) -> dict[str, Any]:
    props = item.get("properties") or item
    return {
        "savings_plan_id": props.get("savingsPlanId") or props.get("billingBenefitId") or "",
        "utilization_percent": _parse_float(
            props.get("avgUtilizationPercentage") or props.get("utilizationPercentage")
        ),
        "used_amount": _parse_float(props.get("usedAmount")),
        "total_amount": _parse_float(props.get("totalAmount")),
        "currency": props.get("billingCurrency") or props.get("currency") or "USD",
        "source": "azure_consumption",
    }


def fetch_live_commitments(subscription_id: str, headers: dict[str, str]) -> dict[str, Any]:
    """Fetch and normalize Azure reservation + savings plan inventory."""
    client = ReservationsClient(headers)
    sub = subscription_id.strip().lower()

    reservations = [normalize_reservation(r) for r in client.list_reservations(sub)]
    reservations = [r for r in reservations if r.get("id")]

    month_start = date.today().replace(day=1)
    res_summaries = [
        normalize_reservation_summary(s)
        for s in client.list_reservation_summaries(sub, start=month_start)
    ]
    sp_summaries = [
        normalize_savings_plan_summary(s)
        for s in client.list_savings_plan_summaries(sub, start=month_start)
    ]

    savings_plans = []
    for raw in client.list_savings_plans():
        normalized = normalize_savings_plan(raw, sub)
        if normalized:
            savings_plans.append(normalized)

    util_by_res_id = {
        s["reservation_id"]: s["utilization_percent"]
        for s in res_summaries
        if s.get("reservation_id") and s.get("utilization_percent") is not None
    }
    for res in reservations:
        rid = res.get("id") or ""
        if rid in util_by_res_id and res.get("utilization_percent") is None:
            res["utilization_percent"] = util_by_res_id[rid]
        short_id = rid.rsplit("/", 1)[-1]
        if short_id in util_by_res_id and res.get("utilization_percent") is None:
            res["utilization_percent"] = util_by_res_id[short_id]

    reservation_recommendations = [
        normalize_reservation_recommendation(r)
        for r in client.list_reservation_recommendations(sub)
    ]
    reservation_recommendations = [r for r in reservation_recommendations if r.get("id")]

    return {
        "reservations": reservations,
        "savings_plans": savings_plans,
        "reservation_summaries": res_summaries,
        "savings_plan_summaries": sp_summaries,
        "reservation_recommendations": reservation_recommendations,
        "azure_fetched": True,
    }

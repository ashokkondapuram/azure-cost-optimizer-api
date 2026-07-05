"""Canonical FOCUS → internal field mapping for Azure cost exports.

Reference: https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus

Rules:
  - Actual-cost exports use BilledCost (billing currency) and x_BilledCostInUsd (USD).
  - Do NOT use EffectiveCost / x_EffectiveCostInUsd for actual spend (amortized).
  - ServiceName is the FOCUS service offering; x_SkuMeterCategory is legacy meter category only.
  - BillingCurrency is the invoice currency; x_PricingCurrency is pricing currency (different).
  - ChargePeriodStart is the usage/charge day for daily rollups.
"""
from __future__ import annotations

# ── FOCUS 1.0+ (primary) ──────────────────────────────────────────────────────

COL_BILLED_COST = ["BilledCost"]
COL_BILLED_USD = ["x_BilledCostInUsd"]
COL_BILLING_CURRENCY = ["BillingCurrency"]
COL_SUBSCRIPTION = ["SubAccountId"]
COL_RESOURCE_ID = ["ResourceId"]
COL_RESOURCE_TYPE = ["ResourceType", "x_ResourceType"]
COL_RESOURCE_GROUP = ["x_ResourceGroupName"]
COL_SERVICE_NAME = ["ServiceName", "x_SkuMeterCategory"]
COL_USAGE_DATE = ["ChargePeriodStart", "x_ServicePeriodStart"]

# ── Legacy Actual / Amortized export columns (fallback only) ─────────────────

LEGACY_BILLED_COST = ["CostInBillingCurrency", "PreTaxCost", "Cost"]
LEGACY_BILLED_USD = ["CostInUsd", "CostInUSD", "PreTaxCostUSD"]
LEGACY_CURRENCY = ["Currency", "BillingCurrencyCode"]
LEGACY_SUBSCRIPTION = ["SubscriptionId", "SubscriptionGuid", "SubscriptionID"]
LEGACY_RESOURCE_ID = ["InstanceId", "instanceId", "ResourceID"]
LEGACY_RESOURCE_GROUP = ["ResourceGroupName", "ResourceGroup", "resourceGroupName"]
LEGACY_SERVICE_NAME = ["MeterCategory", "ConsumedService"]
LEGACY_USAGE_DATE = ["UsageDate", "Date", "BillingPeriodStartDate", "BillingPeriodStart"]

# Combined pick lists (FOCUS first, then legacy)
PICK_BILLED_COST = COL_BILLED_COST + LEGACY_BILLED_COST
PICK_BILLED_USD = COL_BILLED_USD + LEGACY_BILLED_USD
PICK_BILLING_CURRENCY = COL_BILLING_CURRENCY + LEGACY_CURRENCY
PICK_SUBSCRIPTION = COL_SUBSCRIPTION + LEGACY_SUBSCRIPTION
PICK_RESOURCE_ID = COL_RESOURCE_ID + LEGACY_RESOURCE_ID
PICK_RESOURCE_TYPE = COL_RESOURCE_TYPE
PICK_RESOURCE_GROUP = COL_RESOURCE_GROUP + LEGACY_RESOURCE_GROUP
PICK_SERVICE_NAME = COL_SERVICE_NAME + LEGACY_SERVICE_NAME
PICK_USAGE_DATE = COL_USAGE_DATE + LEGACY_USAGE_DATE


def normalize_usage_date(value: str) -> str:
    """Return YYYY-MM-DD from FOCUS ISO datetimes or legacy MM/DD/YYYY export dates."""
    from datetime import date as date_type

    raw = (value or "").strip()
    if not raw:
        return ""
    # ISO: 2026-06-15 or 2026-06-15T00:00:00Z
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    # Legacy Azure cost export: MM/DD/YYYY (e.g. 06/15/2026)
    if "/" in raw:
        parts = [p.strip() for p in raw.split("/")]
        if len(parts) >= 3:
            try:
                month = int(parts[0])
                day = int(parts[1])
                year = int(parts[2][:4])
                return date_type(year, month, day).isoformat()
            except (ValueError, TypeError):
                pass
    try:
        return date_type.fromisoformat(raw[:10]).isoformat()
    except ValueError:
        return ""


def normalize_arm_id(resource_id: str) -> str:
    """Canonical ARM resource ID for matching blob ResourceId to inventory rows."""
    return (resource_id or "").strip().lower().rstrip("/")


# Internal normalized row → API / DB field names
INTERNAL_TO_API = {
    "cost": "PreTaxCost",           # BilledCost in billing currency
    "cost_usd": "CostUSD",          # x_BilledCostInUsd
    "currency": "Currency",         # BillingCurrency
    "date": "UsageDate",            # from ChargePeriodStart (YYYY-MM-DD)
    "resource_id": "ResourceId",
    "resource_type": "ResourceType",
    "resource_group": "ResourceGroup",
    "service_name": "ServiceName",
}

# DB table column mapping (blob import → PostgreSQL)
DB_MAPPING = {
    "cost_by_service": {
        "service_name": "ServiceName",
        "cost_billing": "BilledCost / PreTaxCost",
        "cost_usd": "x_BilledCostInUsd / CostUSD",
        "billing_currency": "BillingCurrency",
        "month": "YYYY-MM from ChargePeriodStart",
    },
    "cost_by_resource": {
        "resource_id": "ResourceId",
        "service_name": "ServiceName",
        "resource_group": "x_ResourceGroupName",
        "resource_type": "ResourceType / x_ResourceType",
        "cost_billing": "BilledCost / PreTaxCost",
        "cost_usd": "x_BilledCostInUsd / CostUSD",
        "billing_currency": "BillingCurrency",
    },
    "cost_daily_by_service": {
        "service_name": "ServiceName",
        "cost_date": "ChargePeriodStart (date)",
        "cost_billing": "BilledCost / PreTaxCost",
        "cost_usd": "x_BilledCostInUsd / CostUSD",
        "billing_currency": "BillingCurrency",
    },
    "cost_snapshots": {
        "resource_group": "x_ResourceGroupName",
        "cost_date": "ChargePeriodStart (date)",
        "cost_billing": "BilledCost / PreTaxCost",
        "cost_usd": "x_BilledCostInUsd / CostUSD",
        "currency": "BillingCurrency",
    },
    "resource_snapshots": {
        "monthly_cost_billing": "BilledCost / PreTaxCost (MTD)",
        "monthly_cost_usd": "x_BilledCostInUsd (MTD)",
        "billing_currency": "BillingCurrency",
        "azure_service_name": "ServiceName",
    },
}

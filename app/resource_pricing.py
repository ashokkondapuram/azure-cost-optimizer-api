"""Resolve SKU and pricing model per resource; persist pricing profiles."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.azure_service_cost_catalog import (
    CostType,
    classify_resource_type,
    cost_type_for_canonical,
)
from app.models import ResourcePricingProfile


RESERVED_INSTANCE_DISCOUNTS: dict[str, float] = {"1yr": 0.36, "3yr": 0.53}
SAVINGS_PLAN_DISCOUNTS: dict[str, float] = {"1yr": 0.14, "3yr": 0.32}


def compare_commitment_options(monthly_cost_usd: float, vm_size: str = "") -> dict[str, Any]:
    """Compare RI vs Savings Plan savings for a monthly on-demand baseline."""
    monthly = float(monthly_cost_usd or 0.0)
    options = [
        {
            "option": "reserved_instance_1yr",
            "monthly_savings_usd": round(monthly * RESERVED_INSTANCE_DISCOUNTS["1yr"], 2),
            "annual_savings_usd": round(monthly * RESERVED_INSTANCE_DISCOUNTS["1yr"] * 12, 2),
            "term": "1 year",
        },
        {
            "option": "reserved_instance_3yr",
            "monthly_savings_usd": round(monthly * RESERVED_INSTANCE_DISCOUNTS["3yr"], 2),
            "annual_savings_usd": round(monthly * RESERVED_INSTANCE_DISCOUNTS["3yr"] * 12, 2),
            "three_year_savings_usd": round(monthly * RESERVED_INSTANCE_DISCOUNTS["3yr"] * 36, 2),
            "term": "3 years",
        },
        {
            "option": "savings_plan_1yr",
            "monthly_savings_usd": round(monthly * SAVINGS_PLAN_DISCOUNTS["1yr"], 2),
            "annual_savings_usd": round(monthly * SAVINGS_PLAN_DISCOUNTS["1yr"] * 12, 2),
            "term": "1 year",
        },
        {
            "option": "savings_plan_3yr",
            "monthly_savings_usd": round(monthly * SAVINGS_PLAN_DISCOUNTS["3yr"], 2),
            "annual_savings_usd": round(monthly * SAVINGS_PLAN_DISCOUNTS["3yr"] * 12, 2),
            "three_year_savings_usd": round(monthly * SAVINGS_PLAN_DISCOUNTS["3yr"] * 36, 2),
            "term": "3 years",
        },
    ]
    best = max(options, key=lambda row: row["monthly_savings_usd"])
    return {
        "vm_size": vm_size,
        "monthly_cost_usd": round(monthly, 2),
        "options": options,
        "best_option": best["option"],
        "best_monthly_savings_usd": best["monthly_savings_usd"],
        "annual_savings_usd": best["annual_savings_usd"],
        "recommendation": (
            f"For {vm_size or 'this workload'}, {best['option'].replace('_', ' ')} "
            f"offers the highest estimated monthly savings."
        ),
    }


def _find_pricing_profile(db: Session, subscription_id: str, resource_id: str) -> ResourcePricingProfile | None:
    """Find pricing profile in DB or pending session inserts (autoflush may be off)."""
    from app.focus_mapping import normalize_arm_id
    from sqlalchemy import func

    sub = subscription_id.strip().lower()
    rid = normalize_arm_id(resource_id)
    if not rid:
        return None

    def _matches(row: ResourcePricingProfile) -> bool:
        return (
            (row.subscription_id or "").strip().lower() == sub
            and normalize_arm_id(row.resource_id or "") == rid
        )

    for obj in list(db.new):
        if isinstance(obj, ResourcePricingProfile) and _matches(obj):
            return obj

    for obj in db.identity_map.values():
        if isinstance(obj, ResourcePricingProfile) and _matches(obj):
            return obj

    return (
        db.query(ResourcePricingProfile)
        .filter(
            ResourcePricingProfile.subscription_id == sub,
            func.lower(ResourcePricingProfile.resource_id) == rid,
        )
        .first()
    )


def _dedupe_pending_pricing_profiles(db: Session) -> int:
    """Collapse duplicate pending pricing profile rows before flush/commit."""
    from app.focus_mapping import normalize_arm_id

    latest: dict[tuple[str, str], ResourcePricingProfile] = {}
    to_remove: list[ResourcePricingProfile] = []

    for obj in list(db.new):
        if not isinstance(obj, ResourcePricingProfile):
            continue
        key = (
            (obj.subscription_id or "").strip().lower(),
            normalize_arm_id(obj.resource_id or ""),
        )
        if not key[1]:
            continue
        if key in latest:
            to_remove.append(latest[key])
        latest[key] = obj

    for obj in to_remove:
        if obj in db.new:
            db.expunge(obj)

    return len(to_remove)


def dedupe_resource_pricing_profiles(db: Session, subscription_id: str) -> int:
    """Remove duplicate committed pricing profiles for the same ARM resource ID."""
    from app.focus_mapping import normalize_arm_id

    sub = subscription_id.strip().lower()
    rows = (
        db.query(ResourcePricingProfile)
        .filter(ResourcePricingProfile.subscription_id == sub)
        .order_by(ResourcePricingProfile.synced_at.desc())
        .all()
    )
    seen: set[str] = set()
    removed = 0
    for row in rows:
        rid = normalize_arm_id(row.resource_id or "")
        if not rid:
            continue
        if rid in seen:
            db.delete(row)
            removed += 1
            continue
        seen.add(rid)
        if row.resource_id != rid:
            row.resource_id = rid
    return removed


def _apply_pricing_profile_fields(
    row: ResourcePricingProfile,
    *,
    resource_name: str,
    canonical_type: str,
    profile: dict[str, Any],
    free_tier_json: str,
    profile_json: str,
    synced_at: datetime,
) -> None:
    row.resource_name = resource_name
    row.canonical_type = canonical_type
    row.sku = profile.get("sku")
    row.sku_name = profile.get("sku_name")
    row.sku_tier = profile.get("sku_tier")
    row.pricing_model = profile.get("pricing_model")
    row.cost_type = profile.get("cost_type")
    row.service_name = profile.get("service_name")
    row.free_tier_json = free_tier_json
    row.profile_json = profile_json
    row.synced_at = synced_at

PricingModel = Literal[
    "always_free",
    "pay_as_you_go",
    "free_tier_limited",
    "free_tier_monthly",
    "free_tier_12_months",
    "hybrid",
    "reserved_capable",
]

FreeTierDuration = Literal["always", "12_months_new_account", "none"]

# Per-canonical default pricing when SKU is unknown.
_DEFAULT_PRICING_MODEL: dict[str, PricingModel] = {
    "compute/vm": "reserved_capable",
    "compute/vmss": "reserved_capable",
    "compute/disk": "pay_as_you_go",
    "compute/snapshot": "pay_as_you_go",
    "containers/aks": "pay_as_you_go",
    "containers/aci": "pay_as_you_go",
    "storage/account": "free_tier_monthly",
    "network/publicip": "pay_as_you_go",
    "network/vnet": "hybrid",
    "network/nic": "always_free",
    "network/nsg": "always_free",
    "network/nat": "pay_as_you_go",
    "network/loadbalancer": "hybrid",
    "network/appgateway": "pay_as_you_go",
    "network/privateendpoint": "pay_as_you_go",
    "network/privatelinkservice": "pay_as_you_go",
    "network/privatedns": "pay_as_you_go",
    "network/firewall": "pay_as_you_go",
    "network/cdn": "pay_as_you_go",
    "database/sql": "pay_as_you_go",
    "database/cosmosdb": "free_tier_monthly",
    "database/postgresql": "pay_as_you_go",
    "database/redis": "pay_as_you_go",
    "appservice/webapp": "pay_as_you_go",
    "appservice/plan": "hybrid",
    "appservice/staticweb": "free_tier_limited",
    "security/keyvault": "hybrid",
    "monitoring/loganalytics": "free_tier_monthly",
    "monitoring/appinsights": "free_tier_monthly",
    "integration/apim": "hybrid",
    "messaging/eventhub": "pay_as_you_go",
    "messaging/servicebus": "pay_as_you_go",
    "automation/automation": "free_tier_monthly",
    "search/cognitivesearch": "pay_as_you_go",
}

# SKU tier rows per canonical type (Azure pricing calculator / retail tiers).
CANONICAL_SKU_PRICING: dict[str, tuple[dict[str, Any], ...]] = {
    "containers/acr": (
        {
            "sku": "Basic",
            "pricing_model": "free_tier_limited",
            "cost_type": "conditional",
            "free_tier": {
                "duration": "always",
                "limit": "10 GB storage",
                "notes": "No registry unit charge; storage over 10 GB bills.",
            },
        },
        {"sku": "Standard", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Premium", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
    ),
    "security/keyvault": (
        {
            "sku": "standard",
            "pricing_model": "hybrid",
            "cost_type": "conditional",
            "free_tier": {
                "duration": "always",
                "limit": "10,000 secret transactions/month",
                "notes": "Standard tier operations mostly free; Premium HSM bills.",
            },
        },
        {"sku": "premium", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
    ),
    "appservice/plan": (
        {
            "sku": "Free",
            "pricing_model": "always_free",
            "cost_type": "free",
            "free_tier": {"duration": "always", "limit": "F1 shared capacity", "notes": "Always-free plan SKU."},
        },
        {
            "sku": "Shared",
            "pricing_model": "free_tier_limited",
            "cost_type": "conditional",
            "free_tier": {"duration": "always", "limit": "D1 shared instance", "notes": "Low-cost shared compute."},
        },
        {"sku": "Basic", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Standard", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Premium", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "PremiumV2", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "PremiumV3", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Isolated", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
    ),
    "appservice/staticweb": (
        {
            "sku": "Free",
            "pricing_model": "free_tier_limited",
            "cost_type": "conditional",
            "free_tier": {"duration": "always", "limit": "100 GB bandwidth/month", "notes": "Free tier for static sites."},
        },
        {"sku": "Standard", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
    ),
    "network/loadbalancer": (
        {
            "sku": "Basic",
            "pricing_model": "hybrid",
            "cost_type": "conditional",
            "free_tier": {
                "duration": "always",
                "limit": "Included with VMs for Basic SKU",
                "notes": "No hourly charge for Basic LB; data processed may bill.",
            },
        },
        {"sku": "Standard", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Gateway", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
    ),
    "network/firewall": (
        {"sku": "Standard", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Premium", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
    ),
    "network/appgateway": (
        {"sku": "Standard_v2", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "WAF_v2", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
    ),
    "storage/account": (
        {
            "sku": "Standard_LRS",
            "pricing_model": "free_tier_monthly",
            "cost_type": "conditional",
            "free_tier": {
                "duration": "12_months_new_account",
                "limit": "5 GB LRS blob storage",
                "notes": "Azure free account includes 5 GB hot block blob for 12 months.",
            },
        },
        {"sku": "Premium_LRS", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Standard_GRS", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Standard_RAGRS", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Standard_ZRS", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
    ),
    "compute/disk": (
        {"sku": "Standard_LRS", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "StandardSSD_LRS", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Premium_LRS", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "UltraSSD_LRS", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
    ),
    "database/cosmosdb": (
        {
            "sku": "Free",
            "pricing_model": "free_tier_monthly",
            "cost_type": "conditional",
            "free_tier": {
                "duration": "always",
                "limit": "1,000 RU/s and 25 GB storage",
                "notes": "Free tier per subscription.",
            },
        },
        {"sku": "Provisioned", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Serverless", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
    ),
    "integration/apim": (
        {
            "sku": "Consumption",
            "pricing_model": "pay_as_you_go",
            "cost_type": "costed",
            "free_tier": {
                "duration": "always",
                "limit": "1 million calls/month",
                "notes": "Consumption tier includes a free call allowance.",
            },
        },
        {"sku": "Developer", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Basic", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Standard", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Premium", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
    ),
    "monitoring/loganalytics": (
        {
            "sku": "PerGB2018",
            "pricing_model": "free_tier_monthly",
            "cost_type": "costed",
            "free_tier": {
                "duration": "always",
                "limit": "5 GB ingestion/month per billing account",
                "notes": "Allowance shared across Log Analytics and Application Insights.",
            },
        },
    ),
    "monitoring/appinsights": (
        {
            "sku": "Basic",
            "pricing_model": "free_tier_monthly",
            "cost_type": "conditional",
            "free_tier": {
                "duration": "always",
                "limit": "5 GB ingestion/month",
                "notes": "Shared with Log Analytics workspace billing.",
            },
        },
    ),
    "containers/aks": (
        {"sku": "Free", "pricing_model": "always_free", "cost_type": "free",
         "free_tier": {"duration": "always", "limit": "Control plane", "notes": "Free tier control plane."}},
        {"sku": "Standard", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
        {"sku": "Premium", "pricing_model": "pay_as_you_go", "cost_type": "costed"},
    ),
}

# Service-level free tier when no SKU tier match (from full Azure catalog).
def _build_service_free_tier() -> dict[str, dict[str, Any]]:
    from app.azure_service_cost_catalog import service_free_tier_map

    return service_free_tier_map()


SERVICE_FREE_TIER: dict[str, dict[str, Any]] = _build_service_free_tier()


def service_label_for_canonical(canonical_type: str) -> str | None:
    from app.resource_type_map import arm_types_for_canonical

    arms = arm_types_for_canonical(canonical_type)
    if not arms:
        return None
    from app.cost_utils import service_label_for_arm_type

    return service_label_for_arm_type(arms[0]) or None


def default_pricing_model_for_canonical(canonical_type: str) -> str | None:
    return _DEFAULT_PRICING_MODEL.get((canonical_type or "").strip().lower())


def sku_pricing_table_rows() -> list[dict[str, Any]]:
    """Flatten canonical SKU pricing reference table."""
    rows: list[dict[str, Any]] = []
    for canonical, tiers in sorted(CANONICAL_SKU_PRICING.items()):
        for tier in tiers:
            rows.append({"canonical_type": canonical, **tier})
    return rows


def _sku_tokens(sku_label: str | None, sku_json: dict[str, Any] | None) -> list[str]:
    tokens: list[str] = []
    payload = sku_json or {}
    for value in (
        sku_label,
        payload.get("name"),
        payload.get("tier"),
        payload.get("vm_size"),
        payload.get("size"),
        payload.get("family"),
    ):
        if not value:
            continue
        text = str(value).strip()
        if text:
            tokens.append(text)
    return tokens


def _normalize_token(token: str) -> str:
    base = token.strip().lower()
    base = re.split(r"[\s_(]", base, maxsplit=1)[0]
    return base


def _match_sku_tier(canonical_type: str, tokens: list[str]) -> dict[str, Any] | None:
    tiers = CANONICAL_SKU_PRICING.get((canonical_type or "").strip().lower()) or ()
    if not tiers:
        return None
    normalized = {_normalize_token(t) for t in tokens if t}
    for tier in tiers:
        sku_key = _normalize_token(str(tier.get("sku") or ""))
        if sku_key and sku_key in normalized:
            return tier
        for token in tokens:
            if sku_key and sku_key in token.lower():
                return tier
    return None


def resolve_resource_pricing_profile(
    *,
    canonical_type: str,
    sku_label: str | None = None,
    sku_json: dict[str, Any] | None = None,
    service_name: str | None = None,
    cost_mtd: float = 0.0,
) -> dict[str, Any]:
    """Resolve SKU, pricing model, cost type, and free tier for one resource."""
    from app.azure_service_cost_catalog import (
        resolve_service_name,
        service_catalog_row,
    )

    canonical = (canonical_type or "").strip().lower()
    tokens = _sku_tokens(sku_label, sku_json)
    sku_tier = _match_sku_tier(canonical, tokens)

    svc = service_name or service_label_for_canonical(canonical) or ""
    resolved_svc = resolve_service_name(svc) or svc
    catalog_row = service_catalog_row(svc) or service_catalog_row(resolved_svc)
    service_free = (catalog_row or {}).get("free_tier") or SERVICE_FREE_TIER.get(resolved_svc) or {}

    if sku_tier:
        pricing_model: PricingModel = sku_tier.get("pricing_model", "pay_as_you_go")
        cost_type: CostType = sku_tier.get("cost_type") or cost_type_for_canonical(canonical) or "costed"
        free_tier = dict(sku_tier.get("free_tier") or {})
        sku_name = str(sku_tier.get("sku") or tokens[0] if tokens else "")
        source = "sku_tier"
    else:
        pricing_model = (
            (catalog_row or {}).get("pricing_model")
            or _DEFAULT_PRICING_MODEL.get(canonical, "pay_as_you_go")
        )
        if cost_type_for_canonical(canonical) == "free":
            pricing_model = "always_free"
        classification = classify_resource_type(
            canonical_type=canonical,
            service_name=resolved_svc,
            cost_mtd=cost_mtd,
        )
        cost_type = classification.cost_type
        free_tier = dict(service_free)
        sku_name = tokens[0] if tokens else ""
        source = "canonical_default"

    if not free_tier and service_free:
        free_tier = dict(service_free)

    return {
        "canonical_type": canonical,
        "sku": sku_label or sku_name or None,
        "sku_name": sku_name or None,
        "sku_tier": sku_tier.get("sku") if sku_tier else (sku_name or None),
        "pricing_model": pricing_model,
        "cost_type": cost_type,
        "service_name": resolved_svc or None,
        "free_tier": free_tier or None,
        "source": source,
    }


def upsert_resource_pricing_profile(
    db: Session,
    *,
    subscription_id: str,
    resource_id: str,
    resource_name: str,
    canonical_type: str,
    sku_label: str | None,
    sku_json: dict[str, Any] | None,
    cost_mtd: float = 0.0,
) -> ResourcePricingProfile:
    """Persist resolved pricing profile for a synced resource."""
    from app.focus_mapping import normalize_arm_id

    sub = subscription_id.strip().lower()
    rid = normalize_arm_id(resource_id)
    profile = resolve_resource_pricing_profile(
        canonical_type=canonical_type,
        sku_label=sku_label,
        sku_json=sku_json,
        cost_mtd=cost_mtd,
    )
    now = datetime.now(timezone.utc)
    free_tier_json = json.dumps(profile.get("free_tier") or {})
    profile_json = json.dumps(profile)

    existing = _find_pricing_profile(db, sub, rid)
    if existing:
        _apply_pricing_profile_fields(
            existing,
            resource_name=resource_name,
            canonical_type=canonical_type,
            profile=profile,
            free_tier_json=free_tier_json,
            profile_json=profile_json,
            synced_at=now,
        )
        return existing

    row = ResourcePricingProfile(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        resource_id=rid,
        resource_name=resource_name,
        canonical_type=canonical_type,
        sku=profile.get("sku"),
        sku_name=profile.get("sku_name"),
        sku_tier=profile.get("sku_tier"),
        pricing_model=profile.get("pricing_model"),
        cost_type=profile.get("cost_type"),
        service_name=profile.get("service_name"),
        free_tier_json=free_tier_json,
        profile_json=profile_json,
        synced_at=now,
    )
    db.add(row)
    return row


def list_pricing_profiles_db(
    db: Session,
    subscription_id: str,
    *,
    canonical_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Paginated pricing profiles for a subscription."""
    sub = subscription_id.strip().lower()
    limit = min(max(1, int(limit)), 500)
    offset = max(0, int(offset))

    q = db.query(ResourcePricingProfile).filter(ResourcePricingProfile.subscription_id == sub)
    if canonical_type:
        q = q.filter(ResourcePricingProfile.canonical_type == canonical_type.strip().lower())
    total = q.count()
    rows = q.order_by(ResourcePricingProfile.resource_name).offset(offset).limit(limit).all()

    items = []
    for row in rows:
        try:
            free_tier = json.loads(row.free_tier_json or "{}")
        except json.JSONDecodeError:
            free_tier = {}
        items.append({
            "resource_id": row.resource_id,
            "resource_name": row.resource_name,
            "canonical_type": row.canonical_type,
            "sku": row.sku,
            "sku_name": row.sku_name,
            "sku_tier": row.sku_tier,
            "pricing_model": row.pricing_model,
            "cost_type": row.cost_type,
            "service_name": row.service_name,
            "free_tier": free_tier or None,
            "synced_at": row.synced_at.isoformat() if row.synced_at else None,
        })

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
    }

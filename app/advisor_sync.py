"""Persist and query Azure Advisor recommendation snapshots."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.auth import arm_auth_context
from app.azure_advisor import AdvisorClient
from app.focus_mapping import normalize_arm_id
from app.advisor_vm_targets import (
    parse_advisor_recommendation_type_id,
    parse_advisor_vm_skus,
)
from app.models import AdvisorRecommendation
from app.utils import utc_now

log = structlog.get_logger()

_CATEGORY_LABELS = {
    "cost": "Cost",
    "performance": "Performance",
    "highavailability": "HighAvailability",
    "security": "Security",
    "operationalexcellence": "OperationalExcellence",
}

_ADVISOR_REC_MARKER = "/providers/microsoft.advisor/recommendations/"


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return utc_now()
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return utc_now()


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_savings(extended: dict[str, Any]) -> tuple[float | None, float | None]:
    if not extended:
        return None, None
    monthly = None
    yearly = None
    for key in ("savingsAmount", "potentialMonthlySavings", "monthlySavings"):
        monthly = _parse_float(extended.get(key))
        if monthly is not None:
            break
    for key in ("annualSavingsAmount", "savingsAmountYear", "potentialYearlySavings"):
        yearly = _parse_float(extended.get(key))
        if yearly is not None:
            break
    if monthly is None and yearly is not None:
        monthly = round(yearly / 12.0, 2)
    if yearly is None and monthly is not None:
        yearly = round(monthly * 12.0, 2)
    return monthly, yearly


def _resolve_resource_id(item: dict[str, Any], props: dict[str, Any]) -> str:
    """Resolve ARM resource ID from Advisor payload (multiple Azure shapes)."""
    resource_meta = props.get("resourceMetadata") or {}
    extended = props.get("extendedProperties") or {}
    candidates: list[str] = []

    for key in ("resourceId", "source"):
        val = resource_meta.get(key)
        if val:
            candidates.append(str(val))

    for key in ("resourceId", "recommendationResourceId", "armResourceId"):
        val = extended.get(key)
        if val:
            candidates.append(str(val))

    impacted = props.get("impactedValue") or ""
    if str(impacted).strip().lower().startswith("/subscriptions/"):
        candidates.append(str(impacted))

    for entry in props.get("impactedResources") or []:
        if isinstance(entry, dict):
            for key in ("resourceId", "id", "resourceUri"):
                val = entry.get(key)
                if val:
                    candidates.append(str(val))

    for key in ("resourceUri", "targetResourceId"):
        val = extended.get(key)
        if val:
            candidates.append(str(val))

    arm_id = str(item.get("id") or "")
    marker_idx = arm_id.lower().find(_ADVISOR_REC_MARKER)
    if marker_idx > 0:
        candidates.append(arm_id[:marker_idx])

    for raw in candidates:
        norm = normalize_arm_id(raw)
        if norm and "/providers/" in norm:
            return norm
    return ""


def _serialize_raw_json(raw_json: Any) -> str:
    if isinstance(raw_json, dict):
        return json.dumps(raw_json)
    if isinstance(raw_json, str) and raw_json.strip():
        return raw_json
    return "{}"


def normalize_advisor_item(item: dict[str, Any], subscription_id: str) -> dict[str, Any]:
    """Map an ARM Advisor recommendation resource to DB fields."""
    props = item.get("properties") or {}
    short = props.get("shortDescription") or {}
    extended = props.get("extendedProperties") or {}

    recommendation_id = (
        item.get("name")
        or props.get("recommendationTypeId")
        or props.get("label")
        or ""
    )
    resource_id = _resolve_resource_id(item, props)
    category = str(props.get("category") or "Unknown")
    impact = str(props.get("impact") or "Low")
    summary = str(short.get("problem") or short.get("solution") or recommendation_id or "Advisor recommendation")
    description = short.get("solution") or props.get("longDescription") or ""
    monthly, yearly = _parse_savings(extended)
    status = "Active"
    if props.get("exclusionMetadata"):
        status = "Dismissed"
    current_sku, target_sku = parse_advisor_vm_skus(extended, props=props)
    recommendation_type_id = parse_advisor_recommendation_type_id(item, props)

    return {
        "recommendation_id": str(recommendation_id),
        "resource_id": resource_id,
        "subscription_id": subscription_id.strip().lower(),
        "category": category,
        "impact": impact,
        "summary": summary[:500],
        "description": str(description) if description else None,
        "potential_savings_monthly": monthly,
        "potential_savings_yearly": yearly,
        "recommendation_type_id": recommendation_type_id,
        "current_sku": current_sku,
        "target_sku": target_sku,
        "status": status,
        "generated_at": _parse_dt(props.get("lastUpdated")),
        "raw_json": item,
    }


def upsert_advisor_recommendations(
    db: Session,
    subscription_id: str,
    items: list[dict[str, Any]],
) -> dict[str, int]:
    """Insert or update advisor recommendation rows."""
    sub = subscription_id.strip().lower()
    created = 0
    updated = 0
    skipped = 0
    errors = 0

    for item in items:
        try:
            row = normalize_advisor_item(item, sub)
            if not row["recommendation_id"]:
                skipped += 1
                continue

            existing = (
                db.query(AdvisorRecommendation)
                .filter(
                    AdvisorRecommendation.subscription_id == sub,
                    AdvisorRecommendation.recommendation_id == row["recommendation_id"],
                )
                .first()
            )
            raw_json = row.pop("raw_json")
            raw_payload = _serialize_raw_json(raw_json)
            if existing:
                if existing.app_override:
                    row["status"] = existing.status
                for key, value in row.items():
                    setattr(existing, key, value)
                existing.raw_json = raw_payload
                existing.synced_at = utc_now()
                updated += 1
            else:
                db.add(AdvisorRecommendation(
                    id=str(uuid.uuid4()),
                    raw_json=raw_payload,
                    synced_at=utc_now(),
                    app_override=False,
                    **row,
                ))
                created += 1
        except Exception as exc:
            errors += 1
            log.warning(
                "advisor_upsert_row_failed",
                recommendation_id=(item.get("name") or "")[:80],
                error=str(exc)[:200],
            )

    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}


def sync_azure_advisor_recommendations(
    subscription_id: str,
    db: Session,
    token: str,
    *,
    trigger_generate: bool = False,
    wait_for_generate: bool = False,
) -> dict[str, Any]:
    """Fetch Advisor recommendations from Azure and persist snapshots."""
    sub = subscription_id.strip().lower()
    generate_result = None

    with arm_auth_context(db=db, token=token):
        client = AdvisorClient(headers={"Authorization": f"Bearer {token}"})
        if trigger_generate:
            if wait_for_generate:
                generate_result = client.generate_and_wait(sub)
            else:
                generate_result = client.generate_recommendations(sub)
        items = client.list_recommendations(sub, use_cache=False)

    counts = upsert_advisor_recommendations(db, sub, items)
    total_monthly = round(
        sum(
            r.potential_savings_monthly or 0.0
            for r in db.query(AdvisorRecommendation).filter(
                AdvisorRecommendation.subscription_id == sub,
                AdvisorRecommendation.status == "Active",
            ).all()
        ),
        2,
    )
    result = {
        "status": "ok",
        "subscription_id": sub,
        "fetched": len(items),
        "stored": counts["created"] + counts["updated"],
        **counts,
        "total_estimated_monthly_savings": total_monthly,
        "source": "azure_advisor",
    }
    if counts.get("errors"):
        result["status"] = "partial"
    if generate_result:
        result["generate"] = generate_result
    log.info("advisor_sync.done", **{k: result[k] for k in ("subscription_id", "fetched", "stored")})
    return result


def list_stored_advisor_recommendations(
    db: Session,
    subscription_id: str,
    *,
    category: str | None = None,
    impact: str | None = None,
    status: str | None = "Active",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return paginated advisor snapshots from the database."""
    sub = subscription_id.strip().lower()
    q = db.query(AdvisorRecommendation).filter(
        AdvisorRecommendation.subscription_id == sub,
    )
    if category:
        cat = _CATEGORY_LABELS.get(category.strip().lower(), category)
        q = q.filter(AdvisorRecommendation.category == cat)
    if impact:
        q = q.filter(AdvisorRecommendation.impact == impact)
    if status:
        q = q.filter(AdvisorRecommendation.status == status)

    from app.inventory_standalone import is_embedded_only_arm_id

    rows = (
        q.order_by(
            AdvisorRecommendation.potential_savings_monthly.desc(),
            AdvisorRecommendation.generated_at.desc(),
        )
        .all()
    )
    rows = [row for row in rows if not is_embedded_only_arm_id(row.resource_id)]
    total = len(rows)
    page_rows = rows[max(0, offset): max(0, offset) + max(1, min(limit, 500))]

    return {
        "subscription_id": sub,
        "count": len(page_rows),
        "total": total,
        "offset": offset,
        "limit": limit,
        "total_estimated_monthly_savings": round(
            sum(r.potential_savings_monthly or 0.0 for r in page_rows), 2,
        ),
        "items": [_serialize_advisor_row(r) for r in page_rows],
        "source": "azure_advisor",
    }


def _serialize_advisor_row(row: AdvisorRecommendation) -> dict[str, Any]:
    return {
        "id": row.id,
        "recommendation_id": row.recommendation_id,
        "resource_id": row.resource_id,
        "subscription_id": row.subscription_id,
        "category": row.category,
        "impact": row.impact,
        "summary": row.summary,
        "description": row.description,
        "potential_savings_monthly": row.potential_savings_monthly,
        "potential_savings_yearly": row.potential_savings_yearly,
        "recommendation_type_id": row.recommendation_type_id,
        "current_sku": row.current_sku,
        "target_sku": row.target_sku,
        "status": row.status,
        "app_override": bool(row.app_override),
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "synced_at": row.synced_at.isoformat() if row.synced_at else None,
    }

"""Azure Advisor VM resize targets — parse, store, and align engine recommendations."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.focus_mapping import normalize_arm_id
from app.models import AdvisorRecommendation

# Azure Advisor: right-size or shutdown underutilized VMs
VM_RIGHTSIZE_RECOMMENDATION_TYPE = "39a8510b-812c-4530-ab2a-c8491f9bf666"

_SHUTDOWN_TARGETS = frozenset({"shutdown", "deallocate", "stop", "none", ""})

_SKU_KEY_PAIRS = (
    ("currentSku", "targetSku"),
    ("CurrentSku", "TargetSku"),
    ("currentSize", "targetSize"),
    ("currentVMSize", "targetVMSize"),
    ("sku", "recommendedSku"),
)

_VM_RESOURCE_MARKER = "/microsoft.compute/virtualmachines/"


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_vm_sku_name(sku: str | None) -> str | None:
    if not sku:
        return None
    text = str(sku).strip()
    if not text or text.lower() in _SHUTDOWN_TARGETS:
        return None
    if text.lower().startswith("standard_") or text.lower().startswith("basic_"):
        return text
    if re.match(r"^[A-Za-z]\d", text):
        return f"Standard_{text}"
    return text


def parse_advisor_vm_skus(
    extended: dict[str, Any] | None,
    *,
    props: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    """Extract current and target VM SKU from Advisor extended properties."""
    extended = extended or {}
    props = props or {}
    current: str | None = None
    target: str | None = None

    for cur_key, tgt_key in _SKU_KEY_PAIRS:
        if not current:
            current = _normalize_vm_sku_name(extended.get(cur_key))
        if not target:
            target = _normalize_vm_sku_name(extended.get(tgt_key))

    if not current:
        current = _normalize_vm_sku_name(props.get("impactedFieldValue") or props.get("impactedValue"))
    return current, target


def parse_advisor_recommendation_type_id(
    item: dict[str, Any],
    props: dict[str, Any] | None = None,
) -> str | None:
    props = props or item.get("properties") or {}
    for key in ("recommendationTypeId", "recommendationType"):
        val = props.get(key) or item.get(key)
        if val:
            return str(val).strip().lower()
    return None


def is_vm_resize_advisor_row(
    *,
    resource_id: str,
    category: str,
    recommendation_type_id: str | None,
    target_sku: str | None,
) -> bool:
    rid = (resource_id or "").lower()
    if _VM_RESOURCE_MARKER not in rid:
        return False
    if (category or "").lower() != "cost":
        return False
    if recommendation_type_id == VM_RIGHTSIZE_RECOMMENDATION_TYPE.lower():
        return bool(target_sku)
    return bool(target_sku)


@dataclass(frozen=True)
class AdvisorVmTarget:
    resource_id: str
    recommendation_id: str
    current_sku: str | None
    target_sku: str
    recommendation_type_id: str | None
    potential_savings_monthly: float | None
    summary: str | None


def advisor_row_to_vm_target(row: AdvisorRecommendation) -> AdvisorVmTarget | None:
    """Build a VM target from a stored advisor row (columns or raw_json fallback)."""
    current = _normalize_vm_sku_name(getattr(row, "current_sku", None))
    target = _normalize_vm_sku_name(getattr(row, "target_sku", None))
    rec_type = getattr(row, "recommendation_type_id", None)

    if not target:
        raw = row.raw_json
        if isinstance(raw, str) and raw.strip():
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        if isinstance(raw, dict):
            props = raw.get("properties") or {}
            extended = props.get("extendedProperties") or {}
            parsed_current, parsed_target = parse_advisor_vm_skus(extended, props=props)
            current = current or parsed_current
            target = parsed_target
            rec_type = rec_type or parse_advisor_recommendation_type_id(raw, props)

    if not target:
        return None
    if not is_vm_resize_advisor_row(
        resource_id=row.resource_id,
        category=row.category,
        recommendation_type_id=rec_type,
        target_sku=target,
    ):
        return None

    return AdvisorVmTarget(
        resource_id=normalize_arm_id(row.resource_id),
        recommendation_id=row.recommendation_id,
        current_sku=current,
        target_sku=target,
        recommendation_type_id=rec_type,
        potential_savings_monthly=row.potential_savings_monthly,
        summary=row.summary,
    )


def load_advisor_vm_targets(db: Session, subscription_id: str) -> dict[str, AdvisorVmTarget]:
    """Return normalized resource id → Advisor VM resize target for active cost recs."""
    sub = subscription_id.strip().lower()
    rows = (
        db.query(AdvisorRecommendation)
        .filter(
            AdvisorRecommendation.subscription_id == sub,
            AdvisorRecommendation.status == "Active",
            AdvisorRecommendation.category == "Cost",
        )
        .all()
    )
    out: dict[str, AdvisorVmTarget] = {}
    for row in rows:
        target = advisor_row_to_vm_target(row)
        if not target:
            continue
        rid = normalize_arm_id(target.resource_id).lower()
        existing = out.get(rid)
        if existing is None:
            out[rid] = target
            continue
        existing_savings = existing.potential_savings_monthly or 0.0
        new_savings = target.potential_savings_monthly or 0.0
        if new_savings > existing_savings:
            out[rid] = target
    return out

"""Build normalized DB resource records for assessment evaluation."""

from __future__ import annotations

import json
from typing import Any

from app.assessment.signals import compute_signals, nest_flat_metrics_for_assessment
from app.focus_mapping import normalize_arm_id
from app.resource_type_map import arm_provider_type


def _parse_json(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


def resource_row_to_dict(row: Any) -> dict[str, Any]:
    """Convert ResourceSnapshot ORM row to a plain dict."""
    props = _parse_json(getattr(row, "properties_json", None), {})
    tags = _parse_json(getattr(row, "tags_json", None), {})
    sku_json = _parse_json(getattr(row, "sku_json", None), {})
    sku_name = getattr(row, "sku", None) or sku_json.get("name") or ""
    rid = normalize_arm_id(getattr(row, "resource_id", "") or "")
    arm_type = arm_provider_type(rid) or ""

    return {
        "id": getattr(row, "id", None),
        "subscription_id": (getattr(row, "subscription_id", "") or "").lower(),
        "resource_id": rid,
        "resource_name": getattr(row, "resource_name", "") or "",
        "resource_type": arm_type or getattr(row, "resource_type", "") or "",
        "canonical_type": getattr(row, "resource_type", "") or "",
        "resource_group": getattr(row, "resource_group", "") or "",
        "location": getattr(row, "location", "") or "",
        "sku": sku_name,
        "state": getattr(row, "state", "") or "",
        "properties": props,
        "tags": tags,
        "monthly_cost_usd": float(getattr(row, "monthly_cost_usd", 0) or 0),
        "monthly_cost_billing": float(getattr(row, "monthly_cost_billing", 0) or 0),
        "billing_currency": getattr(row, "billing_currency", None) or "USD",
        "synced_at": getattr(row, "synced_at", None),
    }


def build_cost_block(row_dict: dict[str, Any]) -> dict[str, Any]:
    billing = row_dict.get("monthly_cost_billing")
    usd = row_dict.get("monthly_cost_usd")
    return {
        "monthlyActualCost": usd or billing,
        "monthly_cost_billing": billing,
        "monthly_cost_usd": usd,
        "monthlyCostBilling": billing,
        "monthlyCostUsd": usd,
        "billingCurrency": row_dict.get("billing_currency"),
        "billing_currency": row_dict.get("billing_currency"),
    }


def build_resource_block(row_dict: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row_dict.get("resource_id"),
        "name": row_dict.get("resource_name"),
        "type": row_dict.get("resource_type"),
        "canonical_type": row_dict.get("canonical_type"),
        "resource_group": row_dict.get("resource_group"),
        "location": row_dict.get("location"),
        "sku": row_dict.get("sku"),
        "state": row_dict.get("state"),
        "subscription_id": row_dict.get("subscription_id"),
    }


def build_normalized_record(
    row_dict: dict[str, Any],
    *,
    metrics: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    required_metric_keys: list[str] | None = None,
    assessment: dict[str, Any] | None = None,
    metrics_payload: dict[str, Any] | None = None,
    monitor_raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the normalized record shape expected by assessment JSON."""
    properties = dict(row_dict.get("properties") or {})
    if row_dict.get("sku") and "sku" not in properties:
        properties["sku"] = row_dict["sku"]

    cost = build_cost_block(row_dict)
    resource = build_resource_block(row_dict)
    tags = dict(row_dict.get("tags") or {})
    policy_block = dict(policy or {})

    record: dict[str, Any] = {
        "resource_id": row_dict.get("resource_id"),
        "resource_type": row_dict.get("resource_type"),
        "resource": resource,
        "properties": properties,
        "metrics": nest_flat_metrics_for_assessment(
            metrics,
            assessment=assessment,
            canonical_type=row_dict.get("canonical_type"),
            metrics_payload=metrics_payload,
            monitor_raw=monitor_raw,
        ),
        "cost": cost,
        "tags": tags,
        "policy": policy_block,
        "signals": {},
        "resource_name": row_dict.get("resource_name"),
        "resource_group": row_dict.get("resource_group"),
        "location": row_dict.get("location"),
    }
    record["signals"] = compute_signals(
        record,
        required_metric_keys=required_metric_keys,
        assessment=assessment,
    )
    return record


def merge_snapshot_json(
    existing: dict[str, Any] | None,
    record: dict[str, Any],
) -> dict[str, Any]:
    """Merge normalized record into persisted snapshot_json."""
    base = dict(existing or {})
    for key in (
        "resource",
        "properties",
        "metrics",
        "cost",
        "tags",
        "policy",
        "signals",
        "assessment",
        "sku_specs",
        "sku_summary",
        "metrics_payload",
        "metrics_timespan",
        "recommendations",
    ):
        if key in record:
            base[key] = record[key]
    base["resource_id"] = record.get("resource_id")
    base["resource_type"] = record.get("resource_type")
    return base

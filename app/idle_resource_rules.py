"""Shared helpers for idle / waste resource findings used by the waste heatmap."""

from __future__ import annotations

import json
from typing import Any

from app.focus_mapping import normalize_arm_id
from app.rule_behavior import is_waste_heatmap_rule

OPEN_IDLE_STATUSES = frozenset({"open", "acknowledged"})

_HEATMAP_CATEGORY_LABELS = {
    "COMPUTE": "Compute",
    "KUBERNETES": "Kubernetes",
    "STORAGE": "Storage",
    "NETWORK": "Network",
    "DATABASE": "Database",
    "SECURITY": "Security",
    "COST": "Cost",
    "GOVERNANCE": "Governance",
    "RELIABILITY": "Reliability",
}

def is_idle_or_waste_rule(rule_id: str | None) -> bool:
    """True when a finding rule represents idle, orphaned, or stale waste."""
    return is_waste_heatmap_rule(rule_id)


def normalize_severity(severity: str | None) -> str:
    sev = (severity or "medium").strip().lower()
    return sev if sev in {"critical", "high", "medium", "low", "info"} else "low"


def heatmap_category(*, category: str | None = None, resource_type: str | None = None) -> str:
    """Map a finding to a display category for the waste heatmap."""
    cat = (category or "").strip().upper()
    if cat in _HEATMAP_CATEGORY_LABELS:
        return _HEATMAP_CATEGORY_LABELS[cat]

    rt = (resource_type or "").lower()
    if any(token in rt for token in ("virtualmachine", "compute/vm", "vmss", "appservice", "sites", "plan")):
        return "Compute"
    if any(token in rt for token in ("disk", "snapshot", "storage/")):
        return "Storage"
    if any(token in rt for token in ("network", "publicip", "nic", "vnet", "loadbal", "gateway", "nat")):
        return "Network"
    if any(token in rt for token in ("kubernetes", "managedcluster", "containers/")):
        return "Kubernetes"
    if any(token in rt for token in ("sql", "postgres", "cosmos", "redis", "database")):
        return "Database"
    if any(token in rt for token in ("keyvault", "security")):
        return "Security"
    return "Other"


def parse_finding_evidence(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def resolve_finding_savings_usd(
    finding: Any,
    *,
    resource_cost_usd: float | None = None,
) -> tuple[float, str]:
    """Resolve monthly savings for idle/waste findings.

    Priority: stored estimated_savings_usd → annualized/12 → evidence savings fields →
    evidence monthly_cost_usd (delete/orphan waste) → synced resource MTD cost.
    """
    stored = float(getattr(finding, "estimated_savings_usd", None) or 0)
    if stored > 0:
        return round(stored, 2), "stored"

    annualized = float(getattr(finding, "annualized_savings_usd", None) or 0)
    if annualized > 0:
        return round(annualized / 12, 2), "stored"

    evidence = parse_finding_evidence(getattr(finding, "evidence_json", None))
    for key in (
        "estimated_monthly_savings_usd",
        "retail_monthly_savings_usd",
        "monthly_savings_usd",
        "savings_usd",
    ):
        val = evidence.get(key)
        if val is not None:
            amount = float(val)
            if amount > 0:
                return round(amount, 2), "evidence"

    methodology = evidence.get("savings_methodology")
    if isinstance(methodology, dict):
        val = methodology.get("estimated_monthly_savings_usd")
        if val is not None:
            amount = float(val)
            if amount > 0:
                return round(amount, 2), "evidence"

    for key in ("monthly_cost_usd", "monthly_cost"):
        monthly = evidence.get(key)
        if monthly is not None:
            amount = float(monthly)
            if amount > 0:
                return round(amount, 2), "evidence_cost"

    if resource_cost_usd is not None:
        amount = float(resource_cost_usd)
        if amount > 0:
            return round(amount, 2), "resource_cost"

    return 0.0, "none"


def load_resource_costs_usd(
    db: Any,
    subscription_id: str,
    resource_ids: set[str],
) -> dict[str, float]:
    """MTD cost keyed by normalized ARM resource id for savings fallback."""
    if not db or not resource_ids:
        return {}
    from app.cost_db import resource_cost_map_from_db
    from app.cost_utils import resource_cost_billing_from_map, resource_cost_usd_from_map
    from app.models import ResourceSnapshot

    sub = (subscription_id or "").strip().lower()
    out: dict[str, float] = {}

    from app.cost_db import _latest_cost_by_resource_month

    cost_details = resource_cost_map_from_db(db, subscription_id)
    if not cost_details:
        latest_month = _latest_cost_by_resource_month(db, subscription_id)
        if latest_month:
            cost_details = resource_cost_map_from_db(db, subscription_id, month=latest_month)
    for rid in resource_ids:
        usd = resource_cost_usd_from_map(cost_details, rid)
        if usd is not None and usd > 0:
            out[rid] = round(usd, 2)
            continue
        billing = resource_cost_billing_from_map(cost_details, rid)
        if billing is not None and billing > 0:
            out[rid] = round(billing, 2)

    missing = resource_ids - set(out)
    if missing:
        rows = (
            db.query(ResourceSnapshot.resource_id, ResourceSnapshot.monthly_cost_usd)
            .filter(
                ResourceSnapshot.subscription_id == sub,
                ResourceSnapshot.is_active.is_(True),
            )
            .all()
        )
        for rid, monthly_usd in rows:
            key = normalize_arm_id(rid)
            if key not in missing:
                continue
            amount = float(monthly_usd or 0)
            if amount > 0:
                out[key] = round(amount, 2)
    return out

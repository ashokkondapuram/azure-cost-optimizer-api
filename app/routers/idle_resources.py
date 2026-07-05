"""Unified idle resource sweep — aggregate idle/stale resources across all resource types."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ResourceSnapshot, Finding

router = APIRouter(prefix="/idle-resources", tags=["Idle Resources"])

# Rule IDs that indicate idle / orphaned / stale resources
_IDLE_RULE_IDS = frozenset({
    "UNATTACHED_DISK",
    "ORPHANED_DISK",
    "DISK_UNUSED",
    "VM_STOPPED_DEALLOCATED",
    "VM_IDLE",
    "VM_LOW_CPU",
    "UNUSED_PUBLIC_IP",
    "ORPHANED_NIC",
    "EMPTY_RESOURCE_GROUP",
    "STALE_SNAPSHOT",
    "UNUSED_LOAD_BALANCER",
    "UNUSED_APP_GATEWAY",
    "IDLE_APP_SERVICE_PLAN",
    "UNUSED_VNET_GATEWAY",
    "EMPTY_AKS_NODE_POOL",
    "UNUSED_RESERVATION",
    "ACR_NO_PULL",
    "SQL_IDLE_DB",
    "COSMOS_LOW_RU",
})

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _normalize(sub: str) -> str:
    return (sub or "").strip().lower()


def _resource_type_category(resource_type: str) -> str:
    rt = (resource_type or "").lower()
    if "microsoft.compute/virtualmachines" in rt:
        return "Virtual Machine"
    if "microsoft.compute/disks" in rt:
        return "Disk"
    if "microsoft.network" in rt:
        return "Network"
    if "microsoft.containerservice" in rt:
        return "Kubernetes"
    if "microsoft.sql" in rt or "microsoft.documentdb" in rt:
        return "Database"
    if "microsoft.storage" in rt:
        return "Storage"
    if "microsoft.web" in rt:
        return "App Service"
    if "microsoft.containerregistry" in rt:
        return "Container Registry"
    return "Other"


@router.get("/sweep/{subscription_id}")
def idle_resource_sweep(
    subscription_id: str,
    severity: str | None = Query(None, description="Filter by severity: critical, high, medium, low"),
    category: str | None = Query(None, description="Filter by resource category"),
    include_resolved: bool = Query(False, description="Include resolved findings"),
    db: Session = Depends(get_db),
) -> dict:
    """Sweep all resource types for idle / orphaned / stale resources using stored findings."""
    sub = _normalize(subscription_id)

    query = (
        db.query(Finding)
        .filter(
            Finding.subscription_id == sub,
            Finding.rule_id.in_(list(_IDLE_RULE_IDS)),
        )
    )
    if not include_resolved:
        query = query.filter(Finding.status.in_(["open", "active", None, ""]))
    if severity:
        query = query.filter(Finding.severity == severity.lower())

    findings = query.order_by(Finding.severity).all()

    items: list[dict] = []
    category_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    total_savings_usd = 0.0

    for f in findings:
        rt = getattr(f, "resource_type", None) or ""
        cat = _resource_type_category(rt)
        if category and cat.lower() != category.lower():
            continue
        category_counts[cat] = category_counts.get(cat, 0) + 1
        sev = (f.severity or "medium").lower()
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        savings = float(getattr(f, "estimated_savings_usd") or 0)
        total_savings_usd += savings
        items.append({
            "finding_id": f.id,
            "rule_id": f.rule_id,
            "resource_id": f.resource_id,
            "resource_name": getattr(f, "resource_name", None),
            "resource_type": rt,
            "category": cat,
            "title": f.title,
            "detail": f.detail,
            "severity": f.severity,
            "status": f.status,
            "estimated_savings_usd": round(savings, 2),
        })

    items.sort(key=lambda x: (_SEVERITY_ORDER.get(x["severity"] or "medium", 4), -x["estimated_savings_usd"]))

    return {
        "subscription_id": subscription_id,
        "total_idle_findings": len(items),
        "total_estimated_savings_usd": round(total_savings_usd, 2),
        "by_severity": severity_counts,
        "by_category": category_counts,
        "idle_resources": items[:200],
        "source": "database",
    }


@router.get("/summary/{subscription_id}")
def idle_resource_summary(
    subscription_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """High-level summary of idle resources — counts and total potential savings."""
    sub = _normalize(subscription_id)

    findings = (
        db.query(Finding)
        .filter(
            Finding.subscription_id == sub,
            Finding.rule_id.in_(list(_IDLE_RULE_IDS)),
            Finding.status.in_(["open", "active", None, ""]),
        )
        .all()
    )

    total_savings = sum(float(getattr(f, "estimated_savings_usd") or 0) for f in findings)
    by_rule: dict[str, dict] = {}
    for f in findings:
        key = f.rule_id or "UNKNOWN"
        entry = by_rule.setdefault(key, {"rule_id": key, "count": 0, "savings_usd": 0.0, "title": f.title})
        entry["count"] += 1
        entry["savings_usd"] = round(entry["savings_usd"] + float(getattr(f, "estimated_savings_usd") or 0), 2)

    rule_summary = sorted(by_rule.values(), key=lambda x: -x["savings_usd"])
    return {
        "subscription_id": subscription_id,
        "total_idle_findings": len(findings),
        "total_estimated_savings_usd": round(total_savings, 2),
        "top_rules": rule_summary[:20],
        "source": "database",
    }

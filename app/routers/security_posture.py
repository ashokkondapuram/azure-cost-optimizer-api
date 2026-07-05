"""Unified security posture score derived from existing security findings."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Finding

router = APIRouter(prefix="/security-posture", tags=["Security Posture"])

# Rule IDs that map to security category
_SECURITY_RULE_PREFIXES = (
    "SEC_",
    "NETWORK_",
    "STORAGE_PUBLIC",
    "KEY_VAULT",
    "MANAGED_IDENTITY",
    "TLS_",
    "HTTPS_",
    "ENCRYPTION_",
    "FIREWALL_",
    "RBAC_",
)

_SEVERITY_WEIGHTS = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
_MAX_SCORE = 100


def _is_security_finding(rule_id: str, category: str | None) -> bool:
    if category and "security" in (category or "").lower():
        return True
    return any((rule_id or "").upper().startswith(p) for p in _SECURITY_RULE_PREFIXES)


def _severity_bucket(severity: str | None) -> str:
    s = (severity or "").lower()
    if s in _SEVERITY_WEIGHTS:
        return s
    return "medium"


def _compute_score(findings: list[Any]) -> float:
    """Weighted security score 0–100. More open high/critical findings = lower score."""
    if not findings:
        return 100.0
    open_findings = [f for f in findings if (f.status or "").lower() in ("open", "active", "")]
    if not open_findings:
        return 100.0
    total_weight = sum(_SEVERITY_WEIGHTS.get(_severity_bucket(f.severity), 2) for f in open_findings)
    penalty_per_weight = 2.0  # each weight unit deducts 2 points, capped at 0
    score = max(0.0, _MAX_SCORE - (total_weight * penalty_per_weight))
    return round(score, 1)


@router.get("/{subscription_id}")
def get_security_posture(
    subscription_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Return a unified security posture score and breakdown of open security findings."""
    sub = (subscription_id or "").strip().lower()

    all_findings = (
        db.query(Finding)
        .filter(Finding.subscription_id == sub)
        .all()
    )
    if not all_findings:
        return {
            "subscription_id": subscription_id,
            "score": None,
            "message": "No findings data. Run an analysis sync first.",
            "source": "database",
        }

    sec_findings = [
        f for f in all_findings
        if _is_security_finding(f.rule_id or "", getattr(f, "category", None))
    ]

    score = _compute_score(sec_findings)

    by_severity: dict[str, int] = {s: 0 for s in _SEVERITY_WEIGHTS}
    for f in sec_findings:
        by_severity[_severity_bucket(f.severity)] = by_severity.get(_severity_bucket(f.severity), 0) + 1

    open_critical = [
        {
            "finding_id": f.id,
            "rule_id": f.rule_id,
            "resource_id": f.resource_id,
            "title": f.title,
            "severity": f.severity,
            "status": f.status,
        }
        for f in sec_findings
        if _severity_bucket(f.severity) in ("critical", "high")
        and (f.status or "").lower() in ("open", "active", "")
    ][:25]

    rating = "A" if score >= 90 else ("B" if score >= 75 else ("C" if score >= 60 else ("D" if score >= 40 else "F")))
    return {
        "subscription_id": subscription_id,
        "score": score,
        "rating": rating,
        "total_security_findings": len(sec_findings),
        "open_by_severity": by_severity,
        "top_critical_findings": open_critical,
        "source": "database",
    }


@router.get("/trend/{subscription_id}")
def security_posture_trend(
    subscription_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Return open security finding counts grouped by severity for trend analysis."""
    sub = (subscription_id or "").strip().lower()

    findings = (
        db.query(Finding)
        .filter(Finding.subscription_id == sub)
        .all()
    )

    sec = [f for f in findings if _is_security_finding(f.rule_id or "", getattr(f, "category", None))]
    by_status: dict[str, int] = {}
    for f in sec:
        s = (f.status or "open").lower()
        by_status[s] = by_status.get(s, 0) + 1

    return {
        "subscription_id": subscription_id,
        "total_security_findings": len(sec),
        "by_status": by_status,
        "source": "database",
    }

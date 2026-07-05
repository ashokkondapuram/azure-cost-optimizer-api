"""Closed-loop recommendation execution tracking (3-D)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import OptimizationFinding, RecommendationExecution


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def log_execution(
    db: Session,
    *,
    finding_id: str,
    executed_by: str,
    action_type: str,
    before_state: dict | None = None,
) -> RecommendationExecution:
    row = RecommendationExecution(
        id=str(uuid.uuid4()),
        finding_id=finding_id,
        executed_by=executed_by,
        executed_at=_utc_now(),
        before_state=json.dumps(before_state or {}),
        action_type=action_type,
        validation_status="pending",
    )
    db.add(row)
    return row


def validate_execution(
    db: Session,
    execution: RecommendationExecution,
    *,
    after_state: dict | None = None,
    regressed: bool = False,
) -> RecommendationExecution:
    execution.validated_at = _utc_now()
    execution.validation_status = "regressed" if regressed else "confirmed"
    if after_state is not None:
        execution.after_state = json.dumps(after_state)
    return execution


def recent_executions_for_resource(
    db: Session,
    resource_id: str,
    *,
    days: int = 14,
) -> list[RecommendationExecution]:
    """Find executions linked to findings on a resource within the lookback window."""
    rid = (resource_id or "").lower()
    cutoff = _utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    cutoff = cutoff - timedelta(days=days)
    return (
        db.query(RecommendationExecution)
        .join(OptimizationFinding, OptimizationFinding.id == RecommendationExecution.finding_id)
        .filter(
            OptimizationFinding.resource_id == rid,
            RecommendationExecution.executed_at >= cutoff,
        )
        .order_by(RecommendationExecution.executed_at.desc())
        .all()
    )


def implemented_findings_for_subscription(
    db: Session,
    subscription_id: str,
) -> list[OptimizationFinding]:
    """Findings with a logged execution (Mark applied / closed-loop), not auto-resolved duplicates."""
    sub = (subscription_id or "").strip().lower()
    if not sub:
        return []
    rows = (
        db.query(OptimizationFinding)
        .join(RecommendationExecution, RecommendationExecution.finding_id == OptimizationFinding.id)
        .filter(func.lower(OptimizationFinding.subscription_id) == sub)
        .order_by(OptimizationFinding.detected_at.desc())
        .all()
    )
    seen: set[str] = set()
    unique: list[OptimizationFinding] = []
    for row in rows:
        if row.id in seen:
            continue
        seen.add(row.id)
        unique.append(row)
    return unique


def serialize_execution(row: RecommendationExecution) -> dict:
    def _parse(raw):
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}

    return {
        "id": row.id,
        "finding_id": row.finding_id,
        "executed_by": row.executed_by,
        "executed_at": row.executed_at.isoformat() if row.executed_at else None,
        "action_type": row.action_type,
        "before_state": _parse(row.before_state),
        "after_state": _parse(row.after_state),
        "validation_status": row.validation_status,
        "validated_at": row.validated_at.isoformat() if row.validated_at else None,
    }


def escalate_persisted_findings_after_execution(
    db: Session,
    findings: list[dict],
    *,
    days: int = 14,
) -> list[dict]:
    """
    Closed-loop validation: if a finding reappears after a confirmed execution,
    escalate severity and annotate evidence.
    """
    if not findings:
        return findings

    severity_rank = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    out: list[dict] = []

    for finding in findings:
        rid = (finding.get("resource_id") or "").lower()
        rule_id = (finding.get("rule_id") or "").upper()
        if not rid or not rule_id:
            out.append(finding)
            continue

        executions = recent_executions_for_resource(db, rid, days=days)
        matched = [
            ex for ex in executions
            if ex.validation_status == "confirmed"
            and _execution_rule_id(db, ex) == rule_id
        ]
        if not matched:
            out.append(finding)
            continue

        updated = dict(finding)
        current = str(updated.get("severity") or "MEDIUM").upper()
        rank = severity_rank.get(current, 2)
        if rank < severity_rank["HIGH"]:
            updated["severity"] = "HIGH"
        evidence = dict(updated.get("evidence") or {})
        evidence["closed_loop_escalation"] = True
        evidence["prior_execution_id"] = matched[0].id
        evidence["closed_loop_note"] = (
            "This recommendation was applied recently but the condition persists — investigate."
        )
        updated["evidence"] = evidence
        detail = updated.get("detail") or ""
        if "persists" not in detail.lower():
            updated["detail"] = f"{detail} Applied previously but unchanged — investigate.".strip()
        out.append(updated)

    return out


def _execution_rule_id(db: Session, execution: RecommendationExecution) -> str:
    row = db.query(OptimizationFinding).filter(OptimizationFinding.id == execution.finding_id).first()
    return (row.rule_id or "").upper() if row else ""

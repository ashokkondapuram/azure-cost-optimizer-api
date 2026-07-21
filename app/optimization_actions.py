"""CRUD and workflow for optimization_actions."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.inventory_standalone import STANDALONE_INVENTORY_EXCLUDED
from app.models import OptimizationAction, ResourceSnapshot
from app.optimization_savings import distinct_action_savings
from app.utils import norm_arm_id, utc_now

VALID_WORKFLOW_STATUSES = frozenset({"proposed", "approved", "executed", "rejected", "deferred"})


def _resource_group_from_arm_id(resource_id: str | None) -> str | None:
    rid = (resource_id or "").strip().lower()
    match = re.search(r"/resourcegroups/([^/]+)", rid)
    if not match:
        return None
    return unquote(match.group(1))


def _inventory_action_join(subscription_id: str):
    from app.inventory_standalone import standalone_inventory_snapshot_filter

    sub = subscription_id.strip().lower()
    return and_(
        func.lower(OptimizationAction.resource_id) == func.lower(ResourceSnapshot.resource_id),
        ResourceSnapshot.subscription_id == sub,
        ResourceSnapshot.is_active.is_(True),
        ResourceSnapshot.is_cost_export_only.is_(False),
        standalone_inventory_snapshot_filter(),
    )


def _exclude_embedded_only_actions(q):
    excluded = sorted(STANDALONE_INVENTORY_EXCLUDED)
    if excluded:
        q = q.filter(
            or_(
                OptimizationAction.resource_type.is_(None),
                OptimizationAction.resource_type == "",
                OptimizationAction.resource_type.notin_(excluded),
            ),
        )
    return q.filter(~OptimizationAction.resource_id.ilike("%/virtualmachinescalesets/%"))


def _action_summary(db: Session, subscription_id: str, *, inventory_only: bool = False) -> dict[str, int]:
    sub = subscription_id.strip().lower()
    summary = {status: 0 for status in VALID_WORKFLOW_STATUSES}
    q = _exclude_embedded_only_actions(
        db.query(OptimizationAction.workflow_status, func.count(OptimizationAction.id))
        .filter(OptimizationAction.subscription_id == sub),
    )
    if inventory_only:
        q = q.join(ResourceSnapshot, _inventory_action_join(sub))
    rows = q.group_by(OptimizationAction.workflow_status).all()
    for status, count in rows:
        key = (status or "proposed").lower()
        if key in summary:
            summary[key] = int(count or 0)
    return summary


def _parse_json(value: Any, default: Any):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def evidence_summary_from_row(row: OptimizationAction) -> dict[str, Any]:
    """Derive compact signal counts for list/table UI from persisted action evidence."""
    cost = _parse_json(row.cost_evidence, {})
    util = _parse_json(row.utilization_evidence, {})
    combined = cost.get("combined_evidence") or {}
    om = util.get("optimization_metrics") or {}
    rules = _parse_json(row.decision_rules_applied, [])

    cost_metrics = len(om.get("cost") or [])
    perf_metrics = len(om.get("performance") or [])
    metrics_count = combined.get("metrics_count")
    if metrics_count is None:
        metrics_count = cost_metrics + perf_metrics

    findings_count = combined.get("findings_count")
    if findings_count is None:
        findings_count = cost.get("signal_count") or len(util.get("triggering_rules") or [])

    advisor_count = combined.get("advisor_count", 0)
    has_advisor = combined.get("has_advisor")
    if has_advisor is None:
        has_advisor = advisor_count > 0 or "signal:cost" in rules or "signal:performance" in rules

    has_findings = combined.get("has_findings")
    if has_findings is None:
        has_findings = findings_count > 0

    has_metrics = combined.get("has_metrics")
    if has_metrics is None:
        has_metrics = metrics_count > 0

    return {
        "advisor_count": int(advisor_count or 0),
        "findings_count": int(findings_count or 0),
        "metrics_count": int(metrics_count or 0),
        "has_advisor": bool(has_advisor),
        "has_findings": bool(has_findings),
        "has_metrics": bool(has_metrics),
        "data_quality": om.get("data_quality") or combined.get("data_quality"),
        "sources_merged": combined.get("sources_merged", True),
    }


def serialize_action(row: OptimizationAction) -> dict[str, Any]:
    return {
        "id": row.id,
        "resource_id": row.resource_id,
        "subscription_id": row.subscription_id,
        "resource_type": row.resource_type,
        "resource_name": row.resource_name,
        "resource_group": _resource_group_from_arm_id(row.resource_id),
        "action_type": row.action_type,
        "action_reason": row.action_reason,
        "confidence": row.confidence,
        "performance_risk": row.performance_risk,
        "estimated_monthly_savings": row.estimated_monthly_savings,
        "owner": row.owner,
        "workflow_status": row.workflow_status,
        "recommendation_tier": row.recommendation_tier,
        "overall_score": row.overall_score,
        "advisor_finding": _parse_json(row.advisor_finding, {}),
        "cost_evidence": _parse_json(row.cost_evidence, {}),
        "utilization_evidence": _parse_json(row.utilization_evidence, {}),
        "decision_rules_applied": _parse_json(row.decision_rules_applied, []),
        "evidence_summary": evidence_summary_from_row(row),
        "workflow_history": _parse_json(row.workflow_history_json, []),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _distinct_action_savings(rows: list[Any]) -> float:
    """Sum savings once per resource (max value when duplicates exist)."""
    return distinct_action_savings(rows)


def _distinct_savings_for_query(q) -> float:
    rows = q.with_entities(
        OptimizationAction.resource_id,
        OptimizationAction.estimated_monthly_savings,
    ).all()
    return _distinct_action_savings(rows)


def list_optimization_actions(
    db: Session,
    subscription_id: str,
    *,
    workflow_status: str | None = None,
    action_type: str | None = None,
    confidence: str | None = None,
    resource_type: str | None = None,
    inventory_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    sub = subscription_id.strip().lower()
    q = _exclude_embedded_only_actions(
        db.query(OptimizationAction).filter(OptimizationAction.subscription_id == sub),
    )

    if inventory_only:
        q = q.join(ResourceSnapshot, _inventory_action_join(sub))

    if workflow_status:
        q = q.filter(OptimizationAction.workflow_status == workflow_status.strip().lower())
    if action_type:
        q = q.filter(OptimizationAction.action_type == action_type.strip().lower())
    if confidence:
        q = q.filter(OptimizationAction.confidence == confidence)
    if resource_type:
        q = q.filter(func.lower(OptimizationAction.resource_type) == resource_type.strip().lower())

    total = q.count()
    total_savings = _distinct_savings_for_query(q)
    rows = (
        q.order_by(
            OptimizationAction.estimated_monthly_savings.desc(),
            OptimizationAction.updated_at.desc(),
        )
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
        .all()
    )

    items = [serialize_action(r) for r in rows]
    summary = _action_summary(db, sub, inventory_only=inventory_only)
    page_savings = _distinct_action_savings(rows)

    return {
        "subscription_id": sub,
        "count": len(items),
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(items) < total,
        "summary": summary,
        "total_estimated_monthly_savings": total_savings,
        "distinct_estimated_monthly_savings": total_savings,
        "page_estimated_monthly_savings": page_savings,
        "distinct_page_estimated_monthly_savings": page_savings,
        "items": items,
    }


def _append_workflow_history(
    row: OptimizationAction,
    *,
    from_status: str,
    to_status: str,
    user: dict | None,
    note: str | None,
    event: str = "status_change",
    owner_from: str | None = None,
    owner_to: str | None = None,
) -> None:
    history = _parse_json(row.workflow_history_json, [])
    entry: dict[str, Any] = {
        "event": event,
        "from_status": from_status,
        "to_status": to_status,
        "user_id": (user or {}).get("id"),
        "user_name": (user or {}).get("display_name") or (user or {}).get("username"),
        "note": note,
        "at": utc_now().isoformat(),
    }
    if owner_from is not None or owner_to is not None:
        entry["owner_from"] = owner_from
        entry["owner_to"] = owner_to
    history.append(entry)
    row.workflow_history_json = json.dumps(history[-50:])


def update_optimization_action(
    db: Session,
    action: OptimizationAction,
    *,
    workflow_status: str | None = None,
    owner: str | None = None,
    note: str | None = None,
    user: dict | None = None,
    unset_owner: bool = False,
) -> OptimizationAction:
    previous = (action.workflow_status or "proposed").lower()
    previous_owner = action.owner
    trimmed_note = note.strip() if note else None
    status_changed = False
    owner_changed = False
    note_recorded = False

    if workflow_status is not None:
        normalized = workflow_status.strip().lower()
        if normalized not in VALID_WORKFLOW_STATUSES:
            raise ValueError(f"workflow_status must be one of: {sorted(VALID_WORKFLOW_STATUSES)}")
        if normalized != previous:
            _append_workflow_history(
                action,
                from_status=previous,
                to_status=normalized,
                user=user,
                note=trimmed_note,
                event="status_change",
            )
            action.workflow_status = normalized
            status_changed = True
            note_recorded = bool(trimmed_note)
        elif trimmed_note:
            _append_workflow_history(
                action,
                from_status=previous,
                to_status=previous,
                user=user,
                note=trimmed_note,
                event="note",
            )
            note_recorded = True

    if unset_owner:
        if previous_owner:
            _append_workflow_history(
                action,
                from_status=action.workflow_status or previous,
                to_status=action.workflow_status or previous,
                user=user,
                note=trimmed_note if not note_recorded else None,
                event="owner_change",
                owner_from=previous_owner,
                owner_to=None,
            )
            if trimmed_note and not note_recorded:
                note_recorded = True
            action.owner = None
            owner_changed = True
    elif owner is not None:
        new_owner = owner.strip() or None
        if new_owner != previous_owner:
            _append_workflow_history(
                action,
                from_status=action.workflow_status or previous,
                to_status=action.workflow_status or previous,
                user=user,
                note=trimmed_note if not note_recorded else None,
                event="owner_change",
                owner_from=previous_owner,
                owner_to=new_owner,
            )
            if trimmed_note and not note_recorded:
                note_recorded = True
            action.owner = new_owner
            owner_changed = True

    if trimmed_note and not note_recorded and not status_changed and not owner_changed:
        _append_workflow_history(
            action,
            from_status=previous,
            to_status=previous,
            user=user,
            note=trimmed_note,
            event="note",
        )

    action.updated_at = utc_now()
    return action


def bulk_update_optimization_actions(
    db: Session,
    *,
    subscription_id: str,
    action_ids: list[str],
    workflow_status: str,
    user: dict | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    sub = subscription_id.strip().lower()
    unique_ids = list(dict.fromkeys(action_ids))
    rows = (
        db.query(OptimizationAction)
        .filter(
            OptimizationAction.subscription_id == sub,
            OptimizationAction.id.in_(unique_ids),
        )
        .all()
    )
    if len(rows) != len(unique_ids):
        found = {r.id for r in rows}
        missing = [aid for aid in unique_ids if aid not in found]
        raise LookupError(f"Actions not found: {missing}")

    updated = 0
    for row in rows:
        update_optimization_action(
            db,
            row,
            workflow_status=workflow_status,
            user=user,
            note=note,
        )
        updated += 1

    db.commit()
    return {"updated": updated, "workflow_status": workflow_status.strip().lower()}


def bulk_assign_optimization_actions(
    db: Session,
    *,
    subscription_id: str,
    action_ids: list[str],
    owner: str,
    user: dict | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    sub = subscription_id.strip().lower()
    owner_value = owner.strip()
    if not owner_value:
        raise ValueError("owner is required")

    unique_ids = list(dict.fromkeys(action_ids))
    rows = (
        db.query(OptimizationAction)
        .filter(
            OptimizationAction.subscription_id == sub,
            OptimizationAction.id.in_(unique_ids),
        )
        .all()
    )
    if len(rows) != len(unique_ids):
        found = {r.id for r in rows}
        missing = [aid for aid in unique_ids if aid not in found]
        raise LookupError(f"Actions not found: {missing}")

    updated = 0
    for row in rows:
        update_optimization_action(
            db,
            row,
            owner=owner_value,
            user=user,
            note=note or "Bulk assign owner",
        )
        updated += 1

    db.commit()
    return {"updated": updated, "owner": owner_value}

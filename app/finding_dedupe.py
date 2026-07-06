"""Shared identity keys and deduplication for optimization findings."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.focus_mapping import normalize_arm_id

COMMITMENT_RULE_CANONICAL: dict[str, str] = {
    "SAVINGS_PLAN_OPPORTUNITY": "SAVINGS_PLAN_OPPORTUNITY_EXTENDED",
    "RESERVED_OPPORTUNITY": "RESERVED_OPPORTUNITY_EXTENDED",
}

SUBSCRIPTION_SCOPED_RULE_IDS = frozenset({
    *COMMITMENT_RULE_CANONICAL.keys(),
    *COMMITMENT_RULE_CANONICAL.values(),
})


def canonical_rule_id(rule_id: str | None) -> str:
    rid = (rule_id or "").strip().upper()
    return COMMITMENT_RULE_CANONICAL.get(rid, rid)


def _evidence_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def is_subscription_scoped_finding(
    *,
    rule_id: str | None,
    evidence: Any = None,
) -> bool:
    rule = canonical_rule_id(rule_id)
    if rule in SUBSCRIPTION_SCOPED_RULE_IDS:
        return True
    return _evidence_dict(evidence).get("scope") == "subscription"


def open_finding_identity_key(
    subscription_id: str,
    resource_id: str,
    rule_id: str,
    *,
    evidence: Any = None,
    subscription_scoped: bool | None = None,
) -> tuple[str, str, str]:
    """One open row per subscription + normalized resource + canonical rule."""
    sub = (subscription_id or "").strip().lower()
    rule = canonical_rule_id(rule_id)
    scoped = (
        subscription_scoped
        if subscription_scoped is not None
        else is_subscription_scoped_finding(rule_id=rule_id, evidence=evidence)
    )
    if scoped:
        return (sub, "", rule)
    return (sub, normalize_arm_id(resource_id), rule)


def dedupe_finding_dicts(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the latest finding per identity key (in-memory)."""
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    for finding in findings:
        key = open_finding_identity_key(
            finding.get("subscription_id") or "",
            finding.get("resource_id") or "",
            finding.get("rule_id") or "",
            evidence=finding.get("evidence"),
        )
        current = best.get(key)
        if not current:
            best[key] = finding
            continue
        cur_at = finding.get("detected_at") or ""
        prev_at = current.get("detected_at") or ""
        if str(cur_at) >= str(prev_at):
            best[key] = finding
    return list(best.values())


def row_finding_identity_key(row: Any) -> tuple[str, str, str]:
    return open_finding_identity_key(
        getattr(row, "subscription_id", None) or "",
        getattr(row, "resource_id", None) or "",
        getattr(row, "rule_id", None) or "",
        evidence=getattr(row, "evidence_json", None),
    )


def collect_open_identity_keys(rows: list[Any]) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for row in rows:
        if (getattr(row, "status", None) or "").lower() != "open":
            continue
        keys.add(row_finding_identity_key(row))
    return keys


def is_superseded_resolved_row(
    row: Any,
    open_keys: set[tuple[str, str, str]],
) -> bool:
    """True when a resolved row was auto-closed but the issue is still open."""
    if (getattr(row, "status", None) or "").lower() != "resolved":
        return False
    return row_finding_identity_key(row) in open_keys


def actionable_resolved_rows(
    resolved_rows: list[Any],
    open_keys: set[tuple[str, str, str]],
) -> list[Any]:
    """Resolved rows that are not superseded by a current open finding."""
    min_dt = datetime.min.replace(tzinfo=timezone.utc)
    best: dict[tuple[str, str, str], Any] = {}
    for row in resolved_rows:
        if is_superseded_resolved_row(row, open_keys):
            continue
        key = row_finding_identity_key(row)
        current = best.get(key)
        row_at = getattr(row, "detected_at", None) or min_dt
        cur_at = getattr(current, "detected_at", None) or min_dt if current else min_dt
        if not current or row_at >= cur_at:
            best[key] = row
    return list(best.values())


def collapse_open_finding_rows(
    rows: list[Any],
    *,
    subscription_id: str,
    now: datetime | None = None,
) -> dict[tuple[str, str, str], list[Any]]:
    """Group open rows by identity key; resolve duplicate open rows in-place."""
    grouped: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for row in rows:
        if (getattr(row, "status", None) or "").lower() != "open":
            continue
        key = open_finding_identity_key(
            subscription_id,
            getattr(row, "resource_id", None) or "",
            getattr(row, "rule_id", None) or "",
            evidence=getattr(row, "evidence_json", None),
        )
        grouped[key].append(row)

    resolved_at = now or datetime.now(timezone.utc)
    collapsed: dict[tuple[str, str, str], list[Any]] = {}
    for key, key_rows in grouped.items():
        if len(key_rows) <= 1:
            collapsed[key] = key_rows
            continue
        primary = max(key_rows, key=lambda row: getattr(row, "detected_at", None) or resolved_at)
        for duplicate in key_rows:
            if duplicate.id != primary.id:
                duplicate.status = "resolved"
                duplicate.resolved_at = resolved_at
        collapsed[key] = [primary]
    return collapsed

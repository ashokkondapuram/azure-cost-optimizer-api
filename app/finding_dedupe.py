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


def _finding_source_tag(finding: dict[str, Any]) -> str:
    evidence = _evidence_dict(finding.get("evidence"))
    return str(
        finding.get("data_source")
        or evidence.get("engine")
        or evidence.get("source")
        or ""
    ).lower()


def pick_better_finding(
    current: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Choose the stronger recommendation when two engines share an identity key."""
    try:
        savings_current = float(current.get("estimated_savings_usd") or 0)
        savings_candidate = float(candidate.get("estimated_savings_usd") or 0)
    except (TypeError, ValueError):
        savings_current = 0.0
        savings_candidate = 0.0

    if savings_candidate > savings_current:
        return candidate
    if savings_current > savings_candidate:
        return current

    severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
    sev_current = severity_rank.get(str(current.get("severity") or "MEDIUM").upper(), 2)
    sev_candidate = severity_rank.get(str(candidate.get("severity") or "MEDIUM").upper(), 2)
    if sev_candidate > sev_current:
        return candidate
    if sev_current > sev_candidate:
        return current

    src_current = _finding_source_tag(current)
    src_candidate = _finding_source_tag(candidate)
    if "legacy" in src_candidate and "legacy" not in src_current:
        return candidate
    if "legacy" in src_current and "legacy" not in src_candidate:
        return current

    detail_current = len(str(current.get("detail") or "")) + len(str(current.get("recommendation") or ""))
    detail_candidate = len(str(candidate.get("detail") or "")) + len(str(candidate.get("recommendation") or ""))
    if detail_candidate > detail_current:
        return candidate
    if detail_current > detail_candidate:
        return current

    cur_at = candidate.get("detected_at") or ""
    prev_at = current.get("detected_at") or ""
    return candidate if str(cur_at) >= str(prev_at) else current


def merge_unified_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge assessment + legacy findings, keeping the best recommendation per key."""
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    for finding in findings:
        key = open_finding_identity_key(
            finding.get("subscription_id") or "",
            finding.get("resource_id") or "",
            finding.get("rule_id") or "",
            evidence=finding.get("evidence"),
        )
        current = best.get(key)
        best[key] = finding if not current else pick_better_finding(current, finding)
    return list(best.values())


def dedupe_finding_dicts(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the latest finding per identity key (in-memory)."""
    return merge_unified_findings(findings)


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

"""Persist optimization runs/findings and write per-resource summaries back to inventory."""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import OptimizationFinding, OptimizationRun, ResourceSnapshot
from app.finding_evidence import enrich_evidence
from app.commitment_findings import dedupe_commitment_findings
from app.finding_dedupe import (
    collapse_open_finding_rows,
    dedupe_finding_dicts,
    open_finding_identity_key,
)
from app.focus_mapping import normalize_arm_id
from app.savings_aggregation import resolve_resource_savings
from app.vm_sizing_persist import normalize_vm_rightsizing_finding_dict
from app.recommendation_output import filter_valid_recommendations

SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


def _open_findings_query(db: Session, subscription_id: str):
    """Open findings for a subscription (case-insensitive subscription + status)."""
    sub = subscription_id.lower()
    return db.query(OptimizationFinding).filter(
        func.lower(OptimizationFinding.subscription_id) == sub,
        OptimizationFinding.status == "open",
    )


def _index_open_findings(
    rows: list[OptimizationFinding],
    subscription_id: str,
) -> dict[tuple[str, str, str], list[OptimizationFinding]]:
    grouped: dict[tuple[str, str, str], list[OptimizationFinding]] = defaultdict(list)
    sub = subscription_id.lower()
    for row in rows:
        key = open_finding_identity_key(
            sub,
            row.resource_id or "",
            row.rule_id or "",
            evidence=row.evidence_json,
        )
        grouped[key].append(row)
    return grouped


def _collapse_duplicate_open_findings(
    existing_open: dict[tuple[str, str, str], list[OptimizationFinding]],
    *,
    now: datetime,
) -> dict[tuple[str, str, str], list[OptimizationFinding]]:
    """Keep one open row per identity key; resolve the rest."""
    collapsed: dict[tuple[str, str, str], list[OptimizationFinding]] = {}
    for key, rows in existing_open.items():
        if len(rows) <= 1:
            collapsed[key] = rows
            continue
        primary = max(rows, key=lambda row: row.detected_at or now)
        for duplicate in rows:
            if duplicate.id != primary.id:
                duplicate.status = "resolved"
                duplicate.resolved_at = now
        collapsed[key] = [primary]
    return collapsed


def _apply_finding_payload(
    row: OptimizationFinding,
    *,
    finding: dict[str, Any],
    subscription_id: str,
    run_id: str,
    enriched: dict[str, Any],
    now: datetime,
) -> None:
    sub = subscription_id.lower()
    row.run_id = run_id
    row.rule_id = finding["rule_id"]
    row.rule_name = finding["rule_name"]
    row.category = finding["category"]
    row.severity = finding["severity"]
    row.resource_id = normalize_arm_id(finding.get("resource_id") or "")
    row.resource_name = finding["resource_name"]
    row.resource_type = finding["resource_type"]
    row.subscription_id = sub
    row.resource_group = finding.get("resource_group") or ""
    row.location = finding.get("location") or ""
    row.detail = finding["detail"]
    row.recommendation = finding["recommendation"]
    row.estimated_savings_usd = finding.get("estimated_savings_usd") or 0
    row.annualized_savings_usd = finding.get("annualized_savings_usd") or round(
        (finding.get("estimated_savings_usd") or 0) * 12, 2
    )
    row.waste_score = finding.get("waste_score") or 0
    row.confidence_score = finding.get("confidence_score") or 0
    row.action_priority = finding.get("action_priority")
    row.impact = finding.get("impact")
    row.evidence_json = json.dumps(enriched or {})
    row.chain_id = finding.get("chain_id")
    row.chain_step = finding.get("chain_step")
    row.chain_total = finding.get("chain_total")
    row.status = (finding.get("status") or "open").lower()
    row.resolved_at = None
    row.detected_at = now


def dedupe_open_findings_for_display(
    rows: list[OptimizationFinding],
) -> list[OptimizationFinding]:
    """Return one open row per identity key (latest detected_at)."""
    best: dict[tuple[str, str, str], OptimizationFinding] = {}
    for row in rows:
        if (row.status or "").lower() != "open":
            continue
        key = open_finding_identity_key(
            row.subscription_id or "",
            row.resource_id or "",
            row.rule_id or "",
            evidence=row.evidence_json,
        )
        current = best.get(key)
        if not current:
            best[key] = row
            continue
        row_at = row.detected_at or datetime.min.replace(tzinfo=timezone.utc)
        cur_at = current.detected_at or datetime.min.replace(tzinfo=timezone.utc)
        if row_at >= cur_at:
            best[key] = row

    kept_open_ids = {row.id for row in best.values()}
    seen_open_keys: set[tuple[str, str, str]] = set()
    out: list[OptimizationFinding] = []
    for row in rows:
        if (row.status or "").lower() != "open":
            out.append(row)
            continue
        key = open_finding_identity_key(
            row.subscription_id or "",
            row.resource_id or "",
            row.rule_id or "",
            evidence=row.evidence_json,
        )
        if row.id not in kept_open_ids or key in seen_open_keys:
            continue
        seen_open_keys.add(key)
        out.append(row)
    return out


def cleanup_duplicate_open_findings(
    db: Session,
    subscription_id: str,
    *,
    commit: bool = True,
) -> int:
    """Resolve duplicate open rows in the database; return rows resolved."""
    sub = subscription_id.lower()
    open_rows = (
        db.query(OptimizationFinding)
        .filter(
            func.lower(OptimizationFinding.subscription_id) == sub,
            func.lower(OptimizationFinding.status) == "open",
        )
        .all()
    )
    before = len(open_rows)
    collapsed = collapse_open_finding_rows(open_rows, subscription_id=sub, now=datetime.now(timezone.utc))
    after = sum(len(v) for v in collapsed.values())
    for key_rows in collapsed.values():
        for row in key_rows:
            row.subscription_id = sub
            if row.resource_id:
                row.resource_id = normalize_arm_id(row.resource_id)
    if after < before and commit:
        db.commit()
    return before - after


def supersede_open_findings(
    db: Session,
    subscription_id: str,
    *,
    commit: bool = False,
) -> int:
    """Resolve all open findings so the next analysis run replaces them entirely."""
    sub = subscription_id.lower()
    now = datetime.now(timezone.utc)
    count = _open_findings_query(db, sub).count()
    if not count:
        return 0
    _open_findings_query(db, sub).update(
        {"status": "resolved", "resolved_at": now},
        synchronize_session=False,
    )
    if commit:
        db.commit()
    return count


def _prepare_open_findings_for_persist(
    db: Session,
    subscription_id: str,
    *,
    scope_resource_types: set[str] | None,
    now: datetime,
) -> dict[tuple[str, str, str], list[OptimizationFinding]]:
    """Collapse legacy duplicates; full runs supersede all prior open findings."""
    sub = subscription_id.lower()
    _normalize_and_collapse_open_findings(db, sub, now=now)
    db.flush()

    if scope_resource_types is None:
        supersede_open_findings(db, sub, commit=False)
        return {}

    all_open_rows = _open_findings_query(db, sub).all()
    return _collapse_duplicate_open_findings(
        _index_open_findings(all_open_rows, sub),
        now=now,
    )


def close_open_findings(
    db: Session,
    subscription_id: str,
    *,
    components: list[str] | None = None,
) -> int:
    """Resolve prior open findings so the latest run is the source of truth in the UI."""
    sub = subscription_id.lower()
    now = datetime.now(timezone.utc)
    q = _open_findings_query(db, sub)
    if components:
        from app.optimizer.component_map import resource_types_for_components
        from app.optimizer.rule_catalog import RULE_MANIFEST

        want = set(components)
        rule_ids = {rid for rid, meta in RULE_MANIFEST.items() if meta.get("component") in want}
        if rule_ids:
            q = q.filter(OptimizationFinding.rule_id.in_(rule_ids))
        else:
            rtypes = resource_types_for_components(list(want))
            if rtypes:
                q = q.filter(OptimizationFinding.resource_type.in_(sorted(rtypes)))
            else:
                return 0
    count = q.count()
    q.update(
        {"status": "resolved", "resolved_at": now},
        synchronize_session=False,
    )
    return count


def persist_optimization_run(
    db: Session,
    *,
    subscription_id: str,
    profile: str,
    engine_version: str,
    result: dict[str, Any],
    data_source: str = "db",
    scope_resource_types: set[str] | None = None,
    scope_resource_ids: set[str] | None = None,
) -> str:
    """Store run + findings; update resource_snapshots with recommendation summaries."""
    sub = subscription_id.lower()
    run_id = str(uuid.uuid4())
    sev = result.get("summary", {}).get("by_severity", {})
    findings = filter_valid_recommendations(dedupe_finding_dicts(dedupe_commitment_findings([
        normalize_vm_rightsizing_finding_dict(f) for f in (result.get("findings") or [])
    ])))

    run = OptimizationRun(
        id=run_id,
        subscription_id=sub,
        profile=profile,
        engine_version=engine_version,
        total_findings=result.get("summary", {}).get("total_findings", len(findings)),
        critical_count=sev.get("CRITICAL", 0),
        high_count=sev.get("HIGH", 0),
        medium_count=sev.get("MEDIUM", 0),
        low_count=sev.get("LOW", 0),
        total_savings_usd=result.get("summary", {}).get("total_estimated_monthly_savings_usd", 0),
        findings_json=json.dumps(findings),
    )
    db.add(run)

    now = datetime.now(timezone.utc)
    existing_open = _prepare_open_findings_for_persist(
        db,
        sub,
        scope_resource_types=scope_resource_types,
        now=now,
    )

    seen_keys: set[tuple[str, str, str]] = set()
    chunk_size = 100
    for idx, f in enumerate(findings):
        key = open_finding_identity_key(
            sub,
            f.get("resource_id") or "",
            f.get("rule_id") or "",
            evidence=f.get("evidence"),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)

        enriched = enrich_evidence(
            f.get("rule_id") or "",
            f.get("evidence"),
            f,
        )
        existing_rows = existing_open.get(key, [])
        if existing_rows:
            primary = max(existing_rows, key=lambda row: row.detected_at or now)
            _apply_finding_payload(
                primary,
                finding=f,
                subscription_id=sub,
                run_id=run_id,
                enriched=enriched,
                now=now,
            )
            for duplicate in existing_rows:
                if duplicate.id != primary.id:
                    duplicate.status = "resolved"
                    duplicate.resolved_at = now
        else:
            new_row = OptimizationFinding(
                id=str(uuid.uuid4()),
                run_id=run_id,
                rule_id=f["rule_id"],
                rule_name=f["rule_name"],
                category=f["category"],
                severity=f["severity"],
                resource_id=normalize_arm_id(f.get("resource_id") or ""),
                resource_name=f["resource_name"],
                resource_type=f["resource_type"],
                subscription_id=sub,
                resource_group=f.get("resource_group") or "",
                location=f.get("location") or "",
                detail=f["detail"],
                recommendation=f["recommendation"],
                estimated_savings_usd=f.get("estimated_savings_usd") or 0,
                annualized_savings_usd=f.get("annualized_savings_usd")
                or round((f.get("estimated_savings_usd") or 0) * 12, 2),
                waste_score=f.get("waste_score") or 0,
                confidence_score=f.get("confidence_score") or 0,
                action_priority=f.get("action_priority"),
                impact=f.get("impact"),
                evidence_json=json.dumps(enriched or {}),
                chain_id=f.get("chain_id"),
                chain_step=f.get("chain_step"),
                chain_total=f.get("chain_total"),
                status="open",
                detected_at=now,
            )
            db.add(new_row)
            existing_open[key] = [new_row]
        if (idx + 1) % chunk_size == 0:
            db.flush()

    for key, rows in existing_open.items():
        if key in seen_keys:
            continue
        primary = rows[0]
        if scope_resource_ids and normalize_arm_id(primary.resource_id or "") not in scope_resource_ids:
            continue
        if scope_resource_types and (primary.resource_type or "") not in scope_resource_types:
            continue
        for row in rows:
            row.status = "resolved"
            row.resolved_at = now

    if scope_resource_types is not None or scope_resource_ids is not None:
        _normalize_and_collapse_open_findings(db, sub, now=now)

    update_resource_analysis_summaries(
        db, sub, findings, run_id, data_source,
        scope_resource_types=scope_resource_types,
        scope_resource_ids=scope_resource_ids,
    )
    db.commit()
    return run_id


def _normalize_and_collapse_open_findings(
    db: Session,
    subscription_id: str,
    *,
    now: datetime,
) -> None:
    """Normalize legacy rows and resolve duplicate open findings for one subscription."""
    sub = subscription_id.lower()
    rows = _open_findings_query(db, sub).all()
    collapsed = _collapse_duplicate_open_findings(
        _index_open_findings(rows, sub),
        now=now,
    )
    for key_rows in collapsed.values():
        for row in key_rows:
            row.subscription_id = sub
            if row.resource_id:
                row.resource_id = normalize_arm_id(row.resource_id)


def update_resource_analysis_summaries(
    db: Session,
    subscription_id: str,
    findings: list[dict[str, Any]],
    run_id: str,
    data_source: str,
    *,
    scope_resource_types: set[str] | None = None,
    scope_resource_ids: set[str] | None = None,
) -> None:
    """Write recommendation counts and top actions onto resource_snapshots for fast UI reads."""
    now = datetime.now(timezone.utc)
    q = db.query(ResourceSnapshot).filter(
        ResourceSnapshot.subscription_id == subscription_id,
        ResourceSnapshot.is_active.is_(True),
    )
    if scope_resource_ids:
        normalized_ids = sorted(scope_resource_ids)
        q = q.filter(func.lower(ResourceSnapshot.resource_id).in_(normalized_ids))
    elif scope_resource_types:
        q = q.filter(ResourceSnapshot.resource_type.in_(sorted(scope_resource_types)))
    snapshot_rows = q.all()
    for snapshot_row in snapshot_rows:
        snapshot_row.analysis_findings_count = 0
        snapshot_row.analysis_savings_usd = 0.0
        snapshot_row.analysis_top_severity = None
        snapshot_row.analysis_updated_at = now
        snapshot_row.analysis_run_id = run_id
        snapshot_row.analysis_data_source = data_source
        snapshot_row.analysis_summary_json = "[]"

    by_resource: dict[str, list[dict]] = defaultdict(list)
    for finding in findings:
        rid = (finding.get("resource_id") or "").strip().lower()
        if rid:
            by_resource[rid].append(finding)

    row_by_id = {(r.resource_id or "").lower(): r for r in snapshot_rows}
    for rid, flist in by_resource.items():
        snapshot_row = row_by_id.get(rid)
        if not snapshot_row:
            continue
        flist_sorted = sorted(
            flist,
            key=lambda f: (
                SEVERITY_RANK.get(f.get("severity", "INFO"), 9),
                -(f.get("estimated_savings_usd") or 0),
                -(f.get("waste_score") or 0),
            ),
        )
        top = flist_sorted[0]
        summary = [
            {
                "rule_id": f.get("rule_id"),
                "rule_name": f.get("rule_name"),
                "severity": f.get("severity"),
                "recommendation": f.get("recommendation"),
                "estimated_savings_usd": f.get("estimated_savings_usd") or 0,
            }
            for f in flist_sorted[:5]
        ]
        snapshot_row.analysis_findings_count = len(flist)
        breakdown = resolve_resource_savings(resource_id=rid, findings=flist)
        snapshot_row.analysis_savings_usd = round(float(breakdown.unified_monthly or 0), 2)
        snapshot_row.analysis_top_severity = top.get("severity")
        snapshot_row.analysis_summary_json = json.dumps(summary)
        snapshot_row.analysis_updated_at = now
        try:
            from app.data_store.resource_enrichment import upsert_recommendations

            upsert_recommendations(
                db,
                snapshot_row,
                summary=summary,
                findings_count=len(flist),
                savings_usd=round(float(breakdown.unified_monthly or 0), 2),
                top_severity=top.get("severity"),
                run_id=run_id,
                data_source=data_source,
            )
        except Exception:
            pass


def refresh_resource_analysis_summary(
    db: Session,
    *,
    subscription_id: str,
    resource_id: str,
) -> None:
    """Recompute denormalized analysis fields on one inventory row from open findings."""
    sub = subscription_id.lower()
    rid = (resource_id or "").strip().lower()
    if not rid:
        return

    snapshot_row = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.resource_id == rid,
            ResourceSnapshot.is_active.is_(True),
        )
        .first()
    )
    if not snapshot_row:
        return

    norm_rid = normalize_arm_id(resource_id)
    open_findings = dedupe_open_findings_for_display([
        f
        for f in _open_findings_query(db, sub).all()
        if normalize_arm_id(f.resource_id or "") == norm_rid
    ])
    now = datetime.now(timezone.utc)
    if not open_findings:
        snapshot_row.analysis_findings_count = 0
        snapshot_row.analysis_savings_usd = 0.0
        snapshot_row.analysis_top_severity = None
        snapshot_row.analysis_summary_json = "[]"
        snapshot_row.analysis_updated_at = now
        db.commit()
        return

    flist = [
        {
            "rule_id": f.rule_id,
            "rule_name": f.rule_name,
            "severity": f.severity,
            "recommendation": f.recommendation,
            "estimated_savings_usd": f.estimated_savings_usd or 0,
        }
        for f in open_findings
    ]
    flist_sorted = sorted(
        flist,
        key=lambda f: (
            SEVERITY_RANK.get(f.get("severity", "INFO"), 9),
            -(f.get("estimated_savings_usd") or 0),
        ),
    )
    top = flist_sorted[0]
    summary = [
        {
            "rule_id": f.get("rule_id"),
            "rule_name": f.get("rule_name"),
            "severity": f.get("severity"),
            "recommendation": f.get("recommendation"),
            "estimated_savings_usd": f.get("estimated_savings_usd") or 0,
        }
        for f in flist_sorted[:5]
    ]
    snapshot_row.analysis_findings_count = len(flist_sorted)
    breakdown = resolve_resource_savings(resource_id=rid, findings=open_findings)
    snapshot_row.analysis_savings_usd = round(float(breakdown.unified_monthly or 0), 2)
    snapshot_row.analysis_top_severity = top.get("severity")
    snapshot_row.analysis_summary_json = json.dumps(summary)
    snapshot_row.analysis_updated_at = now
    try:
        from app.data_store.resource_enrichment import upsert_recommendations

        upsert_recommendations(
            db,
            snapshot_row,
            summary=summary,
            findings_count=len(flist_sorted),
            savings_usd=float(snapshot_row.analysis_savings_usd or 0),
            top_severity=top.get("severity"),
        )
    except Exception:
        pass
    db.commit()

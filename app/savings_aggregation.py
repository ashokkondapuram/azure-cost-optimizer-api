"""Cross-source savings classification, deduplication, and rollups.

Azure Advisor and the optimization engine may both flag the same resource for
cost actions (for example decommission vs SKU reduction). Subscription totals must
not sum overlapping signals. Per resource we:

1. Classify each signal (decommission, rightsize, commitment, …).
2. Within an action class, take max(advisor, engine) — never sum both sources.
3. When decommission and rightsize both apply, decommission wins.
4. Sum unified amounts across resources and action classes only when distinct.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.analysis_persist import dedupe_open_findings_for_display
from app.models import AdvisorRecommendation, OptimizationFinding
from app.utils import norm_arm_id

# ── Action taxonomy ───────────────────────────────────────────────────────────

class SavingsActionClass(str, Enum):
    DECOMMISSION = "decommission"
    RIGHTSIZE = "rightsize"
    COMMITMENT = "commitment"
    SCHEDULE = "schedule"
    GOVERNANCE = "governance"
    OTHER_COST = "other_cost"
    NON_COST = "non_cost"


RIGHTSIZE_RULE_IDS = frozenset({
    "VM_SKU_SIZING_EXTENDED",
    "VM_RIGHTSIZE_FAMILY",
    "VM_UNDERUTILIZED_EXTENDED",
    "VM_OVERSIZE",
    "VM_UNDERUTILIZED",
    "REDIS_RIGHTSIZE_EXTENDED",
    "REDIS_TIER_REVIEW",
    "REDIS_MEMORY_PRESSURE",
    "DISK_OVERSIZE_EXTENDED",
    "DISK_CAPACITY_RIGHTSIZE_EXTENDED",
    "VMSS_AUTOSCALE_TUNING_EXTENDED",
    "WEBAPP_PLAN_LOAD_LOW_EXTENDED",
    "ASP_CONSOLIDATION_CANDIDATE_EXTENDED",
    "AKS_POD_DENSITY_EXTENDED",
    "STORAGE_COOL_TIER_CANDIDATE_EXTENDED",
    "ACR_IMAGE_RETENTION_EXTENDED",
    "VM_EGRESS_HIGH_EXTENDED",
    "STORAGE_EGRESS_HIGH_EXTENDED",
    "POSTGRESQL_BURSTABLE_EXTENDED",
    "POSTGRESQL_STORAGE_EXTENDED",
    "POSTGRESQL_STORAGE_EXPANSION",
    "POSTGRESQL_HA_UNNECESSARY",
    "POSTGRESQL_READ_REPLICA_ANALYSIS",
    "COSMOS_AUTOSCALE_EXTENDED",
    "COSMOS_SERVERLESS",
    "COSMOS_RU_RIGHT_SIZING_UNDER",
    "COSMOS_RU_RIGHT_SIZING_OVER",
    "COSMOS_INDEXING_OVERPROVISIONED",
    "COSMOS_MULTI_WRITE_UNNECESSARY",
    "COSMOS_API_COST_VARIANCE",
    "COSMOS_CONSISTENCY_OVERPROVISIONED",
    "LOAD_BALANCER_THROUGHPUT_RIGHTSIZE",
    "LOAD_BALANCER_BACKEND_CONSOLIDATION",
    "APP_GATEWAY_CU_RIGHTSIZE_DOWN",
    "PRIVATE_ENDPOINT_UNDERUTILIZED",
    "PRIVATE_LINK_NAT_RIGHTSIZE",
    "PRIVATE_DNS_UNUSED_ZONE",
    "VNET_PEERING_CONSOLIDATION_EXTENDED",
    "NSG_FLOW_LOG_COST",
    "NAT_GATEWAY_SKU_V2_UPGRADE",
    "NAT_GATEWAY_SUBNET_CONSOLIDATION",
})

DECOMMISSION_RULE_IDS = frozenset({
    "VM_IDLE",
    "VM_STOPPED_DEALLOCATED",
    "VM_STOPPED_BILLING_EXTENDED",
    "VM_ZOMBIE_CANDIDATE_EXTENDED",
    "DISK_UNATTACHED",
    "DISK_UNUSED_EXTENDED",
    "IP_UNASSOCIATED",
    "AKS_EMPTY_POOL",
    "SNAPSHOT_STALE_EXTENDED",
    "SNAPSHOT_ARCHIVE_EXTENDED",
    "APP_SERVICE_IDLE_EXTENDED",
    "LOAD_BALANCER_NO_BACKEND",
    "LOAD_BALANCER_IDLE_EXTENDED",
    "NAT_GATEWAY_UNUSED_EXTENDED",
    "NAT_GATEWAY_IDLE_EXTENDED",
    "PUBLIC_IP_UNASSOCIATED",
    "PUBLIC_IP_IDLE_EXTENDED",
    "PRIVATE_ENDPOINT_ORPHAN_EXTENDED",
    "PRIVATE_LINK_UNUSED_EXTENDED",
    "PRIVATE_DNS_EMPTY_EXTENDED",
    "PRIVATE_DNS_UNUSED_ZONE",
    "APP_GATEWAY_IDLE_EXTENDED",
    "NIC_ORPHANED_EXTENDED",
    "NSG_ORPHANED_EXTENDED",
    "WEBAPP_STOPPED_EXTENDED",
})

COMMITMENT_RULE_IDS = frozenset({
    "VM_NO_RESERVED",
    "VM_COMMITMENT_CANDIDATE",
    "AKS_COMMITMENT_CANDIDATE",
    "RESERVED_INSTANCE_OPPORTUNITY",
    "SAVINGS_PLAN_OPPORTUNITY",
})

SCHEDULE_RULE_IDS = frozenset({
    "VM_SCHEDULE_CANDIDATE_EXTENDED",
})

GOVERNANCE_RULE_IDS = frozenset({
    "VM_MISSING_GOVERNANCE_TAGS",
    "GOVERNANCE_TAGS_EXTENDED",
    "MISSING_GOVERNANCE_TAGS",
})

_DECOMMISSION_TEXT = re.compile(
    r"\b(decommission|shut\s*down|shutdown|delete|remove|terminate|deallocate|"
    r"eliminate|retire|unused|idle|orphan|unattached|zombie)\b",
    re.I,
)
_RIGHTSIZE_TEXT = re.compile(
    r"\b(right[\s-]?size|resize|downsize|sku|smaller|underutiliz|oversiz|"
    r"reduce\s+capacity|change\s+family)\b",
    re.I,
)
_COMMITMENT_TEXT = re.compile(
    r"\b(reserved\s+instance|reservation|savings\s+plan|commitment|prepay)\b",
    re.I,
)

_ACTION_CLASS_LABELS = {
    SavingsActionClass.DECOMMISSION: "Decommission",
    SavingsActionClass.RIGHTSIZE: "Rightsize",
    SavingsActionClass.COMMITMENT: "Commitment",
    SavingsActionClass.SCHEDULE: "Schedule",
    SavingsActionClass.GOVERNANCE: "Governance",
    SavingsActionClass.OTHER_COST: "Cost",
    SavingsActionClass.NON_COST: "Non-cost",
}


def action_class_label(action_class: SavingsActionClass | str) -> str:
    if isinstance(action_class, SavingsActionClass):
        return _ACTION_CLASS_LABELS.get(action_class, action_class.value)
    try:
        return _ACTION_CLASS_LABELS[SavingsActionClass(action_class)]
    except ValueError:
        return str(action_class).replace("_", " ").title()


def _parse_evidence(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return {}


def _text_blob(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts if p)


def _field(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def classify_engine_finding(finding: Any) -> SavingsActionClass:
    """Map an optimization finding to a savings action class."""
    from app.rule_behavior import canonical_rule_id, classify_rule_action_class

    rule_id = str(_field(finding, "rule_id") or "").upper()
    canonical = canonical_rule_id(rule_id).upper()
    behavior_class = classify_rule_action_class(rule_id)
    if behavior_class is not None:
        return behavior_class
    if canonical in DECOMMISSION_RULE_IDS or rule_id in DECOMMISSION_RULE_IDS:
        return SavingsActionClass.DECOMMISSION
    if canonical in RIGHTSIZE_RULE_IDS or rule_id in RIGHTSIZE_RULE_IDS:
        return SavingsActionClass.RIGHTSIZE
    if rule_id in COMMITMENT_RULE_IDS:
        return SavingsActionClass.COMMITMENT
    if rule_id in SCHEDULE_RULE_IDS:
        return SavingsActionClass.SCHEDULE
    if rule_id in GOVERNANCE_RULE_IDS:
        return SavingsActionClass.GOVERNANCE

    evidence = _parse_evidence(_field(finding, "evidence_json") or _field(finding, "evidence"))
    sizing_action = str(evidence.get("sizing_action") or "").lower()
    if sizing_action in {"downgrade", "cross_family", "upgrade"}:
        return SavingsActionClass.RIGHTSIZE

    text = _text_blob(
        _field(finding, "rule_name"),
        _field(finding, "detail"),
        _field(finding, "recommendation"),
        rule_id,
    )
    if _DECOMMISSION_TEXT.search(text):
        return SavingsActionClass.DECOMMISSION
    if _RIGHTSIZE_TEXT.search(text):
        return SavingsActionClass.RIGHTSIZE
    if _COMMITMENT_TEXT.search(text):
        return SavingsActionClass.COMMITMENT

    category = str(_field(finding, "category") or "").upper()
    savings = monthly_savings_finding(finding)
    if category == "COST" or savings > 0:
        return SavingsActionClass.OTHER_COST
    return SavingsActionClass.NON_COST


def classify_advisor_recommendation(rec: Any) -> SavingsActionClass:
    """Map an Azure Advisor recommendation to a savings action class."""
    category = str(_field(rec, "category") or "").strip()
    cat_lower = category.lower()
    if cat_lower not in {"cost"}:
        return SavingsActionClass.NON_COST

    text = _text_blob(
        _field(rec, "summary"),
        _field(rec, "description"),
        _field(rec, "recommendation_id"),
    )
    if _COMMITMENT_TEXT.search(text):
        return SavingsActionClass.COMMITMENT
    if _DECOMMISSION_TEXT.search(text):
        return SavingsActionClass.DECOMMISSION
    if _RIGHTSIZE_TEXT.search(text):
        return SavingsActionClass.RIGHTSIZE
    return SavingsActionClass.OTHER_COST


def monthly_savings_advisor(rec: Any) -> float:
    return round(float(_field(rec, "potential_savings_monthly") or 0), 2)


def monthly_savings_finding(finding: Any) -> float:
    if isinstance(finding, dict):
        value = finding.get("estimated_savings_usd")
    else:
        value = getattr(finding, "estimated_savings_usd", None)
    return round(float(value or 0), 2)


@dataclass
class SavingsSignal:
    source: str
    action_class: SavingsActionClass
    monthly_savings: float
    label: str
    detail: str = ""
    priority: int = 0


@dataclass
class ResourceSavingsBreakdown:
    resource_id: str
    unified_monthly: float = 0.0
    by_action_class: dict[str, float] = field(default_factory=dict)
    signals: list[SavingsSignal] = field(default_factory=list)
    advisor_raw_monthly: float = 0.0
    engine_raw_monthly: float = 0.0
    overlap_action_classes: list[str] = field(default_factory=list)


def _signal_label(source: str, action_class: SavingsActionClass, item: Any) -> str:
    prefix = "Azure Advisor" if source == "advisor" else "Recommendation engine"
    if source == "advisor":
        detail = _field(item, "summary") or ""
    else:
        detail = _field(item, "rule_name") or ""
    return f"{prefix} · {action_class_label(action_class)} · {detail}".strip(" ·")


def _max_signal(signals: Iterable[SavingsSignal]) -> SavingsSignal | None:
    ordered = sorted(signals, key=lambda s: (s.monthly_savings, s.priority), reverse=True)
    return ordered[0] if ordered else None


def _competing_signals(signals: list[SavingsSignal]) -> list[SavingsSignal]:
    """Signals eligible to win unified savings for an action class.

    Engine findings always compete. Advisor rows only compete when they carry a
    positive savings amount — Advisor SKU alignment is handled at finding time
    and must not zero out engine-computed savings.
    """
    engine = [s for s in signals if s.source == "engine"]
    advisor = [s for s in signals if s.source == "advisor" and s.monthly_savings > 0]
    if engine:
        return engine + advisor
    return signals


def resolve_resource_savings(
    *,
    resource_id: str,
    advisor_recs: list[Any] | None = None,
    findings: list[Any] | None = None,
    finding_savings_by_id: dict[str, float] | None = None,
) -> ResourceSavingsBreakdown:
    """Resolve non-overlapping monthly savings for one resource."""
    advisor_recs = advisor_recs or []
    findings = findings or []
    by_class: dict[SavingsActionClass, list[SavingsSignal]] = defaultdict(list)

    advisor_raw = 0.0
    for rec in advisor_recs:
        status = str(_field(rec, "status") or "Active")
        if status != "Active":
            continue
        action_class = classify_advisor_recommendation(rec)
        if action_class == SavingsActionClass.NON_COST:
            continue
        savings = monthly_savings_advisor(rec)
        advisor_raw += savings
        by_class[action_class].append(SavingsSignal(
            source="advisor",
            action_class=action_class,
            monthly_savings=savings,
            label=_signal_label("advisor", action_class, rec),
            detail=str(_field(rec, "summary") or ""),
            priority=2 if savings > 0 else 1,
        ))

    engine_raw = 0.0
    for finding in findings:
        status = str(_field(finding, "status") or "open").lower()
        if status not in {"open", "acknowledged"}:
            continue
        action_class = classify_engine_finding(finding)
        if action_class == SavingsActionClass.NON_COST:
            continue
        savings = monthly_savings_finding(finding)
        finding_id = str(_field(finding, "id") or "")
        if finding_savings_by_id and finding_id in finding_savings_by_id:
            override = finding_savings_by_id[finding_id]
            savings = float(override[0] if isinstance(override, tuple) else override)
        engine_raw += savings
        by_class[action_class].append(SavingsSignal(
            source="engine",
            action_class=action_class,
            monthly_savings=savings,
            label=_signal_label("engine", action_class, finding),
            detail=str(_field(finding, "rule_name") or ""),
            priority=2 if savings > 0 else 1,
        ))

    overlap_classes: list[str] = []
    selected: dict[SavingsActionClass, SavingsSignal] = {}
    for action_class, signals in by_class.items():
        advisor_signals = [s for s in signals if s.source == "advisor"]
        engine_signals = [s for s in signals if s.source == "engine"]
        if advisor_signals and engine_signals:
            overlap_classes.append(action_class.value)
        pool = _competing_signals(signals)
        best = _max_signal(pool)
        if best:
            selected[action_class] = best

    # Decommission supersedes rightsize on the same resource.
    if SavingsActionClass.DECOMMISSION in selected and SavingsActionClass.RIGHTSIZE in selected:
        del selected[SavingsActionClass.RIGHTSIZE]

    by_action_class = {
        cls.value: round(sig.monthly_savings, 2)
        for cls, sig in selected.items()
        if sig.monthly_savings > 0 or cls in {
            SavingsActionClass.DECOMMISSION,
            SavingsActionClass.RIGHTSIZE,
            SavingsActionClass.COMMITMENT,
        }
    }
    unified = round(sum(v for v in by_action_class.values()), 2)

    return ResourceSavingsBreakdown(
        resource_id=resource_id,
        unified_monthly=unified,
        by_action_class=by_action_class,
        signals=list(selected.values()),
        advisor_raw_monthly=round(advisor_raw, 2),
        engine_raw_monthly=round(engine_raw, 2),
        overlap_action_classes=overlap_classes,
    )


def _group_by_resource(
    advisor_rows: list[AdvisorRecommendation],
    finding_rows: list[OptimizationFinding],
) -> dict[str, tuple[list[AdvisorRecommendation], list[OptimizationFinding]]]:
    grouped: dict[str, tuple[list[AdvisorRecommendation], list[OptimizationFinding]]] = defaultdict(
        lambda: ([], []),
    )
    for rec in advisor_rows:
        rid = norm_arm_id(rec.resource_id or "")
        if rid:
            grouped[rid][0].append(rec)
    for finding in finding_rows:
        rid = norm_arm_id(finding.resource_id or "")
        if rid:
            grouped[rid][1].append(finding)
    return grouped


def aggregate_subscription_savings(
    db: Session,
    subscription_id: str,
    *,
    include_acknowledged: bool = True,
) -> dict[str, Any]:
    """Subscription rollup with cross-source deduplication."""
    sub = subscription_id.strip().lower()
    statuses = ["open"]
    if include_acknowledged:
        statuses.append("acknowledged")

    open_rows = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status.in_(statuses),
        )
        .all()
    )
    deduped_findings = dedupe_open_findings_for_display(open_rows)

    advisor_rows = (
        db.query(AdvisorRecommendation)
        .filter(
            AdvisorRecommendation.subscription_id == sub,
            AdvisorRecommendation.status == "Active",
        )
        .all()
    )

    grouped = _group_by_resource(advisor_rows, deduped_findings)
    resource_ids = set(grouped.keys())

    # Resources referenced only on one side still matter for raw totals.
    for rec in advisor_rows:
        rid = norm_arm_id(rec.resource_id or "")
        if rid:
            resource_ids.add(rid)
    for finding in deduped_findings:
        rid = norm_arm_id(finding.resource_id or "")
        if rid:
            resource_ids.add(rid)

    unified_total = 0.0
    advisor_raw_total = 0.0
    engine_raw_total = 0.0
    by_action_class: dict[str, float] = defaultdict(float)
    overlap_resources = 0
    overlap_classes_total: dict[str, int] = defaultdict(int)
    resources_with_signals = 0

    for rid in resource_ids:
        recs, findings = grouped.get(rid, ([], []))
        if not recs and not findings:
            continue
        breakdown = resolve_resource_savings(
            resource_id=rid,
            advisor_recs=recs,
            findings=findings,
        )
        if not breakdown.signals and breakdown.unified_monthly <= 0:
            if breakdown.advisor_raw_monthly <= 0 and breakdown.engine_raw_monthly <= 0:
                continue
        resources_with_signals += 1
        unified_total += breakdown.unified_monthly
        advisor_raw_total += breakdown.advisor_raw_monthly
        engine_raw_total += breakdown.engine_raw_monthly
        if breakdown.overlap_action_classes:
            overlap_resources += 1
            for cls in breakdown.overlap_action_classes:
                overlap_classes_total[cls] += 1
        for cls, amount in breakdown.by_action_class.items():
            by_action_class[cls] += amount

    return {
        "unified_estimated_monthly_savings": round(unified_total, 2),
        "advisor_raw_monthly_savings": round(advisor_raw_total, 2),
        "engine_raw_monthly_savings": round(engine_raw_total, 2),
        "double_count_avoided_monthly": round(
            max(0.0, advisor_raw_total + engine_raw_total - unified_total),
            2,
        ),
        "by_action_class": {k: round(v, 2) for k, v in sorted(by_action_class.items())},
        "resources_with_signals": resources_with_signals,
        "resources_with_overlap": overlap_resources,
        "overlap_by_action_class": dict(overlap_classes_total),
        "advisor_active_count": len(advisor_rows),
        "engine_open_count": len(deduped_findings),
        "merged_signal_count": resources_with_signals,
    }


def aggregate_findings_savings(findings: list[Any], savings_by_id: dict[str, float] | None = None) -> dict[str, Any]:
    """Engine-only rollup for waste heatmap with per-resource dedupe."""
    savings_by_id = savings_by_id or {}
    by_resource: dict[str, list[Any]] = defaultdict(list)
    for finding in findings:
        rid = norm_arm_id(_field(finding, "resource_id") or "")
        if rid:
            by_resource[rid].append(finding)

    unified_total = 0.0
    raw_total = 0.0
    by_action_class: dict[str, float] = defaultdict(float)
    findings_with_savings = 0

    for rid, rows in by_resource.items():
        for row in rows:
            fid = _field(row, "id") or _field(row, "finding_id")
            resolved_amount = savings_by_id.get(fid, monthly_savings_finding(row))
            if isinstance(resolved_amount, tuple):
                resolved_amount = resolved_amount[0]
            raw_total += float(resolved_amount or 0)
        breakdown = resolve_resource_savings(
            resource_id=rid,
            findings=rows,
            finding_savings_by_id=savings_by_id,
        )
        if breakdown.unified_monthly > 0:
            findings_with_savings += 1
        unified_total += breakdown.unified_monthly
        for cls, amount in breakdown.by_action_class.items():
            by_action_class[cls] += amount

    return {
        "total_estimated_savings_usd": round(unified_total, 2),
        "raw_total_estimated_savings_usd": round(raw_total, 2),
        "double_count_avoided_usd": round(max(0.0, raw_total - unified_total), 2),
        "by_action_class_savings": {k: round(v, 2) for k, v in sorted(by_action_class.items())},
        "findings_with_savings": findings_with_savings,
    }

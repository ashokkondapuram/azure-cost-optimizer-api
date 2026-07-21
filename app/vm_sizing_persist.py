"""Persist live VM sizing recommendations as open optimization findings."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.finding_evidence import enrich_evidence
from app.focus_mapping import normalize_arm_id
from app.models import OptimizationFinding, OptimizationRun
from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.resource_engines.compute.vm.helpers import (
    VM_RIGHTSIZING_RULE_IDS,
    VM_RIGHTSIZING_SEVERITY,
    emit_vm_sizing_finding,
    vm_catalog,
    vm_utilization,
)
from app.resource_utilization import merge_vm_utilization_facts, vm_sizing_metrics_ok
from app.cost_utils import project_mtd_to_monthly_run_rate, resource_cost
from app.vm_sizing import VmSizingRecommendation, VmUtilization, recommend_vm_sku

RIGHTSIZING_RULE_IDS = frozenset({
    *VM_RIGHTSIZING_RULE_IDS,
    "VM_OVERSIZE",
    "VM_UNDERUTILIZED_EXTENDED",
})
SIZING_ACTIONS = frozenset({"downgrade", "cross_family", "upgrade"})


def _recommendation_from_payload(recommendation: dict[str, Any] | None) -> VmSizingRecommendation | None:
    if not recommendation:
        return None
    action = recommendation.get("action")
    if action not in SIZING_ACTIONS:
        return None
    return VmSizingRecommendation(
        action=action,
        current_sku=recommendation.get("current_sku") or "",
        suggested_sku=recommendation.get("suggested_sku") or "",
        current_family=recommendation.get("current_family") or "",
        suggested_family=recommendation.get("suggested_family") or "",
        family_label=recommendation.get("family_label") or "",
        direction=recommendation.get("direction") or "none",
        avg_cpu_pct=recommendation.get("avg_cpu_pct"),
        avg_memory_pct=recommendation.get("avg_memory_pct"),
        confidence=int(recommendation.get("confidence") or 0),
        reasons=list(recommendation.get("reasons") or []),
    )


def _utilization_from_payload(utilization: dict[str, Any] | None) -> VmUtilization:
    payload = utilization or {}
    return VmUtilization(
        avg_cpu_pct=payload.get("avg_cpu_pct"),
        avg_memory_pct=payload.get("avg_memory_pct"),
        avg_available_memory_bytes=payload.get("avg_available_memory_bytes"),
        memory_gb_total=payload.get("memory_gb_total"),
        metrics_window=payload.get("metrics_window"),
        has_cpu=bool(payload.get("has_cpu")),
        has_memory=bool(payload.get("has_memory")),
    )


def build_vm_sizing_finding_dict(
    *,
    subscription_id: str,
    vm: dict,
    recommendation: dict[str, Any],
    utilization: dict[str, Any],
    pricing: dict[str, Any] | None,
    monthly_cost: float = 0.0,
    rule_overrides: dict[str, dict] | None = None,
    vm_metrics: dict[str, dict] | None = None,
) -> dict[str, Any] | None:
    """Build a finding payload from live VM sizing data (same shape as analysis output)."""
    sizing = _recommendation_from_payload(recommendation)
    if not sizing or not sizing.suggested_sku:
        return None

    engine = ExtendedOptimizationEngine(rule_overrides=rule_overrides)
    sizing_rule = engine.rules.get("VM_SKU_SIZING_EXTENDED")
    family_rule = engine.rules.get("VM_RIGHTSIZE_FAMILY")
    if sizing_rule and sizing_rule.enabled:
        active_sizing_rule = sizing_rule
    elif family_rule and family_rule.enabled and sizing.action == "cross_family":
        active_sizing_rule = family_rule
    else:
        return None

    util = _utilization_from_payload(utilization)
    props = vm.get("properties") or {}
    sku = (props.get("hardwareProfile") or {}).get("vmSize") or recommendation.get("current_sku") or ""
    cpu = util.avg_cpu_pct
    mem = util.avg_memory_pct
    vm_eval = merge_vm_utilization_facts(vm, util, vm_metrics=vm_metrics)
    metrics_map = vm_metrics or {}
    rid = (vm.get("id") or "").lower()
    if rid and not metrics_map.get(rid):
        metrics_map = {**metrics_map, rid: {"value": []}}

    finding = emit_vm_sizing_finding(
        engine,
        sizing_rule=active_sizing_rule,
        subscription_id=subscription_id.lower(),
        vm=vm_eval,
        sku=sku,
        sizing=sizing,
        monthly_cost=monthly_cost,
        cpu=cpu,
        mem=mem,
        util=util,
        vm_metrics=metrics_map,
    )
    if not finding:
        return None

    finding_dict = finding.to_dict()
    finding_dict["severity"] = VM_RIGHTSIZING_SEVERITY
    if pricing:
        finding_dict["evidence"] = {**(finding_dict.get("evidence") or {}), **pricing}
        savings = pricing.get("estimated_monthly_savings_usd")
        if savings is not None and pricing.get("pricing_status") == "available":
            finding_dict["estimated_savings_usd"] = round(float(savings), 2)
            finding_dict["annualized_savings_usd"] = round(float(savings) * 12, 2)
    return finding_dict


def _latest_run_id(db: Session, subscription_id: str) -> str:
    run = (
        db.query(OptimizationRun)
        .filter(OptimizationRun.subscription_id == subscription_id.lower())
        .order_by(OptimizationRun.analyzed_at.desc())
        .first()
    )
    if run:
        return run.id
    return f"vm-sizing-{uuid.uuid4()}"


def _find_open_vm_sizing_finding(
    db: Session,
    subscription_id: str,
    resource_id: str,
) -> OptimizationFinding | None:
    rid = normalize_arm_id(resource_id)
    sub = subscription_id.lower()
    from app.analysis_persist import _open_findings_query

    rows = _open_findings_query(db, sub).all()
    for row in rows:
        if normalize_arm_id(row.resource_id or "") != rid:
            continue
        if row.rule_id in RIGHTSIZING_RULE_IDS:
            return row
        try:
            evidence = json.loads(row.evidence_json or "{}")
        except json.JSONDecodeError:
            evidence = {}
        if evidence.get("sizing_action") in SIZING_ACTIONS:
            return row
    return None


def upsert_vm_sizing_open_finding(
    db: Session,
    *,
    subscription_id: str,
    vm: dict,
    recommendation: dict[str, Any],
    utilization: dict[str, Any],
    pricing: dict[str, Any] | None = None,
    monthly_cost: float = 0.0,
    rule_overrides: dict[str, dict] | None = None,
    vm_metrics: dict[str, dict] | None = None,
) -> OptimizationFinding | None:
    """Create or refresh an open VM rightsizing finding from live sizing data."""
    finding_dict = build_vm_sizing_finding_dict(
        subscription_id=subscription_id,
        vm=vm,
        recommendation=recommendation,
        utilization=utilization,
        pricing=pricing,
        monthly_cost=monthly_cost,
        rule_overrides=rule_overrides,
        vm_metrics=vm_metrics,
    )
    if not finding_dict:
        return None

    rid = normalize_arm_id(vm.get("id") or "")
    sub = subscription_id.lower()
    enriched = enrich_evidence(
        finding_dict.get("rule_id") or "",
        finding_dict.get("evidence"),
        finding_dict,
    )
    now = datetime.now(timezone.utc)
    existing = _find_open_vm_sizing_finding(db, sub, rid)

    if existing:
        from app.analysis_persist import _apply_finding_payload

        run_id = existing.run_id or _latest_run_id(db, sub)
        finding_dict["severity"] = VM_RIGHTSIZING_SEVERITY
        _apply_finding_payload(
            existing,
            finding=finding_dict,
            subscription_id=sub,
            run_id=run_id,
            enriched=enriched,
            now=now,
        )
        existing.severity = VM_RIGHTSIZING_SEVERITY
        db.commit()
        db.refresh(existing)
        return existing

    run_id = _latest_run_id(db, sub)
    row = OptimizationFinding(
        id=str(uuid.uuid4()),
        run_id=run_id,
        rule_id=finding_dict["rule_id"],
        rule_name=finding_dict["rule_name"],
        category=finding_dict["category"],
        severity=VM_RIGHTSIZING_SEVERITY,
        resource_id=normalize_arm_id(finding_dict.get("resource_id") or rid),
        resource_name=finding_dict["resource_name"],
        resource_type=finding_dict["resource_type"],
        subscription_id=sub,
        resource_group=finding_dict.get("resource_group") or "",
        location=finding_dict.get("location") or "",
        detail=finding_dict["detail"],
        recommendation=finding_dict["recommendation"],
        estimated_savings_usd=finding_dict.get("estimated_savings_usd") or 0,
        annualized_savings_usd=finding_dict.get("annualized_savings_usd") or 0,
        waste_score=finding_dict.get("waste_score") or 0,
        confidence_score=finding_dict.get("confidence_score") or 0,
        action_priority=finding_dict.get("action_priority"),
        impact=finding_dict.get("impact"),
        evidence_json=json.dumps(enriched or {}),
        status="open",
        detected_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def compute_vm_sizing_recommendation(
    *,
    vm: dict,
    catalog: list[dict],
    metrics: dict | None,
    timespan: str = "P7D",
    rule_overrides: dict[str, dict] | None = None,
    monthly_cost: float | None = None,
) -> tuple[VmUtilization, VmSizingRecommendation | None, dict[str, Any] | None]:
    """Shared sizing logic for GET sizing and open-finding persistence."""
    from app.azure_retail_pricing import estimate_vm_sku_savings, vm_os_type
    from app.cost_utils import normalize_monthly_cost_usd
    from app.vm_sizing import extract_vm_utilization, parse_vm_sku

    monthly_cost = normalize_monthly_cost_usd(monthly_cost)

    props = vm.get("properties") or {}
    sku = (props.get("hardwareProfile") or {}).get("vmSize") or ""
    location = vm.get("location") or ""
    catalog_entry = next((row for row in catalog if row.get("name") == sku), None)
    parsed = parse_vm_sku(sku, catalog_entry=catalog_entry)

    util = extract_vm_utilization(metrics, sku=sku, catalog_entry=catalog_entry, timespan=timespan)
    if not sku:
        return util, None, None

    engine = ExtendedOptimizationEngine(rule_overrides=rule_overrides)
    sizing_rule = engine.rules.get("VM_SKU_SIZING_EXTENDED")
    if sizing_rule and sizing_rule.enabled:
        recommendation = recommend_vm_sku(
            current_sku=sku,
            utilization=util,
            catalog=catalog,
            cpu_down_pct=sizing_rule.cpu_idle_pct,
            cpu_up_pct=sizing_rule.cpu_oversize_pct,
            memory_down_pct=sizing_rule.memory_idle_pct,
            memory_up_pct=85.0,
        )
    else:
        recommendation = recommend_vm_sku(current_sku=sku, utilization=util, catalog=catalog)

    pricing = None
    if recommendation and recommendation.suggested_sku and recommendation.action in SIZING_ACTIONS:
        run_rate = project_mtd_to_monthly_run_rate(monthly_cost) if monthly_cost else None
        pricing = estimate_vm_sku_savings(
            location,
            sku,
            recommendation.suggested_sku,
            os_type=vm_os_type(vm),
            actual_monthly_cost=monthly_cost,
            monthly_run_rate_usd=run_rate,
        )

    return util, recommendation, pricing


def _finding_evidence(finding: dict[str, Any]) -> dict[str, Any]:
    evidence = finding.get("evidence")
    return evidence if isinstance(evidence, dict) else {}


def is_vm_rightsizing_finding(finding: dict[str, Any]) -> bool:
    if finding.get("rule_id") in VM_RIGHTSIZING_RULE_IDS:
        return True
    return _finding_evidence(finding).get("sizing_action") in SIZING_ACTIONS


def _is_underutilized_sizing_duplicate(finding: dict[str, Any]) -> bool:
    return (
        finding.get("rule_id") == "VM_UNDERUTILIZED_EXTENDED"
        and _finding_evidence(finding).get("sizing_action") in SIZING_ACTIONS
    )


def normalize_vm_rightsizing_finding_dict(finding: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(finding)
    if is_vm_rightsizing_finding(normalized):
        normalized["severity"] = VM_RIGHTSIZING_SEVERITY
    return normalized


def supplement_vm_rightsizing_findings(
    findings: list[dict[str, Any]],
    *,
    subscription_id: str,
    vms: list[dict],
    vm_metrics: dict[str, dict],
    cost_by_resource: dict[str, float],
    rule_overrides: dict[str, dict] | None = None,
) -> list[dict[str, Any]]:
    """Ensure every VM with a sizing recommendation has an open MEDIUM rightsizing finding."""
    cleaned = [
        normalize_vm_rightsizing_finding_dict(f)
        for f in findings
        if not _is_underutilized_sizing_duplicate(f)
    ]
    rightsized_rids = {
        normalize_arm_id(f.get("resource_id") or "")
        for f in cleaned
        if is_vm_rightsizing_finding(f)
    }

    engine = ExtendedOptimizationEngine(rule_overrides=rule_overrides)
    sizing_rule = engine.rules.get("VM_SKU_SIZING_EXTENDED")
    family_rule = engine.rules.get("VM_RIGHTSIZE_FAMILY")
    if not ((sizing_rule and sizing_rule.enabled) or (family_rule and family_rule.enabled)):
        return cleaned

    extra: list[dict[str, Any]] = []
    for vm in vms:
        rid = normalize_arm_id(vm.get("id") or "")
        if not rid or rid in rightsized_rids:
            continue
        props = vm.get("properties") or {}
        sku = (props.get("hardwareProfile") or {}).get("vmSize") or ""
        loc = vm.get("location") or ""
        if not sku or not loc:
            continue
        util = vm_utilization(engine, vm, vm_metrics)
        if not vm_sizing_metrics_ok(vm, util, vm_metrics):
            continue
        vm_eval = merge_vm_utilization_facts(vm, util, vm_metrics=vm_metrics)
        catalog = vm_catalog(engine, subscription_id, loc)
        cpu = util.avg_cpu_pct
        mem = util.avg_memory_pct
        monthly_cost = resource_cost(cost_by_resource, rid)

        sizing = None
        active_rule = None
        if sizing_rule and sizing_rule.enabled:
            sizing = recommend_vm_sku(
                current_sku=sku,
                utilization=util,
                catalog=catalog,
                cpu_down_pct=sizing_rule.cpu_idle_pct,
                cpu_up_pct=sizing_rule.cpu_oversize_pct,
                memory_down_pct=sizing_rule.memory_idle_pct,
                memory_up_pct=85.0,
            )
            active_rule = sizing_rule
        elif family_rule and family_rule.enabled:
            sizing = recommend_vm_sku(
                current_sku=sku,
                utilization=util,
                catalog=catalog,
                cpu_down_pct=family_rule.cpu_oversize_pct,
                cpu_up_pct=75.0,
                memory_down_pct=30.0,
            )
            active_rule = family_rule

        if not sizing or not active_rule:
            continue
        finding = emit_vm_sizing_finding(
            engine,
            sizing_rule=active_rule,
            subscription_id=subscription_id.lower(),
            vm=vm_eval,
            sku=sku,
            sizing=sizing,
            monthly_cost=monthly_cost,
            cpu=cpu,
            mem=mem,
            util=util,
            vm_metrics=vm_metrics,
        )
        if not finding:
            continue
        extra.append(normalize_vm_rightsizing_finding_dict(finding.to_dict()))
        rightsized_rids.add(rid)

    if not extra:
        return cleaned
    return cleaned + extra

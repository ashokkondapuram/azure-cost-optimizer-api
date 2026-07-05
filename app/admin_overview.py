"""Admin optimization overview — per-component usage, waste, and savings."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import EngineConfig, OptimizationFinding, OptimizationRun, ResourceSnapshot
from app.optimizer.component_map import (
    CANONICAL_TO_COMPONENT,
    COMPONENT_RESOURCE_TYPES,
    IDLE_STATE_PATTERNS,
    WASTE_STATE_PATTERNS,
)
from app.optimizer.rule_catalog import RULE_MANIFEST, list_all_rules
from app.analysis_cooldown import full_analysis_cooldown_status


def _is_idle_state(state: str | None, *, waste_only: bool = False) -> bool:
    if not state:
        return False
    lower = state.lower()
    patterns = WASTE_STATE_PATTERNS if waste_only else IDLE_STATE_PATTERNS
    return any(pat in lower for pat in patterns)


def _enabled_rules_for_component(db: Session, profile: str, component: str) -> tuple[int, int]:
    """Return (enabled_count, total_count) for rules mapped to this component."""
    rule_ids = [rid for rid, meta in RULE_MANIFEST.items() if meta.get("component") == component]
    if not rule_ids:
        return 0, 0

    rows = (
        db.query(EngineConfig)
        .filter(EngineConfig.profile == profile, EngineConfig.rule_id.in_(rule_ids))
        .all()
    )
    overrides = {r.rule_id: r.enabled for r in rows}
    enabled = 0
    for rid in rule_ids:
        if overrides.get(rid, True):
            enabled += 1
    return enabled, len(rule_ids)


def build_optimization_overview(
    db: Session,
    *,
    subscription_id: str,
    profile: str = "default",
) -> dict[str, Any]:
    sub = subscription_id.lower()

    # Resource rows grouped by canonical type
    resource_rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
        )
        .all()
    )

    by_type: dict[str, list] = {}
    for row in resource_rows:
        by_type.setdefault(row.resource_type, []).append(row)

    # Open findings grouped by component
    findings = (
        db.query(OptimizationFinding)
        .filter(
            OptimizationFinding.subscription_id == sub,
            OptimizationFinding.status == "open",
        )
        .all()
    )
    findings_by_component: dict[str, list] = {}
    for f in findings:
        comp = RULE_MANIFEST.get(f.rule_id or "", {}).get("component")
        if not comp:
            comp = CANONICAL_TO_COMPONENT.get(f.resource_type or "", "Other")
        findings_by_component.setdefault(comp, []).append(f)

    last_run = (
        db.query(OptimizationRun)
        .filter(OptimizationRun.subscription_id == sub)
        .order_by(OptimizationRun.analyzed_at.desc())
        .first()
    )
    last_analyzed = last_run.analyzed_at.isoformat() if last_run and last_run.analyzed_at else None

    all_rules = list_all_rules()
    rules_by_component: dict[str, list] = {}
    for rule in all_rules:
        rules_by_component.setdefault(rule["component"], []).append(rule)

    components: list[dict[str, Any]] = []
    totals = {
        "resource_count": 0,
        "idle_count": 0,
        "mtd_cost": 0.0,
        "open_findings": 0,
        "estimated_savings_usd": 0.0,
        "enabled_rules": 0,
        "total_rules": 0,
    }

    for component, canonical_types in COMPONENT_RESOURCE_TYPES.items():
        resources: list[ResourceSnapshot] = []
        for ct in canonical_types:
            resources.extend(by_type.get(ct, []))

        resource_count = len(resources)
        idle_count = sum(1 for r in resources if _is_idle_state(r.state, waste_only=True))
        mtd_cost = round(sum(r.monthly_cost_usd or 0 for r in resources), 2)

        comp_findings = findings_by_component.get(component, [])
        open_findings = len(comp_findings)
        savings = round(sum(f.estimated_savings_usd or 0 for f in comp_findings), 2)

        snapshot_findings = sum((r.analysis_findings_count or 0) for r in resources)
        snapshot_savings = round(sum((r.analysis_savings_usd or 0) for r in resources), 2)
        if open_findings == 0 and snapshot_findings > 0:
            open_findings = snapshot_findings
            savings = snapshot_savings

        enabled_rules, total_rules = _enabled_rules_for_component(db, profile, component)
        comp_rules = rules_by_component.get(component, [])

        with_analysis = sum(1 for r in resources if (r.analysis_findings_count or 0) > 0)

        components.append({
            "component": component,
            "resource_types": canonical_types,
            "resource_count": resource_count,
            "idle_or_unused_count": idle_count,
            "analyzed_resource_count": with_analysis,
            "mtd_cost": mtd_cost,
            "open_findings": open_findings,
            "estimated_savings_usd": savings,
            "enabled_rules": enabled_rules,
            "total_rules": total_rules,
            "rules": comp_rules,
            "top_findings": [
                {
                    "rule_id": f.rule_id,
                    "rule_name": f.rule_name,
                    "severity": f.severity,
                    "resource_name": f.resource_name,
                    "estimated_savings_usd": f.estimated_savings_usd,
                }
                for f in sorted(
                    comp_findings,
                    key=lambda x: (-(x.estimated_savings_usd or 0), x.severity or ""),
                )[:5]
            ],
        })

        totals["resource_count"] += resource_count
        totals["idle_count"] += idle_count
        totals["mtd_cost"] += mtd_cost
        totals["open_findings"] += open_findings
        totals["estimated_savings_usd"] += savings
        totals["enabled_rules"] += enabled_rules
        totals["total_rules"] += total_rules

    totals["mtd_cost"] = round(totals["mtd_cost"], 2)
    totals["estimated_savings_usd"] = round(totals["estimated_savings_usd"], 2)

    return {
        "subscription_id": sub,
        "profile": profile,
        "last_analyzed_at": last_analyzed,
        "last_run_id": last_run.id if last_run else None,
        "full_analysis": full_analysis_cooldown_status(db, sub),
        "totals": totals,
        "components": components,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

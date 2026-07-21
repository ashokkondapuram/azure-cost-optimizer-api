#!/usr/bin/env python3
"""Inject regionGovernance and pillarTriggers blocks into assessment JSON files."""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

REGION_BLOCK = {
    "policyFile": "region-governance-policy.json",
    "primaryApprovedRegion": "canadacentral",
    "secondaryApprovedRegion": "canadaeast",
    "approvedRegions": ["canadacentral", "canadaeast"],
    "conditionalRegions": [],
    "blockedRegions": [],
    "recommendedTargetRegion": "canadacentral",
    "unclassifiedBehavior": "flag_for_review",
}

PILLAR_BLOCK = {
    "policyFile": "assessment-pillar-triggers.json",
    "version": 1,
}


def _service_prefix(message: str) -> str:
    match = re.match(r"^(.+? Optimization:)", message)
    return match.group(1) if match else "Resource Optimization:"


def _region_message(prefix: str) -> dict[str, str]:
    lead = prefix if prefix.endswith(":") else f"{prefix}:"
    text = (
        f"{lead} Resource is in an unapproved or unclassified region. "
        "Move to Canada Central (canadacentral) or Canada East (canadaeast) "
        "for approved data residency, latency, and policy alignment."
    )
    short = (
        f"{lead} Move to Canada Central (canadacentral) or Canada East (canadaeast) "
        "for approved data residency."
    )
    return {
        "message": text,
        "shortMessage": short,
        "recommendedActionText": text,
    }


def _what_if_region(rule_id: str, prefix: str, resource_type: str | None) -> dict:
    lead = prefix if prefix.endswith(":") else f"{prefix}:"
    return {
        "ruleId": rule_id,
        "action": "investigate",
        "title": "Plan migration to approved Canada region",
        "summary": (
            f"{lead} Recreate or migrate the resource in Canada Central (canadacentral) "
            "or Canada East (canadaeast). Validate latency, data residency, and DR pairing."
        ),
        "currentState": {
            "description": "Resource runs in an unapproved or unclassified Azure region.",
            "costField": "cost.monthlyActualCost",
            "regionField": "signals.currentRegion",
        },
        "proposedState": {
            "description": (
                "Deploy equivalent workload in canadacentral (primary) or canadaeast (DR). "
                "Service Bus namespaces require recreation — update connection strings and cut over."
            ),
            "costField": "cost.monthlyActualCost",
            "regionField": "signals.recommendedRegion",
        },
        "risk": "medium",
        "reversible": False,
        "blastRadius": "Regional migration; may require dual-run cutover",
        "prerequisites": [
            "Confirm organizational region policy with platform team",
            "Validate paired-region DR requirements",
            "Plan connection string and DNS updates for dependents",
        ],
        "costImpact": {
            "savingsBasis": "unknown",
            "savingsPercent": 0,
            "description": "Cost may change by region; prioritize compliance and latency over savings.",
        },
        "performanceImpact": {
            "before": "Latency and throughput depend on current region placement.",
            "after": "Latency aligns with Canada-based consumers after migration.",
            "direction": "improved",
        },
        "reliabilityImpact": {
            "before": "May be outside approved DR and residency boundary.",
            "after": "Aligns with Canada Central / Canada East pairing for DR.",
            "direction": "improved",
        },
        **({"resourceType": resource_type} if resource_type else {}),
    }


def _patch_rule(rule: dict, prefix: str) -> bool:
    if rule.get("id") != "best_unapproved_region":
        return False
    output = rule.setdefault("output", {})
    msgs = _region_message(prefix)
    changed = False
    for key, val in msgs.items():
        if output.get(key) != val:
            output[key] = val
            changed = True
    if output.get("action") == "upgrade":
        output["action"] = "investigate"
        output["recommendationAction"] = "investigate"
        output["actionOutcome"] = "investigate"
        rule["recommendationAction"] = "investigate"
        rule["actionOutcome"] = "investigate"
        changed = True
    return changed


def patch_assessment(data: dict) -> tuple[bool, list[str]]:
    changes: list[str] = []
    resource_type = data.get("resourceType")
    assessment_name = data.get("assessmentName") or "Resource Optimization"
    prefix = assessment_name if assessment_name.endswith("Optimization") else f"{assessment_name} Optimization"

    if data.get("regionGovernance") != REGION_BLOCK:
        data["regionGovernance"] = dict(REGION_BLOCK)
        changes.append("regionGovernance")

    pillar = dict(PILLAR_BLOCK)
    if resource_type:
        pillar["resourceType"] = resource_type
    if data.get("pillarTriggers") != pillar:
        data["pillarTriggers"] = pillar
        changes.append("pillarTriggers")

    rule_sections = (
        "recommendationRules",
        "assessmentRules",
        "metricAssessmentRules",
        "propertyAssessmentRules",
        "bestOptimizationRules",
        "actionOutcomeRules",
    )
    for section in rule_sections:
        for rule in data.get(section) or []:
            if _patch_rule(rule, prefix):
                changes.append(f"{section}:best_unapproved_region")

    what_if = data.setdefault("whatIfScenarios", {})
    scenario = _what_if_region("best_unapproved_region", prefix, resource_type)
    if what_if.get("best_unapproved_region") != scenario:
        what_if["best_unapproved_region"] = scenario
        changes.append("whatIfScenarios:best_unapproved_region")

    return bool(changes), changes


def main() -> int:
    updated = 0
    errors = 0
    for path in sorted(DATA.glob("*-assessment.json")):
        if path.name == "assessment-case-matrix.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            changed, detail = patch_assessment(data)
            if changed:
                path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                updated += 1
                print(f"patched {path.name}: {', '.join(detail)}")
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"ERROR {path.name}: {exc}", file=sys.stderr)
    print(f"done: {updated} files patched, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

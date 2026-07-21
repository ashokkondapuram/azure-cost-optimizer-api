"""What-if scenario modeling for assessment recommendation actions."""

from __future__ import annotations

from typing import Any

ACTION_TEMPLATES: dict[str, dict[str, Any]] = {
    "stop_or_delete": {
        "risk": "medium",
        "reversible": False,
        "blastRadius": "Target resource only",
        "prerequisites": [
            "Confirm no active dependencies",
            "Verify backup or retention requirements",
            "Notify resource owner before change",
        ],
        "costImpact": {
            "savingsBasis": "monthly_cost",
            "savingsPercent": 100,
            "description": "Remove recurring cost for the resource after deletion or stop.",
        },
        "performanceImpact": {
            "before": "Workload runs on the current resource with existing capacity.",
            "after": "Workload stops when the resource is deallocated or deleted.",
            "direction": "degraded",
        },
        "reliabilityImpact": {
            "before": "Availability follows the current resource uptime and SLA.",
            "after": "Service is unavailable until the resource is restored or replaced.",
            "direction": "degraded",
        },
    },
    "downgrade": {
        "risk": "low",
        "reversible": True,
        "blastRadius": "Performance or SKU tier on target resource",
        "prerequisites": [
            "Validate workload still meets SLA after downgrade",
            "Review metrics for peak utilization",
        ],
        "costImpact": {
            "savingsBasis": "sku_delta",
            "savingsPercent": 25,
            "description": "Reduce SKU, tier, or capacity to lower monthly spend.",
        },
        "performanceImpact": {
            "before": "Current SKU or tier supports the observed utilization profile.",
            "after": "Lower tier reduces headroom during peak CPU, memory, or I/O.",
            "direction": "at_risk",
        },
        "reliabilityImpact": {
            "before": "Meets SLA at present utilization with current capacity.",
            "after": "SLA margin narrows if peaks exceed the reduced capacity.",
            "direction": "at_risk",
        },
    },
    "upgrade": {
        "risk": "low",
        "reversible": True,
        "blastRadius": "Target resource capacity",
        "prerequisites": [
            "Confirm upgrade resolves the detected bottleneck",
            "Budget for increased monthly cost if applicable",
        ],
        "costImpact": {
            "savingsBasis": "none",
            "savingsPercent": 0,
            "description": "Increase capacity or tier; may raise cost but improve reliability.",
        },
        "performanceImpact": {
            "before": "Capacity may be constrained at the current tier or SKU.",
            "after": "Higher tier improves throughput and performance headroom.",
            "direction": "improved",
        },
        "reliabilityImpact": {
            "before": "May not meet SLA under sustained or peak load.",
            "after": "Improved resilience and availability margin for the workload.",
            "direction": "improved",
        },
    },
    "investigate": {
        "risk": "low",
        "reversible": True,
        "blastRadius": "None until a change is approved",
        "prerequisites": [
            "Review evidence and owner context",
            "Run deeper analysis before executing a change",
        ],
        "costImpact": {
            "savingsBasis": "unknown",
            "savingsPercent": 0,
            "description": "Potential savings depend on investigation outcome.",
        },
        "performanceImpact": {
            "before": "Current performance profile from live metrics and assessment.",
            "after": "Outcome depends on investigation — no change until validated.",
            "direction": "unchanged",
        },
        "reliabilityImpact": {
            "before": "Current reliability posture from uptime and dependency signals.",
            "after": "Outcome depends on investigation — no change until validated.",
            "direction": "unchanged",
        },
    },
    "stay": {
        "risk": "low",
        "reversible": True,
        "blastRadius": "None",
        "prerequisites": ["No change required"],
        "costImpact": {
            "savingsBasis": "none",
            "savingsPercent": 0,
            "description": "Current configuration is appropriate.",
        },
        "performanceImpact": {
            "before": "Workload performance remains within acceptable bounds.",
            "after": "No configuration change; continue monitoring utilization.",
            "direction": "unchanged",
        },
        "reliabilityImpact": {
            "before": "Current configuration meets reliability requirements.",
            "after": "No change; maintain existing SLA and redundancy posture.",
            "direction": "unchanged",
        },
    },
    "migrate_region": {
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
            "after": "Latency aligns with approved region consumers after migration.",
            "direction": "improved",
        },
        "reliabilityImpact": {
            "before": "May be outside approved DR and residency boundary.",
            "after": "Aligns with approved regional pairing for disaster recovery.",
            "direction": "improved",
        },
    },
}


def rule_action(rule: dict[str, Any]) -> str | None:
    output = rule.get("output") or {}
    rid = str(rule.get("id") or "")
    if "unapproved_region" in rid or rid.endswith("_region_migration"):
        return "migrate_region"
    return (
        rule.get("recommendationAction")
        or rule.get("actionOutcome")
        or output.get("recommendationAction")
        or output.get("action")
    )


def build_what_if_scenario(rule: dict[str, Any], *, resource_type: str | None = None) -> dict[str, Any]:
    """Build a what-if scenario block for a matched recommendation rule."""
    action = rule_action(rule) or "investigate"
    template = dict(ACTION_TEMPLATES.get(action, ACTION_TEMPLATES["investigate"]))
    output = rule.get("output") or {}
    recommendation = (
        rule.get("recommendation")
        or output.get("recommendedActionText")
        or output.get("shortMessage")
        or output.get("message")
        or ""
    )
    title = rule.get("id") or "recommended_change"
    title_text = recommendation.split(".")[0].strip() if recommendation else title.replace("_", " ").title()

    scenario = {
        "ruleId": rule.get("id"),
        "action": action,
        "title": title_text[:120],
        "summary": recommendation,
        "currentState": {
            "description": "Resource remains in its current configuration and cost profile.",
            "costField": "cost.monthlyActualCost",
        },
        "proposedState": {
            "description": _proposed_state_description(action, recommendation),
            "costField": "cost.monthlyActualCost",
        },
        "risk": template["risk"],
        "reversible": template["reversible"],
        "blastRadius": template["blastRadius"],
        "prerequisites": list(template["prerequisites"]),
        "costImpact": dict(template["costImpact"]),
        "performanceImpact": dict(template.get("performanceImpact") or {}),
        "reliabilityImpact": dict(template.get("reliabilityImpact") or {}),
    }
    if resource_type:
        scenario["resourceType"] = resource_type
    applies = rule.get("appliesToResourceTypes")
    if applies:
        scenario["appliesToResourceTypes"] = list(applies)
    return scenario


def _proposed_state_description(action: str, recommendation: str) -> str:
    if action == "stop_or_delete":
        return "Resource is stopped, deleted, or expired after validation."
    if action == "downgrade":
        return "Resource SKU, tier, or capacity is reduced to a lower-cost option."
    if action == "upgrade":
        return "Resource SKU, tier, or capacity is increased to meet workload needs."
    if action == "migrate_region":
        return "Resource is recreated or migrated to the approved target region after validation."
    if action == "stay":
        return "No configuration change; continue monitoring."
    return recommendation or "Investigate and validate before applying a change."


def _personalize_scenario(
    scenario: dict[str, Any],
    *,
    resource: dict[str, Any] | None = None,
    rule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fill region/SKU placeholders using normalized record signals."""
    if not resource:
        return scenario

    signals = resource.get("signals") or {}
    rid = str((rule or {}).get("id") or scenario.get("ruleId") or "")
    current = dict(scenario.get("currentState") or {})
    proposed = dict(scenario.get("proposedState") or {})
    target_region = None
    target_display = None

    if "region" in rid or current.get("regionField") or proposed.get("regionField"):
        current_region = signals.get("currentRegion") or resource.get("location")
        target_region = signals.get("recommendedRegion")
        target_display = signals.get("recommendedRegionDisplay") or target_region
        if current_region:
            current.setdefault("region", current_region)
        if target_region:
            proposed.setdefault("region", target_region)
            proposed["description"] = (
                f"Deploy equivalent workload in {target_display or target_region}. "
                + str(proposed.get("description") or "")
            ).strip()

    scenario = dict(scenario)
    scenario["currentState"] = current
    scenario["proposedState"] = proposed
    if target_region:
        scenario["recommendedTargetRegion"] = target_region
    if target_display:
        scenario["recommendedTargetRegionDisplay"] = target_display
    return scenario


def _merge_template_impacts(scenario: dict[str, Any]) -> dict[str, Any]:
    """Backfill performance/reliability impact blocks from action template."""
    action = scenario.get("action") or "investigate"
    template = ACTION_TEMPLATES.get(action, ACTION_TEMPLATES["investigate"])
    for key in ("performanceImpact", "reliabilityImpact"):
        if not scenario.get(key) and template.get(key):
            scenario[key] = dict(template[key])
    return scenario


def lookup_what_if_scenario(
    assessment: dict[str, Any],
    rule_id: str | None,
    *,
    rule: dict[str, Any] | None = None,
    resource: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return explicit what-if from assessment JSON, or build from the rule."""
    if not rule_id and not rule:
        return None
    scenarios = assessment.get("whatIfScenarios") or {}
    if rule_id and rule_id in scenarios:
        scenario = _merge_template_impacts(dict(scenarios[rule_id]))
    elif rule:
        scenario = build_what_if_scenario(rule, resource_type=assessment.get("resourceType"))
    else:
        return None
    return _personalize_scenario(scenario, resource=resource, rule=rule)


def enrich_finding_with_what_if(
    finding: dict[str, Any],
    assessment: dict[str, Any],
    rule: dict[str, Any],
    *,
    resource: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach what-if scenario to finding evidence."""
    rule_id = str(rule.get("id") or finding.get("rule_id") or "")
    scenario = lookup_what_if_scenario(assessment, rule_id, rule=rule, resource=resource)
    if not scenario:
        return finding
    evidence = dict(finding.get("evidence") or {})
    evidence["what_if"] = scenario
    finding = dict(finding)
    finding["evidence"] = evidence
    return finding


def build_what_if_index(assessment: dict[str, Any]) -> dict[str, Any]:
    """Generate whatIfScenarios map from recommendation and best-optimization rules."""
    out: dict[str, Any] = {}
    primary = assessment.get("resourceType")
    rule_lists = (
        assessment.get("recommendationRules") or [],
        assessment.get("bestOptimizationRules") or [],
        assessment.get("assessmentRules") or [],
    )
    for rules in rule_lists:
        for rule in rules:
            rule_id = rule.get("id")
            if not rule_id or rule_id in out:
                continue
            applies = rule.get("appliesToResourceTypes") or [primary]
            out[rule_id] = build_what_if_scenario(rule, resource_type=applies[0] if len(applies) == 1 else primary)
            if rule.get("appliesToResourceTypes"):
                out[rule_id]["appliesToResourceTypes"] = list(rule["appliesToResourceTypes"])
    return out

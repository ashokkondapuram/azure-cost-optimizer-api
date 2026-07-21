"""Deduplicate subscription vs per-VM commitment (RI / Savings Plan) findings."""
from __future__ import annotations

from typing import Any

SUBSCRIPTION_COMMITMENT_RULE_IDS = frozenset({
    "RESERVED_OPPORTUNITY_EXTENDED",
    "SAVINGS_PLAN_OPPORTUNITY_EXTENDED",
    "RESERVED_OPPORTUNITY",
    "SAVINGS_PLAN_OPPORTUNITY",
})

PER_VM_COMMITMENT_RULE_IDS = frozenset({
    "VM_COMMITMENT_CANDIDATE",
    "VM_NO_RESERVED",
})

COMBINED_COMMITMENT_RULE_ID = "SAVINGS_PLAN_OPPORTUNITY_EXTENDED"


def _evidence(finding: dict[str, Any]) -> dict[str, Any]:
    evidence = finding.get("evidence")
    return evidence if isinstance(evidence, dict) else {}


def _is_subscription_commitment(finding: dict[str, Any]) -> bool:
    if finding.get("rule_id") in SUBSCRIPTION_COMMITMENT_RULE_IDS:
        return True
    return _evidence(finding).get("scope") == "subscription"


def _merge_subscription_commitment_pair(
    ri_finding: dict[str, Any],
    sp_finding: dict[str, Any],
) -> dict[str, Any]:
    """Merge separate RI and Savings Plan subscription findings into one."""
    ri_ev = _evidence(ri_finding)
    sp_ev = _evidence(sp_finding)
    ri_savings = float(ri_finding.get("estimated_savings_usd") or 0)
    sp_savings = float(sp_finding.get("estimated_savings_usd") or 0)
    total_vm_spend = ri_ev.get("total_vm_monthly_spend_usd") or sp_ev.get("estimated_compute_spend_usd")
    running_count = ri_ev.get("running_vm_count") or sp_ev.get("running_vm_count")
    spend_text = f"${float(total_vm_spend):,.2f}/month" if total_vm_spend else "sustained on-demand spend"
    vm_text = f" across {running_count} running VMs" if running_count else ""

    merged = dict(sp_finding)
    merged["rule_id"] = COMBINED_COMMITMENT_RULE_ID
    merged["rule_name"] = sp_finding.get("rule_name") or "Savings Plan Opportunity"
    merged["detail"] = (
        f"Subscription has {spend_text} on-demand VM spend{vm_text} — "
        "review Reserved Instances and Azure Savings Plans together."
    )
    merged["recommendation"] = (
        "Compare 1-year and 3-year Reserved Instances with Azure Savings Plan coverage "
        "for always-on compute. Pick one commitment model per workload shape."
    )
    merged["estimated_savings_usd"] = round(max(ri_savings, sp_savings), 2)
    merged["annualized_savings_usd"] = round(merged["estimated_savings_usd"] * 12, 2)
    merged["evidence"] = {
        **sp_ev,
        **ri_ev,
        "scope": "subscription",
        "commitment_options": ["reserved_instance", "savings_plan"],
        "reserved_instance_estimated_savings_usd": ri_savings,
        "savings_plan_estimated_savings_usd": sp_savings,
    }
    return merged


def dedupe_commitment_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Remove repetitive commitment guidance:
    - Drop per-VM RI/Savings Plan candidates when subscription-level findings exist.
    - Collapse duplicate subscription RI + Savings Plan findings into one.
    """
    if not findings:
        return findings

    subscription_commitments = [f for f in findings if _is_subscription_commitment(f)]
    if not subscription_commitments:
        return findings

    filtered = [
        f for f in findings
        if f.get("rule_id") not in PER_VM_COMMITMENT_RULE_IDS
    ]

    ri = next(
        (
            f for f in filtered
            if f.get("rule_id") in {"RESERVED_OPPORTUNITY_EXTENDED", "RESERVED_OPPORTUNITY"}
        ),
        None,
    )
    sp = next(
        (
            f for f in filtered
            if f.get("rule_id") in {"SAVINGS_PLAN_OPPORTUNITY_EXTENDED", "SAVINGS_PLAN_OPPORTUNITY"}
        ),
        None,
    )
    if ri and sp:
        pair_rule_ids = {
            "RESERVED_OPPORTUNITY_EXTENDED",
            "RESERVED_OPPORTUNITY",
            "SAVINGS_PLAN_OPPORTUNITY_EXTENDED",
            "SAVINGS_PLAN_OPPORTUNITY",
        }
        without_pair = [f for f in filtered if f.get("rule_id") not in pair_rule_ids]
        return without_pair + [_merge_subscription_commitment_pair(ri, sp)]

    return filtered

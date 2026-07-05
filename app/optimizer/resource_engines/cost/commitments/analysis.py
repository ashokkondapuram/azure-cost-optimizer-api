"""Commitments optimization analysis rules."""
from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from app.resource_pricing import (
    RESERVED_INSTANCE_DISCOUNTS,
    SAVINGS_PLAN_DISCOUNTS,
    compare_commitment_options,
)
from app.vm_uptime import vm_is_running


def _aggregate_vm_spend(
    vms: list[dict],
    cost_by_resource: dict[str, float],
) -> tuple[float, dict[str, float], int]:
    """Return total on-demand spend, spend by SKU, and running VM count."""
    total = 0.0
    by_sku: dict[str, float] = defaultdict(float)
    running_count = 0
    for vm in vms:
        rid = (vm.get("id") or "").lower()
        props = vm.get("properties") or {}
        power = ""
        iv = props.get("instanceView", {})
        for s in iv.get("statuses") or []:
            code = str(s.get("code") or "")
            if code.startswith("PowerState/"):
                power = code.replace("PowerState/", "")
        if not vm_is_running(vm, power_state=power):
            continue
        monthly = resource_cost(cost_by_resource, rid)
        if monthly <= 0:
            continue
        running_count += 1
        total += monthly
        sku = ((props.get("hardwareProfile") or {}).get("vmSize")) or "unknown"
        by_sku[sku] += monthly
    return total, dict(by_sku), running_count


def _is_stable_workload(resource_id: str, daily_cost_history: list[float]) -> bool:
    """Require 28 days of non-declining spend before RI eligibility."""
    if len(daily_cost_history) < 28:
        return False
    n = len(daily_cost_history)
    xs = list(range(n))
    ys = daily_cost_history
    x_mean = mean(xs)
    y_mean = mean(ys)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs) or 1.0
    slope = num / den
    return slope >= 0


def subscription_commitment_eligible(
    engine,
    vms: list[dict],
    cost_by_resource: dict[str, float],
    subscription_spend_usd: float = 0.0,
    *,
    resource_cost_histories: dict[str, list[float]] | None = None,
) -> bool:
    """True when subscription-level RI or Savings Plan rules would fire."""
    if not vms:
        return False
    total_vm_spend, _, running_count = _aggregate_vm_spend(vms, cost_by_resource)
    if running_count == 0:
        return False
    histories = resource_cost_histories or {}
    stable_vms = 0
    for vm in vms:
        rid = (vm.get("id") or "").lower()
        if _is_stable_workload(rid, histories.get(rid, [])):
            stable_vms += 1
    if stable_vms == 0 and histories:
        return False
    ri_rule = engine.rules.get("RESERVED_OPPORTUNITY_EXTENDED")
    sp_rule = engine.rules.get("SAVINGS_PLAN_OPPORTUNITY_EXTENDED")
    ri_ok = bool(
        ri_rule
        and ri_rule.enabled
        and total_vm_spend >= ri_rule.min_monthly_savings_usd
    )
    compute_spend = max(total_vm_spend, subscription_spend_usd * 0.4)
    sp_ok = bool(
        sp_rule
        and sp_rule.enabled
        and compute_spend >= sp_rule.savings_plan_min_monthly_usd
    )
    return ri_ok or sp_ok


def analyze_commitments(
    engine,
    subscription_id: str,
    vms: list[dict],
    cost_by_resource: dict[str, float],
    subscription_spend_usd: float,
    *,
    resource_cost_histories: dict[str, list[float]] | None = None,
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    ri_rule = engine.rules.get("RESERVED_OPPORTUNITY_EXTENDED")
    sp_rule = engine.rules.get("SAVINGS_PLAN_OPPORTUNITY_EXTENDED")
    if not vms:
        return out

    total_vm_spend, by_sku, running_count = _aggregate_vm_spend(vms, cost_by_resource)
    if running_count == 0:
        return out

    histories = resource_cost_histories or {}
    stable_count = sum(
        1 for vm in vms
        if _is_stable_workload((vm.get("id") or "").lower(), histories.get((vm.get("id") or "").lower(), []))
    )
    if histories and stable_count == 0:
        return out

    top_vm = max(vms, key=lambda v: resource_cost(cost_by_resource, (v.get("id") or "").lower())) if vms else None
    anchor = top_vm or (vms[0] if vms else {})
    top_skus = sorted(by_sku.items(), key=lambda x: -x[1])[:5]
    top_sku = top_skus[0][0] if top_skus else ""
    comparison = compare_commitment_options(total_vm_spend, top_sku)

    ri_eligible = bool(
        ri_rule and ri_rule.enabled and total_vm_spend >= ri_rule.min_monthly_savings_usd
    )
    compute_spend = max(total_vm_spend, subscription_spend_usd * 0.4)
    sp_eligible = bool(
        sp_rule and sp_rule.enabled and compute_spend >= sp_rule.savings_plan_min_monthly_usd
    )

    comparison_text = (
        f"Best option: {comparison['best_option']} "
        f"(~${comparison['best_monthly_savings_usd']:,.2f}/mo, "
        f"${comparison['annual_savings_usd']:,.2f}/yr)."
    )

    if ri_eligible and sp_eligible:
        ri_savings = savings_from_factor(total_vm_spend, ri_rule.reserved_savings_threshold)
        sp_savings = savings_from_factor(compute_spend, 0.20)
        out.append(engine._finding(
            rule=sp_rule,
            subscription_id=subscription_id,
            resource=anchor,
            detail=(
                f"Subscription has ${total_vm_spend:,.2f}/month on-demand VM spend "
                f"across {running_count} stable running VMs — review commitments. {comparison_text}"
            ),
            recommendation=(
                "Compare 1-year and 3-year Reserved Instances with Azure Savings Plan coverage. "
                f"{comparison['recommendation']}"
            ),
            savings=max(ri_savings, sp_savings, comparison["best_monthly_savings_usd"]),
            waste_score=55,
            confidence=72,
            priority="P2",
            impact="Portfolio-level commitment discount opportunity",
            evidence={
                "total_vm_monthly_spend_usd": total_vm_spend,
                "estimated_compute_spend_usd": compute_spend,
                "running_vm_count": running_count,
                "stable_vm_count": stable_count,
                "top_skus_by_spend": top_skus,
                "subscription_spend_usd": subscription_spend_usd,
                "scope": "subscription",
                "commitment_options": comparison["options"],
                "commitment_comparison": comparison,
                "reserved_instance_estimated_savings_usd": ri_savings,
                "savings_plan_estimated_savings_usd": sp_savings,
            },
        ))
        return out

    if ri_eligible:
        est_savings = max(
            savings_from_factor(total_vm_spend, ri_rule.reserved_savings_threshold),
            comparison["best_monthly_savings_usd"],
        )
        out.append(engine._finding(
            rule=ri_rule,
            subscription_id=subscription_id,
            resource=anchor,
            detail=(
                f"Subscription has ${total_vm_spend:,.2f}/month on-demand VM spend "
                f"across {running_count} running VMs — suitable for Reserved Instances. {comparison_text}"
            ),
            recommendation=f"Group always-on VMs by SKU and region. {comparison['recommendation']}",
            savings=est_savings,
            waste_score=55,
            confidence=72,
            priority="P2",
            impact="Portfolio-level RI discount opportunity (~30–40%)",
            evidence={
                "total_vm_monthly_spend_usd": total_vm_spend,
                "running_vm_count": running_count,
                "stable_vm_count": stable_count,
                "top_skus_by_spend": top_skus,
                "scope": "subscription",
                "commitment_options": comparison["options"],
                "commitment_comparison": comparison,
            },
        ))

    if sp_eligible:
        est_savings = savings_from_factor(compute_spend, 0.20)
        out.append(engine._finding(
            rule=sp_rule,
            subscription_id=subscription_id,
            resource=anchor,
            detail=(
                f"Subscription compute spend (~${compute_spend:,.2f}/month) may qualify for Azure Savings Plans. "
                f"{comparison_text}"
            ),
            recommendation=f"Compare Savings Plan coverage against Reserved Instances. {comparison['recommendation']}",
            savings=max(est_savings, comparison["best_monthly_savings_usd"]),
            waste_score=48,
            confidence=68,
            priority="P2",
            impact="Flexible compute discount across VM families and regions",
            evidence={
                "estimated_compute_spend_usd": compute_spend,
                "subscription_spend_usd": subscription_spend_usd,
                "running_vm_count": running_count,
                "stable_vm_count": stable_count,
                "scope": "subscription",
                "commitment_options": comparison["options"],
                "commitment_comparison": comparison,
            },
        ))
    return out

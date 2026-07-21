"""Budgets optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding


def analyze_budgets(engine, subscription_id: str, budgets: list[dict], subscription_spend_usd: float) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    guardrail_rule = engine.rules.get("BUDGET_GUARDRAIL_EXTENDED")
    warn_rule = engine.rules.get("BUDGET_WARNING_EXTENDED")
    crit_rule = engine.rules.get("BUDGET_CRITICAL_EXTENDED")
    for budget in budgets:
        props = budget.get("properties") or budget
        amount = float(props.get("amount") or 0)
        if amount <= 0:
            continue
        current = engine._budget_current_spend(props, subscription_spend_usd)
        forecast = engine._budget_forecast_spend(props)
        used_pct = max(current, forecast) / amount * 100
        bname = budget.get("name") or props.get("name") or "subscription budget"
        evidence = {
            "amount": amount,
            "current_spend_usd": current,
            "forecast_spend_usd": forecast,
            "used_pct": used_pct,
        }

        if crit_rule and crit_rule.enabled and used_pct >= crit_rule.budget_crit_pct:
            out.append(engine._finding(
                rule=crit_rule,
                subscription_id=subscription_id,
                resource=budget,
                detail=f"Budget '{bname}' is at {used_pct:.1f}% of limit (critical threshold).",
                recommendation="Immediately review top spend drivers and pause non-critical workloads.",
                savings=0,
                waste_score=85,
                confidence=85,
                priority="P1",
                impact="Prevents budget overrun",
                evidence=evidence,
            ))
        elif warn_rule and warn_rule.enabled and used_pct >= warn_rule.budget_warn_pct:
            out.append(engine._finding(
                rule=warn_rule,
                subscription_id=subscription_id,
                resource=budget,
                detail=f"Budget '{bname}' is at {used_pct:.1f}% of limit (warning threshold).",
                recommendation="Review top spend drivers, pause non-prod workloads, and raise owner-specific remediation tickets.",
                savings=0,
                waste_score=60,
                confidence=78,
                priority="P2",
                impact="Controls budget overrun risk",
                evidence=evidence,
            ))
        elif guardrail_rule and guardrail_rule.enabled and used_pct >= 80:
            out.append(engine._finding(
                rule=guardrail_rule,
                subscription_id=subscription_id,
                resource=budget,
                detail=f"Budget '{bname}' is at {used_pct:.1f}% of limit.",
                recommendation="Review top spend drivers, pause non-prod workloads, and raise owner-specific remediation tickets.",
                savings=0,
                waste_score=70 if used_pct >= 95 else 54,
                confidence=78,
                priority="P1" if used_pct >= 95 else "P2",
                impact="Controls budget overrun risk",
                evidence=evidence,
            ))
    return out

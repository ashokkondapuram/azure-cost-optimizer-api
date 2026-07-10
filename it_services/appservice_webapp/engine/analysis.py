"""App Service optimization analysis rules."""
from __future__ import annotations

from typing import Any

from it_services.appservice_webapp.engine.optimization_rules import (
    evaluate_asp_consolidation_candidate,
    evaluate_webapp_plan_load_low,
)
from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from app.azure_retail_pricing import estimate_app_service_tier_savings
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import cpu_pct
from app.resource_utilization import is_low_cpu
from app.resource_utilization import is_low_cpu_time
from app.resource_utilization import is_low_memory
from app.resource_utilization import is_low_request_volume
from app.resource_utilization import metrics_block_rightsize
from app.resource_utilization import monitor_evidence
from app.resource_utilization import utilization_gate
from app.resource_utilization import webapp_utilization_summary


def _append_metrics_draft(out, engine, subscription_id, resource, rule, draft):
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=resource,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def analyze_app_services(engine, subscription_id: str, apps: list[dict], plans: list[dict], cost_by_resource: dict[str, float]) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    plan_rule = engine.rules.get("APP_SERVICE_PLAN_EXTENDED")
    stopped_rule = engine.rules.get("WEBAPP_STOPPED_EXTENDED")
    always_on_rule = engine.rules.get("WEBAPP_ALWAYS_ON_EXTENDED")

    apps_by_plan: dict[str, int] = {}
    for app in apps:
        plan_id = ((app.get("properties") or {}).get("serverFarmId") or "").lower()
        if plan_id:
            apps_by_plan[plan_id] = apps_by_plan.get(plan_id, 0) + 1

    if plan_rule and plan_rule.enabled:
        for plan in plans:
            pid = (plan.get("id") or "").lower()
            pname = plan.get("name") or ""
            sku = plan.get("sku") or {}
            tier = (sku.get("tier") or "").lower()
            count = apps_by_plan.get(pid, 0)
            plan_cost = resource_cost(cost_by_resource, plan.get("id", ""))
            if count == 0:
                out.append(engine._finding(
                    rule=plan_rule,
                    subscription_id=subscription_id,
                    resource=plan,
                    detail=f"App Service Plan '{pname}' ({tier}) has no hosted applications.",
                    recommendation="Delete unused plans or consolidate apps to reduce platform overhead.",
                    savings=plan_cost,
                    waste_score=74,
                    confidence=90,
                    priority="P2",
                    impact="Recurring App Service Plan cost with no workload",
                    evidence={"tier": tier, "app_count": count},
                ))
            elif tier in ("premium", "premiumv2", "premiumv3", "isolated") and count < plan_rule.asp_min_apps_for_premium:
                if metrics_block_rightsize(plan):
                    continue
                if not utilization_gate(plan, "avg_cpu_pct", allow_inventory_only=False):
                    continue
                low_cpu = is_low_cpu(plan, threshold=25.0)
                if low_cpu is not True:
                    continue
                detail = f"Plan '{pname}' is {tier} with only {count} app(s) — likely over-provisioned."
                if low_cpu is True:
                    detail += f" Average CPU is {cpu_pct(plan):.1f}% in Azure Monitor."
                suggested_tier = "standard"
                pricing = estimate_app_service_tier_savings(
                    plan.get("location") or "",
                    tier,
                    suggested_tier,
                    actual_monthly_cost=plan_cost if plan_cost > 0 else None,
                )
                savings = savings_from_retail_or_none(pricing)
                if savings is None and plan_cost > 0:
                    from app.cost_utils import savings_from_factor
                    savings = savings_from_factor(plan_cost, 0.35)
                out.append(engine._finding(
                    rule=plan_rule,
                    subscription_id=subscription_id,
                    resource=plan,
                    detail=detail,
                    recommendation="Downgrade SKU or migrate additional apps to improve plan utilization.",
                    savings=savings or 0,
                    waste_score=60,
                    confidence=confidence_with_monitor(75, plan, required_keys=("avg_cpu_pct",)),
                    priority="P3",
                    impact="Platform SKU optimization",
                    evidence=monitor_evidence(plan, {"tier": tier, "app_count": count, **pricing}),
                ))

            load_rule = engine.rules.get("WEBAPP_PLAN_LOAD_LOW_EXTENDED")
            consolidation_rule = engine.rules.get("ASP_CONSOLIDATION_CANDIDATE_EXTENDED")
            _append_metrics_draft(
                out, engine, subscription_id, plan, load_rule,
                evaluate_webapp_plan_load_low(plan, count, plan_cost, load_rule),
            )
            _append_metrics_draft(
                out, engine, subscription_id, plan, consolidation_rule,
                evaluate_asp_consolidation_candidate(plan, count, plan_cost, consolidation_rule),
            )

    for app in apps:
        props = app.get("properties") or {}
        state = (props.get("state") or "").lower()
        site_config = props.get("siteConfig") or {}
        always_on = bool(site_config.get("alwaysOn"))
        tags = app.get("tags") or {}
        env = str(tags.get("environment") or tags.get("env") or "").lower()
        aname = app.get("name") or ""
        app_cost = resource_cost(cost_by_resource, app.get("id", ""))

        if stopped_rule and stopped_rule.enabled and state == "stopped":
            out.append(engine._finding(
                rule=stopped_rule,
                subscription_id=subscription_id,
                resource=app,
                detail=f"Web app '{aname}' is stopped but still tied to a paid App Service Plan.",
                recommendation="Delete unused apps, move to a shared lower-tier plan, or start the app if still required.",
                savings=savings_from_factor(app_cost, 0.5) if app_cost > 0 else 0,
                waste_score=62,
                confidence=88,
                priority="P2",
                impact="Frees plan slots and reduces platform overhead",
                evidence={"state": state},
            ))

        if always_on_rule and always_on_rule.enabled and env in always_on_rule.prod_tag_values and not always_on:
            out.append(engine._finding(
                rule=always_on_rule,
                subscription_id=subscription_id,
                resource=app,
                detail=f"Production web app '{aname}' does not have Always On enabled.",
                recommendation="Enable Always On for production apps on Basic tier and above to avoid cold starts and failed probes.",
                savings=0,
                waste_score=38,
                confidence=confidence_with_monitor(82, app),
                priority="P2",
                impact="Improves reliability; may reduce retry-driven compute waste",
                evidence=monitor_evidence(app, {"environment": env, "alwaysOn": always_on}),
            ))

        low_cpu = is_low_cpu(app)
        low_cpu_time = is_low_cpu_time(app)
        low_requests = is_low_request_volume(app, threshold=500.0)
        low_util = low_cpu is True or low_cpu_time is True or low_requests is True
        low_mem = is_low_memory(app)
        if (
            plan_rule
            and plan_rule.enabled
            and low_util
            and low_mem is not False
            and app_cost > 0
            and utilization_gate(app, "avg_cpu_pct", allow_inventory_only=False)
        ):
            out.append(engine._finding(
                rule=plan_rule,
                subscription_id=subscription_id,
                resource=app,
                detail=(
                    f"Web app '{aname}' shows low utilization in Azure Monitor "
                    f"({webapp_utilization_summary(app)}) — review plan sizing."
                ),
                recommendation="Downgrade the App Service Plan SKU or consolidate apps to improve utilization.",
                savings=savings_from_factor(app_cost, 0.3),
                waste_score=55,
                confidence=confidence_with_monitor(78, app),
                priority="P3",
                impact="App Service compute right-sizing from utilization metrics",
                evidence=monitor_evidence(app, {"state": state, "monthly_cost_usd": app_cost}),
            ))
    return out


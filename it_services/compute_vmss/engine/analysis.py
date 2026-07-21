"""Virtual Machine Scale Sets optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from app.resource_utilization import cpu_pct
from app.resource_utilization import memory_pct
from app.vmss_metrics_catalog import parse_vmss_arm
from it_services.compute_vmss.engine.optimization_rules import (
    ComputeFindingDraft,
    evaluate_vmss_autoscale_tuning,
)


def _append_metrics_draft(out, engine, subscription_id, resource, rule, draft: ComputeFindingDraft | None):
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


def analyze_vmss(
    engine,
    subscription_id: str,
    scale_sets: list[dict],
    vm_metrics: dict[str, dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    autoscale_rule = engine.rules.get("VMSS_NO_AUTOSCALE_EXTENDED")
    scheduling_rule = engine.rules.get("VMSS_NONPROD_SCHEDULING_EXTENDED")
    for vmss in scale_sets:
        name = vmss.get("name") or ""
        tags = vmss.get("tags") or {}
        env = str(tags.get("environment") or tags.get("env") or "").lower()
        props = vmss.get("properties") or {}
        sku = ((props.get("virtualMachineProfile") or {}).get("hardwareProfile") or {}).get("vmSize") or ""
        vmss_ctx = parse_vmss_arm(vmss)
        capacity = int(vmss_ctx.get("capacity") or 0)
        monthly_cost = resource_cost(cost_by_resource, vmss.get("id", ""))
        has_autoscale = bool(vmss_ctx.get("has_autoscale"))

        if autoscale_rule and autoscale_rule.enabled and not has_autoscale and capacity > 1:
            out.append(engine._finding(
                rule=autoscale_rule,
                subscription_id=subscription_id,
                resource=vmss,
                detail=f"VMSS '{name}' has {capacity} fixed instances without autoscale profile.",
                recommendation="Configure Azure Monitor autoscale rules to scale based on CPU or queue depth.",
                savings=savings_from_factor(monthly_cost, 0.25) if monthly_cost > 0 else 0,
                waste_score=58,
                confidence=75,
                priority="P2",
                impact="Reduces over-provisioned scale set capacity",
                evidence={"capacity": capacity, "vm_size": sku, "monthly_cost_usd": monthly_cost},
            ))

        if scheduling_rule and scheduling_rule.enabled and env in scheduling_rule.nonprod_tag_values:
            cpu = cpu_pct(vmss)
            mem = memory_pct(vmss)
            low_util = (cpu is not None and cpu < 15) or (mem is not None and mem < 20)
            if low_util and (cpu is not None or mem is not None):
                savings = savings_from_factor(monthly_cost, scheduling_rule.nonprod_shutdown_hours_per_day / 24)
                out.append(engine._finding(
                    rule=scheduling_rule,
                    subscription_id=subscription_id,
                    resource=vmss,
                    detail=f"VMSS '{name}' appears non-production (env={env}) and may run continuously.",
                    recommendation=f"Apply shutdown schedule or scale to zero outside business hours (up to {scheduling_rule.nonprod_shutdown_hours_per_day} hrs/day savings).",
                    savings=savings,
                    waste_score=55,
                    confidence=70,
                    priority="P2",
                    impact="Non-prod scale set scheduling savings",
                    evidence={"environment": env, "capacity": capacity, "avg_cpu_pct": cpu},
                ))

        tuning_rule = engine.rules.get("VMSS_AUTOSCALE_TUNING_EXTENDED")
        _append_metrics_draft(
            out, engine, subscription_id, vmss, tuning_rule,
            evaluate_vmss_autoscale_tuning(vmss, vmss_ctx, monthly_cost, tuning_rule),
        )
    return out

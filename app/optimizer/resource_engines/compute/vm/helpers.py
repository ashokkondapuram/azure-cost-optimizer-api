"""VM-specific analysis helpers for the extended optimization engine."""
from __future__ import annotations

from typing import Any

from app.azure_retail_pricing import estimate_vm_sku_savings, vm_os_type
from app.pricing.savings_calculator import enrich_pricing_payload, savings_from_retail_or_none
from app.resource_utilization import (
    VM_SIZING_FACT_KEYS,
    confidence_with_monitor,
    data_quality,
    evidence_data_source,
    monitor_facts_status,
    technical_facts,
)
from app.vm_sizing import VmUtilization, extract_vm_utilization, parse_vm_sku
from app.optimizer.advanced_rules import AdvancedRule
from app.optimizer.core.finding import ExtendedFinding

SIZING_ACTION_VERBS = {
    "downgrade": "Downsize",
    "cross_family": "Change family to",
    "upgrade": "Upsize",
}
RIGHTSIZING_ACTIONS = frozenset({"downgrade", "cross_family", "upgrade"})
VM_RIGHTSIZING_RULE_IDS = frozenset({
    "VM_SKU_SIZING_EXTENDED",
    "VM_RIGHTSIZE_FAMILY",
})
VM_RIGHTSIZING_SEVERITY = "MEDIUM"


def sizing_action_label(action: str | None) -> str:
    return SIZING_ACTION_VERBS.get(action or "", "Resize")


def vm_optimization_action_text(sizing, *, fallback: str | None = None) -> str:
    """Lead-in text for VM rightsizing recommendations (downsize or change family)."""
    fallback = fallback or (
        "Downsize, schedule shutdown, or move suitable non-prod workloads "
        "to burstable or Spot-backed patterns."
    )
    if not sizing or not getattr(sizing, "suggested_sku", None):
        return fallback
    action = getattr(sizing, "action", None)
    if action == "cross_family":
        return (
            f"Change family to {sizing.suggested_sku}, schedule shutdown, or move suitable "
            f"non-prod workloads to burstable or Spot-backed patterns."
        )
    if action == "downgrade":
        return (
            f"Downsize to {sizing.suggested_sku}, schedule shutdown, or move suitable "
            f"non-prod workloads to burstable or Spot-backed patterns."
        )
    return fallback


def idle_vm_action_text(sizing) -> str:
    if not sizing or not sizing.suggested_sku or sizing.action not in RIGHTSIZING_ACTIONS:
        return "Deallocate if unused, or downsize to a smaller SKU."
    if sizing.action == "cross_family":
        return f"Change family to {sizing.suggested_sku}."
    return f"Downsize to {sizing.suggested_sku}."


def vm_catalog(engine, subscription_id: str, location: str) -> list[dict[str, Any]]:
    key = (subscription_id.strip().lower(), (location or "").strip().lower())
    if key in engine._vm_catalog_cache:
        return engine._vm_catalog_cache[key]
    catalog: list[dict[str, Any]] = []
    if key[1]:
        try:
            from app.azure_resources import AzureResourcesClient
            catalog = AzureResourcesClient().list_vm_sizes(subscription_id, location) or []
        except Exception:
            catalog = []
    engine._vm_catalog_cache[key] = catalog
    return catalog


def vm_utilization(engine, vm: dict, vm_metrics: dict[str, dict]) -> VmUtilization:
    rid = (vm.get("id") or "").lower()
    props = vm.get("properties") or {}
    sku = (
        ((props.get("hardwareProfile") or {}).get("vmSize"))
        or ((props.get("virtualMachineProfile") or {}).get("hardwareProfile") or {}).get("vmSize")
        or ""
    )
    payload = vm_metrics.get(rid)
    util = extract_vm_utilization(payload, sku=sku)
    facts = technical_facts(vm)

    cpu = util.avg_cpu_pct if util.has_cpu else facts.get("avg_cpu_pct")
    mem = util.avg_memory_pct if util.has_memory else facts.get("avg_memory_pct")
    avail = util.avg_available_memory_bytes or facts.get("avg_available_memory_bytes")

    if mem is None and avail is not None and sku and payload:
        derived = extract_vm_utilization(
            {
                "value": [{
                    "name": {"value": "Available Memory Bytes"},
                    "timeseries": [{"data": [{"average": avail}]}],
                }],
            },
            sku=sku,
        )
        mem = derived.avg_memory_pct

    if cpu is not None or mem is not None:
        parsed = parse_vm_sku(sku) if sku else None
        return VmUtilization(
            avg_cpu_pct=float(cpu) if cpu is not None else None,
            avg_memory_pct=float(mem) if mem is not None else None,
            avg_available_memory_bytes=avail,
            memory_gb_total=parsed.memory_gb if parsed else None,
            metrics_window=util.metrics_window,
            has_cpu=cpu is not None,
            has_memory=mem is not None,
        )
    return util


def vm_sizing_data_source(vm: dict, vm_metrics: dict[str, dict]) -> str:
    rid = (vm.get("id") or "").lower()
    if vm_metrics.get(rid):
        return "azure_monitor"
    return evidence_data_source(vm)


def vm_sizing_pricing(
    vm: dict,
    current_sku: str,
    suggested_sku: str,
    *,
    monthly_cost: float = 0.0,
) -> tuple[float | None, dict[str, Any]]:
    """Return (savings_usd or None, pricing_evidence) from Azure retail on-demand SKU prices."""
    pricing = enrich_pricing_payload(
        estimate_vm_sku_savings(
            (vm.get("location") or "").strip(),
            current_sku,
            suggested_sku,
            os_type=vm_os_type(vm),
            actual_monthly_cost=monthly_cost if monthly_cost > 0 else None,
        )
    )
    return savings_from_retail_or_none(pricing), pricing


def apply_vm_rightsizing_severity(finding: ExtendedFinding) -> ExtendedFinding:
    """Return finding with severity from the rule (configurable via engine profile)."""
    return finding


def emit_vm_sizing_finding(
    engine,
    *,
    sizing_rule: AdvancedRule,
    subscription_id: str,
    vm: dict,
    sku: str,
    sizing,
    monthly_cost: float,
    cpu,
    mem,
    util: VmUtilization,
    vm_metrics: dict[str, dict] | None = None,
) -> ExtendedFinding | None:
    if not sizing or sizing.action not in {"downgrade", "upgrade", "cross_family"} or not sizing.suggested_sku:
        return None
    if sizing.action == "insufficient_data":
        return None
    active_rule = sizing_rule
    if sizing.action == "cross_family":
        family_rule = engine.rules.get("VM_RIGHTSIZE_FAMILY")
        if family_rule and family_rule.enabled:
            active_rule = family_rule

    savings, pricing = vm_sizing_pricing(
        vm,
        sku,
        sizing.suggested_sku,
        monthly_cost=monthly_cost,
    )
    pricing_available = pricing.get("pricing_status") == "available"
    if not pricing_available:
        savings = 0.0
    elif savings is None:
        savings = 0.0

    current_retail = pricing.get("current_sku_monthly_usd")
    suggested_retail = pricing.get("suggested_sku_monthly_usd")
    savings_detail = ""
    if current_retail is not None and suggested_retail is not None:
        savings_detail = (
            f" Azure retail pricing: {sku} ~${current_retail:,.2f}/mo → "
            f"{sizing.suggested_sku} ~${suggested_retail:,.2f}/mo "
            f"(est. savings ${savings:,.2f}/mo)."
        )

    verb = sizing_action_label(sizing.action)
    name = vm.get("name") or ""
    cpu_text = f"{cpu:.1f}% CPU" if cpu is not None else "low CPU"
    mem_text = f" and {mem:.1f}% memory" if mem is not None else ""
    family_label = parse_vm_sku(sku).family_label if parse_vm_sku(sku) else sizing.family_label
    data_src = vm_sizing_data_source(vm, vm_metrics or {})
    confidence = min(
        sizing.confidence,
        confidence_with_monitor(sizing.confidence, vm, required_keys=VM_SIZING_FACT_KEYS),
    )
    return apply_vm_rightsizing_severity(
        engine._finding(
        rule=active_rule,
        subscription_id=subscription_id,
        resource=vm,
        detail=(
            f"VM '{name}' ({family_label}) averages {cpu_text}{mem_text}"
            f" — {sizing.action.replace('_', ' ')} candidate."
        ),
        recommendation=(
            f"{verb} {sku} → {sizing.suggested_sku}. "
            "Validate disk, networking, and maintenance window before resizing."
            f"{savings_detail}"
        ),
        savings=savings,
        waste_score=70 if sizing.action == "downgrade" else 55,
        confidence=confidence,
        priority="P2" if sizing.action == "downgrade" else "P3",
        impact="Rightsize compute to match workload shape",
        evidence={
            **util.as_dict(),
            "vm_size": sku,
            "suggested_sku": sizing.suggested_sku,
            "sizing_action": sizing.action,
            "sku_family": sizing.current_family,
            "suggested_family": sizing.suggested_family,
            "family_label": sizing.family_label,
            "sizing_reasons": sizing.reasons,
            "monthly_cost_usd": monthly_cost,
            "data_source": data_src,
            "monitor_facts_status": monitor_facts_status(vm, *VM_SIZING_FACT_KEYS),
            "data_quality": data_quality(vm, *VM_SIZING_FACT_KEYS),
            **pricing,
        },
    ))

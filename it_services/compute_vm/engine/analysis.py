"""Virtual Machines optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from app.resource_utilization import (
    VM_SIZING_FACT_KEYS,
    confidence_with_monitor,
    fact_value,
    merge_vm_utilization_facts,
    monitor_evidence,
    peak_cpu_ok_for_downsize,
    vm_sizing_metrics_ok,
)
from app.vm_sizing import recommend_vm_sku
from app.vm_uptime import vm_is_running, vm_uptime_facts
from app.optimizer.platform.cost.commitments.analysis import (
    _is_stable_workload,
    subscription_commitment_eligible,
)
from app.resource_pricing import compare_commitment_options
from it_services.compute_vm.engine.schedule import classify_workload_schedule
from app.optimizer.workload_classifier import (
    classify_workload,
    downsize_allowed_for_workload,
    is_zombie_workload,
)
from it_services.compute_vm.engine.helpers import (
    VM_RIGHTSIZING_RULE_IDS,
    VM_RIGHTSIZING_SEVERITY,
    apply_vm_rightsizing_severity,
    emit_vm_sizing_finding,
    merge_advisor_vm_target,
    vm_catalog,
    vm_optimization_action_text,
    vm_sizing_data_source,
    vm_sizing_pricing,
    vm_utilization,
)


from app.utilization_history import downsize_allowed_by_trend
from app.focus_mapping import normalize_arm_id
from app.vm_metrics_catalog import parse_vm_arm
from it_services.compute_vm.engine.optimization_rules import (
    ComputeFindingDraft,
    evaluate_vm_egress_high,
    evaluate_vm_memory_pressure,
)


def _append_metrics_draft(
    out: list[ExtendedFinding],
    engine,
    subscription_id: str,
    vm: dict,
    rule,
    draft: ComputeFindingDraft | None,
) -> None:
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=vm,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def _facts_for_id(resource_facts: dict[str, dict[str, float]], resource_id: str) -> dict[str, float]:
    return dict(resource_facts.get(normalize_arm_id(resource_id).lower(), {}))


def _vm_bottleneck_findings(
    engine,
    subscription_id: str,
    vm: dict,
    *,
    resource_graph: dict[str, dict[str, list[str]]] | None,
    resource_facts: dict[str, dict[str, float]],
    monthly_cost: float,
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rid = normalize_arm_id(vm.get("id") or "").lower()
    name = vm.get("name") or ""
    links = (resource_graph or {}).get(rid) or {}
    related_ids: list[str] = []

    disk_rule = engine.rules.get("VM_DISK_BOTTLENECK")
    if disk_rule and disk_rule.enabled:
        for disk_id in links.get("disk_ids") or []:
            facts = _facts_for_id(resource_facts, disk_id)
            util_pct = facts.get("max_disk_iops_utilization_pct") or facts.get("disk_iops_utilization_pct")
            if util_pct is not None and float(util_pct) > 80.0:
                related_ids.append(disk_id)
                out.append(engine._finding(
                    rule=disk_rule,
                    subscription_id=subscription_id,
                    resource=vm,
                    detail=(
                        f"VM '{name}' has low average CPU but an attached disk is saturating IOPS "
                        f"({float(util_pct):.1f}% of provisioned peak)."
                    ),
                    recommendation="Right-size or upgrade the attached disk before downsizing the VM SKU.",
                    savings=0,
                    waste_score=70,
                    confidence=82,
                    priority="P1",
                    impact="Avoid conflicting compute and storage recommendations",
                    evidence={
                        "disk_resource_id": disk_id,
                        "max_disk_iops_utilization_pct": float(util_pct),
                        "monthly_cost_usd": monthly_cost,
                    },
                    related_resource_ids=related_ids,
                ))
                break

    nic_rule = engine.rules.get("VM_NETWORK_BOTTLENECK")
    if nic_rule and nic_rule.enabled:
        for nic_id in links.get("nic_ids") or []:
            facts = _facts_for_id(resource_facts, nic_id)
            tx = facts.get("bytes_sent_rate")
            rx = facts.get("bytes_received_rate")
            saturated = (
                (tx is not None and float(tx) >= 50_000_000.0)
                or (rx is not None and float(rx) >= 50_000_000.0)
            )
            if saturated:
                related_ids.append(nic_id)
                out.append(engine._finding(
                    rule=nic_rule,
                    subscription_id=subscription_id,
                    resource=vm,
                    detail=f"VM '{name}' shows network egress/ingress saturation on attached NIC '{nic_id.split('/')[-1]}'.",
                    recommendation="Investigate network throughput limits before reducing VM size.",
                    savings=0,
                    waste_score=68,
                    confidence=78,
                    priority="P1",
                    impact="Prevent VM downsize when network is the constraint",
                    evidence={
                        "nic_resource_id": nic_id,
                        "bytes_sent_rate": tx,
                        "bytes_received_rate": rx,
                    },
                    related_resource_ids=related_ids,
                ))
                break
    return out


def analyze_vms(
    engine,
    subscription_id: str,
    vms: list[dict],
    vm_metrics: dict[str, dict],
    cost_by_resource: dict[str, float],
    *,
    subscription_spend_usd: float = 0.0,
    resource_graph: dict[str, dict[str, list[str]]] | None = None,
    resource_facts: dict[str, dict[str, float]] | None = None,
    resource_cost_histories: dict[str, list[float]] | None = None,
    utilization_trends: dict[str, dict[str, dict[str, Any]]] | None = None,
    workload_classes: dict[str, str] | None = None,
    advisor_vm_targets: dict[str, Any] | None = None,
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    under = engine.rules["VM_UNDERUTILIZED_EXTENDED"]
    family = engine.rules["VM_RIGHTSIZE_FAMILY"]
    commit = engine.rules["VM_COMMITMENT_CANDIDATE"]
    tags_rule = engine.rules["VM_MISSING_GOVERNANCE_TAGS"]
    sizing_rule = engine.rules.get("VM_SKU_SIZING_EXTENDED")
    rightsized_rids: set[str] = set()
    resource_facts = resource_facts or {}
    resource_cost_histories = resource_cost_histories or {}
    utilization_trends = utilization_trends or {}
    workload_classes = workload_classes or {}
    advisor_vm_targets = advisor_vm_targets or {}
    skip_per_vm_commitment = subscription_commitment_eligible(
        engine,
        vms,
        cost_by_resource,
        subscription_spend_usd,
        resource_cost_histories=resource_cost_histories,
    )
    for vm in vms:
        rid = (vm.get("id") or "").lower()
        name = vm.get("name") or ""
        tags = vm.get("tags") or {}
        loc = vm.get("location") or ""
        props = vm.get("properties") or {}
        sku = (
            ((props.get("hardwareProfile") or {}).get("vmSize"))
            or ((props.get("virtualMachineProfile") or {}).get("hardwareProfile") or {}).get("vmSize")
            or ""
        )
        monthly_cost = resource_cost(cost_by_resource, rid)
        advisor_target = advisor_vm_targets.get(rid)
        util = vm_utilization(engine, vm, vm_metrics)
        cpu = util.avg_cpu_pct
        mem = util.avg_memory_pct
        vm_eval = merge_vm_utilization_facts(vm, util, vm_metrics=vm_metrics)
        tech_facts = _facts_for_id(resource_facts, rid)
        for fact_key, fact_val in tech_facts.items():
            vm_eval.setdefault("_technical_facts", {})
            if isinstance(vm_eval["_technical_facts"], dict):
                vm_eval["_technical_facts"][fact_key] = fact_val
        wl_class = workload_classes.get(rid) or classify_workload(
            vm_eval,
            vm_eval.get("_technical_facts") or {},
            resource_type="compute/vm",
        )
        bottleneck_findings = _vm_bottleneck_findings(
            engine,
            subscription_id,
            vm_eval,
            resource_graph=resource_graph,
            resource_facts=resource_facts,
            monthly_cost=monthly_cost,
        )
        out.extend(bottleneck_findings)
        vm_ctx = parse_vm_arm(vm_eval)
        for rule_id, evaluator in (
            ("VM_MEMORY_PRESSURE_EXTENDED", evaluate_vm_memory_pressure),
            ("VM_EGRESS_HIGH_EXTENDED", evaluate_vm_egress_high),
        ):
            metrics_rule = engine.rules.get(rule_id)
            _append_metrics_draft(
                out, engine, subscription_id, vm_eval, metrics_rule,
                evaluator(vm_eval, vm_ctx, monthly_cost, metrics_rule),
            )
        has_disk_bottleneck = any(f.rule_id == "VM_DISK_BOTTLENECK" for f in bottleneck_findings)
        sizing_metrics_ok = vm_sizing_metrics_ok(vm, util, vm_metrics)
        catalog = vm_catalog(engine, subscription_id, loc) if sku and loc else []
        iv = props.get("instanceView", {})
        statuses = iv.get("statuses", [])
        power = next(
            (s.get("code", "").replace("PowerState/", "") for s in statuses
             if str(s.get("code", "")).startswith("PowerState")),
            "",
        )
        power_norm = power.replace("PowerState/", "") if power else ""
        stopped_rule = engine.rules.get("VM_STOPPED_BILLING_EXTENDED")
        if stopped_rule and stopped_rule.enabled and power_norm == "stopped":
            savings = monthly_cost if monthly_cost > 0 else 0.0
            out.append(engine._finding(
                rule=stopped_rule,
                subscription_id=subscription_id,
                resource=vm,
                detail=f"VM '{name}' is stopped (not deallocated) and may still incur compute charges.",
                recommendation="Deallocate the VM when it is not needed, or delete it if it is no longer required.",
                savings=savings,
                waste_score=88,
                confidence=95,
                priority="P1",
                impact="Eliminates recurring compute charges for an unused VM",
                evidence={
                    "power_state": power_norm,
                    "vm_size": sku,
                    "monthly_cost_usd": monthly_cost,
                },
            ))
        if sizing_rule and sizing_rule.enabled and sku and sizing_metrics_ok:
            sizing = recommend_vm_sku(
                current_sku=sku,
                utilization=util,
                catalog=catalog,
                cpu_down_pct=sizing_rule.cpu_idle_pct,
                cpu_up_pct=sizing_rule.cpu_oversize_pct,
                memory_down_pct=sizing_rule.memory_idle_pct,
                memory_up_pct=85.0,
            )
            finding = emit_vm_sizing_finding(
                engine,
                sizing_rule=sizing_rule,
                subscription_id=subscription_id,
                vm=vm_eval,
                sku=sku,
                sizing=sizing,
                monthly_cost=monthly_cost,
                cpu=cpu,
                mem=mem,
                util=util,
                vm_metrics=vm_metrics,
                advisor_target=advisor_target,
            )
            if finding:
                out.append(finding)
                rightsized_rids.add(rid)
        elif (
            sizing_rule
            and sizing_rule.enabled
            and sku
            and advisor_target
            and rid not in rightsized_rids
        ):
            finding = emit_vm_sizing_finding(
                engine,
                sizing_rule=sizing_rule,
                subscription_id=subscription_id,
                vm=vm_eval,
                sku=sku,
                sizing=None,
                monthly_cost=monthly_cost,
                cpu=cpu,
                mem=mem,
                util=util,
                vm_metrics=vm_metrics,
                advisor_target=advisor_target,
            )
            if finding:
                out.append(finding)
                rightsized_rids.add(rid)

        if (
            under.enabled
            and rid not in rightsized_rids
            and not has_disk_bottleneck
            and sizing_metrics_ok
            and cpu is not None
            and monthly_cost >= under.min_monthly_savings_usd
            and cpu < under.cpu_idle_pct
            and peak_cpu_ok_for_downsize(vm_eval, avg_threshold=under.cpu_idle_pct)
            and downsize_allowed_for_workload(
                wl_class,
                vm_eval.get("_technical_facts") or {},
                avg_threshold=under.cpu_idle_pct,
            )
            and downsize_allowed_by_trend((utilization_trends.get(rid) or {}).get("avg_cpu_pct"))
        ):
            cpu_trend = (utilization_trends.get(rid) or {}).get("avg_cpu_pct") or {}
            idle_sizing = recommend_vm_sku(
                current_sku=sku,
                utilization=util,
                catalog=catalog,
                cpu_down_pct=under.cpu_idle_pct,
                memory_down_pct=under.cpu_idle_pct,
            )
            idle_sizing, _ = merge_advisor_vm_target(
                idle_sizing,
                current_sku=sku,
                advisor=advisor_target,
            )
            savings = 0.0
            pricing: dict[str, Any] = {}
            price_note = ""
            if idle_sizing and idle_sizing.suggested_sku and idle_sizing.action in {"downgrade", "cross_family"}:
                retail_savings, pricing = vm_sizing_pricing(
                    vm, sku, idle_sizing.suggested_sku, monthly_cost=monthly_cost,
                )
                if retail_savings is not None:
                    savings = retail_savings
                    current_retail = pricing.get("current_sku_monthly_usd")
                    suggested_retail = pricing.get("suggested_sku_monthly_usd")
                    if current_retail is not None and suggested_retail is not None:
                        price_note = (
                            f" Consider {idle_sizing.suggested_sku} "
                            f"(~${current_retail:,.2f}/mo → ~${suggested_retail:,.2f}/mo)."
                        )
            has_sizing_rec = bool(
                idle_sizing
                and idle_sizing.suggested_sku
                and idle_sizing.action in {"downgrade", "cross_family", "upgrade"}
            )
            if has_sizing_rec:
                active_rule = sizing_rule if sizing_rule and sizing_rule.enabled else family
                if active_rule and active_rule.enabled:
                    sizing_finding = emit_vm_sizing_finding(
                        engine,
                        sizing_rule=active_rule,
                        subscription_id=subscription_id,
                        vm=vm_eval,
                        sku=sku,
                        sizing=idle_sizing,
                        monthly_cost=monthly_cost,
                        cpu=cpu,
                        mem=mem,
                        util=util,
                        vm_metrics=vm_metrics,
                        advisor_target=advisor_target,
                    )
                    if sizing_finding:
                        out.append(sizing_finding)
                        rightsized_rids.add(rid)
                        continue
            if not has_sizing_rec and savings < under.min_monthly_savings_usd:
                continue
            if has_sizing_rec:
                continue
            action_text = vm_optimization_action_text(idle_sizing)
            out.append(engine._finding(
                rule=under,
                subscription_id=subscription_id,
                resource=vm,
                detail=f"VM '{name}' shows sustained low CPU utilization ({cpu:.1f}%) with recurring monthly cost.",
                recommendation=f"{action_text}{price_note}",
                savings=savings,
                waste_score=82,
                confidence=confidence_with_monitor(88, vm_eval, required_keys=VM_SIZING_FACT_KEYS),
                priority="P1",
                impact="High recurring compute savings",
                evidence=monitor_evidence(vm_eval, {
                    "workload_class": wl_class,
                    "avg_cpu_pct": cpu,
                    "max_cpu_pct": fact_value(vm_eval, "max_cpu_pct"),
                    "utilization_trend": cpu_trend.get("slope"),
                    "projected_cpu_4w": cpu_trend.get("projected_4w"),
                    "trend_sample_count": cpu_trend.get("sample_count"),
                    "vm_size": sku,
                    "suggested_sku": idle_sizing.suggested_sku if idle_sizing else None,
                    "sizing_action": idle_sizing.action if idle_sizing else None,
                    "power_state": power or "unknown",
                    "monthly_cost_usd": monthly_cost,
                    "data_source": vm_sizing_data_source(vm, vm_metrics),
                    **pricing,
                }),
            ))
        if (
            family.enabled
            and rid not in rightsized_rids
            and not (sizing_rule and sizing_rule.enabled)
            and sku
            and sizing_metrics_ok
        ):
            sizing = recommend_vm_sku(
                current_sku=sku,
                utilization=util,
                catalog=catalog,
                cpu_down_pct=family.cpu_oversize_pct,
                cpu_up_pct=75.0,
                memory_down_pct=30.0,
            )
            if sizing and sizing.action == "cross_family" and sizing.suggested_sku:
                savings, pricing = vm_sizing_pricing(
                    vm,
                    sku,
                    sizing.suggested_sku,
                    monthly_cost=monthly_cost,
                )
                if savings is None:
                    savings = 0.0
                current_retail = pricing.get("current_sku_monthly_usd")
                suggested_retail = pricing.get("suggested_sku_monthly_usd")
                price_note = ""
                if current_retail is not None and suggested_retail is not None:
                    price_note = (
                        f" Azure retail pricing: {sku} ~${current_retail:,.2f}/mo → "
                        f"{sizing.suggested_sku} ~${suggested_retail:,.2f}/mo "
                        f"(est. savings ${savings:,.2f}/mo)."
                    )
                out.append(apply_vm_rightsizing_severity(engine._finding(
                    rule=family,
                    subscription_id=subscription_id,
                    resource=vm,
                    detail=(
                        f"VM '{name}' workload shape fits a different SKU family "
                        f"({sizing.current_family} → {sizing.suggested_family})."
                    ),
                    recommendation=(
                        f"Change family to {sizing.suggested_sku}. "
                        "Validate disk, networking, and maintenance window before resizing."
                        f"{price_note}"
                    ),
                    savings=savings,
                    waste_score=64,
                    confidence=min(
                        sizing.confidence,
                        confidence_with_monitor(sizing.confidence, vm_eval, required_keys=VM_SIZING_FACT_KEYS),
                    ),
                    priority="P2",
                    impact="Meaningful compute optimization with low risk",
                    evidence={
                        **util.as_dict(),
                        "vm_size": sku,
                        "suggested_sku": sizing.suggested_sku,
                        "sizing_action": sizing.action,
                        "sku_family": sizing.current_family,
                        "suggested_family": sizing.suggested_family,
                        "monthly_cost_usd": monthly_cost,
                        "data_source": vm_sizing_data_source(vm, vm_metrics),
                        **pricing,
                    },
                )))
                rightsized_rids.add(rid)
        if (
            commit.enabled
            and not skip_per_vm_commitment
            and monthly_cost >= commit.min_monthly_savings_usd
            and monthly_cost > 0
        ):
            uptime = vm_uptime_facts(vm, power_state=power_norm)
            uptime_hours = uptime.get("uptime_hours")
            running = vm_is_running(vm, power_state=power_norm)
            min_uptime = float(commit.vm_uptime_hours_candidate or 0)
            if running and uptime_hours is not None and uptime_hours >= min_uptime:
                history = resource_cost_histories.get(rid, [])
                if resource_cost_histories and not _is_stable_workload(rid, history):
                    continue
                comparison = compare_commitment_options(monthly_cost, sku)
                savings = comparison["best_monthly_savings_usd"] or savings_from_factor(monthly_cost, 0.18)
                evidence_payload: dict[str, Any] = {
                    "monthly_cost_usd": monthly_cost,
                    "vm_size": sku,
                    "power_state": power or "unknown",
                    "uptime_hours": uptime_hours,
                    "commitment_comparison": comparison,
                }
                if uptime.get("time_created"):
                    evidence_payload["time_created"] = uptime["time_created"]
                if uptime.get("uptime_source") == "vmss_instance":
                    evidence_payload["uptime_source"] = "vmss_instance"
                    props_uptime = props.get("oldest_instance_time_created")
                    if props_uptime:
                        evidence_payload["oldest_instance_time_created"] = props_uptime
                out.append(engine._finding(
                    rule=commit,
                    subscription_id=subscription_id,
                    resource=vm,
                    detail=(
                        f"VM '{name}' has been running for {uptime_hours:,.0f} hours "
                        f"with sufficient recurring spend to evaluate Reservations or Savings Plans."
                    ),
                    recommendation=(
                        f"Compare commitment options for this VM. {comparison['recommendation']}"
                    ),
                    savings=savings,
                    waste_score=42,
                    confidence=70,
                    priority="P3",
                    impact="Portfolio-level discount opportunity",
                    evidence=evidence_payload,
                ))
        missing_tags = [t for t in tags_rule.require_tags if not tags.get(t)]
        if tags_rule.enabled and missing_tags:
            out.append(engine._finding(
                rule=tags_rule,
                subscription_id=subscription_id,
                resource=vm,
                detail=f"VM '{name}' is missing governance tags: {', '.join(missing_tags)}.",
                recommendation="Enforce Azure Policy for required tags so savings can be assigned to owners and cost centers.",
                savings=0,
                waste_score=38,
                confidence=96,
                priority="P2",
                impact="Improves accountability and recommendation quality",
                evidence={"missing_tags": missing_tags},
            ))

        schedule_rule = engine.rules.get("VM_SCHEDULE_CANDIDATE_EXTENDED")
        zombie_rule = engine.rules.get("VM_ZOMBIE_CANDIDATE_EXTENDED")
        schedule_class = classify_workload_schedule(
            vm_eval,
            vm_eval.get("_technical_facts") or {},
            daily_cost=resource_cost_histories.get(rid, []),
            power_state=power_norm,
        )
        if schedule_rule and schedule_rule.enabled and schedule_class == "schedule_candidate":
            env = str(tags.get("environment") or tags.get("env") or "").lower()
            savings = monthly_cost if monthly_cost > 0 else savings_from_factor(50.0, 0.85)
            out.append(engine._finding(
                rule=schedule_rule,
                subscription_id=subscription_id,
                resource=vm,
                detail=(
                    f"VM '{name}' is often stopped or deallocated (workload class: schedule candidate). "
                    f"Current power state: {power_norm or 'unknown'}."
                ),
                recommendation=(
                    "Delete the VM if it is no longer needed, or automate start/stop on a schedule "
                    "instead of leaving it idle between runs."
                ),
                savings=savings,
                waste_score=70,
                confidence=78,
                priority="P2",
                impact="Reduce recurring compute for intermittently used VMs",
                evidence={
                    "workload_class": wl_class,
                    "schedule_class": schedule_class,
                    "power_state": power_norm,
                    "environment": env,
                    "monthly_cost_usd": monthly_cost,
                    "idle_days_last_7": _idle_days_hint(resource_cost_histories.get(rid, [])),
                },
            ))
        elif zombie_rule and zombie_rule.enabled and (
            schedule_class == "zombie_candidate" or is_zombie_workload(wl_class)
        ):
            avg_cpu = fact_value(vm_eval, "avg_cpu_pct")
            savings = monthly_cost if monthly_cost > 0 else 0.0
            out.append(engine._finding(
                rule=zombie_rule,
                subscription_id=subscription_id,
                resource=vm,
                detail=(
                    f"VM '{name}' runs continuously with very low CPU "
                    f"({avg_cpu:.1f}% average) — zombie workload candidate."
                    if avg_cpu is not None
                    else f"VM '{name}' runs continuously with near-zero utilization — zombie workload candidate."
                ),
                recommendation="Deallocate or delete this VM after confirming no downstream dependency.",
                savings=savings,
                waste_score=76,
                confidence=82,
                priority="P1",
                impact="Eliminate always-on compute with no meaningful workload",
                evidence={
                    "workload_class": wl_class,
                    "avg_cpu_pct": avg_cpu,
                    "max_cpu_pct": fact_value(vm_eval, "max_cpu_pct"),
                    "power_state": power_norm,
                    "monthly_cost_usd": monthly_cost,
                },
            ))
    return out


def _idle_days_hint(daily_cost: list[float]) -> int:
    if not daily_cost:
        return 0
    return sum(1 for amount in daily_cost[-7:] if float(amount or 0.0) < 0.5)

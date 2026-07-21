"""Managed Disks optimization analysis — driven by disk-assessment.json."""

from __future__ import annotations

from datetime import datetime, timezone

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.pricing.savings_calculator import savings_from_disk_pricing
from app.azure_retail_pricing import estimate_disk_tier_savings
from app.disk_staleness import augment_disk_evidence
from app.disk_staleness import evaluate_unattached_disk
from app.disk_staleness import staleness_evidence
from app.disk_utilization import (
    disk_utilization_evidence,
    disk_utilization_gate,
    is_disk_underprovisioned,
    metrics_block_disk_downgrade,
    peak_disk_iops_utilization_pct,
)
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import is_idle_io
from app.resource_utilization import monitor_evidence
from it_services.compute_disk.assessment_bridge import (
    ASSESSMENT_FILE,
    augment_finding_evidence,
    grace_period_days,
    metric_keys_for_rule,
    optimization_thresholds,
    peak_downgrade_block_iops_pct,
    rule_recommendation_text,
    rule_target_tier,
    rule_utilization_thresholds,
)
from it_services.compute_disk.engine.optimization_rules import (
    evaluate_disk_capacity_rightsize,
    evaluate_disk_queue_depth,
)


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
        evidence=augment_finding_evidence(draft.rule_id, draft.evidence),
    ))


def _disk_threshold_evidence(rule) -> dict[str, float | int]:
    """Persist rule thresholds under rule_thresholds — not as display evidence rows."""
    thresholds = {
        key: getattr(rule, key)
        for key in (
            "max_unattached_disk_days",
            "disk_io_idle_bps",
            "disk_idle_min_size_gb",
            "disk_iops_block_downgrade_pct",
            "disk_iops_high_util_pct",
            "evaluation_window_days",
            "min_monthly_savings_usd",
        )
        if getattr(rule, key, None) is not None
    }
    return {"rule_thresholds": thresholds} if thresholds else {}


def _peak_iops_allows_downgrade(disk: dict, *, threshold_pct: float | None = None) -> bool:
    """Only downgrade when peak IOPS stay below threshold of provisioned capacity."""
    block_pct = threshold_pct if threshold_pct is not None else peak_downgrade_block_iops_pct()
    peak_util = peak_disk_iops_utilization_pct(disk, disk)
    if peak_util is None:
        return True
    return peak_util < block_pct


def _tier_savings(
    disk: dict,
    *,
    size_gb: int | float,
    sku_name: str,
    target_tier: str,
    billed_mtd: float,
) -> tuple[dict, float]:
    location = (disk.get("location") or "").strip()
    pricing = estimate_disk_tier_savings(
        location,
        size_gb,
        sku_name,
        target_tier,
        actual_monthly_cost=billed_mtd if billed_mtd > 0 else None,
    )
    savings = savings_from_disk_pricing(pricing, billed_mtd=billed_mtd)
    return pricing, savings


def _confidence(disk: dict, rule_id: str, base: int, *, boost: int = 0) -> int:
    keys = metric_keys_for_rule(rule_id)
    if keys:
        return confidence_with_monitor(base, disk, required_keys=keys, boost=boost)
    return confidence_with_monitor(base, disk, boost=boost)


def analyze_disks(engine, subscription_id: str, disks: list[dict], cost_by_resource: dict[str, float]) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    thresholds = optimization_thresholds()
    rule = engine.rules["DISK_UNUSED_EXTENDED"]
    oversize_rule = engine.rules.get("DISK_OVERSIZE_EXTENDED")
    under_rule = engine.rules.get("DISK_UNDERPROVISIONED")

    unused_rec = rule_recommendation_text("DISK_UNUSED_EXTENDED") or (
        "Delete unused disks or snapshot only what must be retained for recovery requirements."
    )
    oversize_rec = rule_recommendation_text("DISK_OVERSIZE_EXTENDED") or (
        "Downgrade to Standard SSD or HDD if premium IOPS are not required."
    )
    under_rec = rule_recommendation_text("DISK_UNDERPROVISIONED") or (
        "Increase disk size (Premium) or move to Ultra SSD before applying cost reductions on this disk."
    )
    oversize_target = rule_target_tier("DISK_OVERSIZE_EXTENDED") or "StandardSSD_LRS"

    for disk in disks:
        props = disk.get("properties") or {}
        state = (props.get("diskState") or disk.get("state") or "").strip()
        size_gb = props.get("diskSizeGB") or 0
        from it_services.compute_disk.managed_disk_catalog import disk_sku_name

        sku_name = disk_sku_name(disk.get("sku"), props=props)
        sku_upper = sku_name.upper()
        est = resource_cost(cost_by_resource, disk.get("id", ""))

        if rule.enabled and state.lower() == "unattached":
            stale_ctx = evaluate_unattached_disk(disk, max_days=rule.max_unattached_disk_days)
            if not stale_ctx.is_stale:
                continue
            idle_io = is_idle_io(disk, max_bps=rule.disk_io_idle_bps)
            detail = (
                f"Disk '{disk.get('name')}' has been unattached for {stale_ctx.age_days} days "
                f"(threshold: {rule.max_unattached_disk_days} days)."
            )
            if stale_ctx.last_owner_name:
                detail += f" Last attached to '{stale_ctx.last_owner_name}'."
            elif stale_ctx.last_ownership_update:
                detail += " Last ownership change recorded in Azure."
            if idle_io is True:
                detail += (
                    f" Monitor metrics show combined I/O below {rule.disk_io_idle_bps:,.0f} B/s "
                    f"over the evaluation window."
                )
            out.append(engine._finding(
                rule=rule,
                subscription_id=subscription_id,
                resource=disk,
                detail=detail,
                recommendation=unused_rec,
                savings=est,
                waste_score=90 if stale_ctx.age_days and stale_ctx.age_days >= rule.max_unattached_disk_days * 2 else 86,
                confidence=_confidence(disk, "DISK_UNUSED_EXTENDED", 96, boost=4),
                priority="P1",
                impact="Direct storage cost reduction",
                evidence=augment_finding_evidence("DISK_UNUSED_EXTENDED", monitor_evidence(disk, augment_disk_evidence({
                    "disk_state": state,
                    "size_gb": size_gb,
                    "sku": sku_name,
                    "monthly_cost_usd": est,
                    "assessment_file": ASSESSMENT_FILE,
                    **staleness_evidence(stale_ctx),
                    **_disk_threshold_evidence(rule),
                }, props, disk_resource=disk))),
            ))
            continue

        if state.lower() != "attached":
            continue

        if (
            rule.enabled
            and size_gb
            and int(size_gb) >= rule.disk_idle_min_size_gb
            and disk_utilization_gate(disk, "disk_read_bps", "disk_write_bps", allow_inventory_only=True)
            and is_idle_io(disk, max_bps=rule.disk_io_idle_bps) is True
            and _peak_iops_allows_downgrade(disk)
            and not metrics_block_disk_downgrade(
                disk, disk, threshold_pct=rule.disk_iops_block_downgrade_pct,
            )
        ):
            pricing, savings = _tier_savings(
                disk,
                size_gb=size_gb,
                sku_name=sku_name or "Premium_LRS",
                target_tier=oversize_target,
                billed_mtd=est,
            )
            if savings > 0:
                out.append(engine._finding(
                    rule=rule,
                    subscription_id=subscription_id,
                    resource=disk,
                    detail=(
                        f"Disk '{disk.get('name')}' is attached but shows combined I/O below "
                        f"{rule.disk_io_idle_bps:,.0f} B/s — consider a lower performance tier."
                    ),
                    recommendation=unused_rec,
                    savings=savings,
                    waste_score=58,
                    confidence=_confidence(disk, "DISK_UNUSED_EXTENDED", 76),
                    priority="P3",
                    impact="Disk SKU optimization based on utilization",
                    evidence=augment_finding_evidence("DISK_UNUSED_EXTENDED", monitor_evidence(disk, {
                        "disk_state": state, "size_gb": size_gb, "sku": sku_name,
                        "monthly_cost_usd": est, **pricing, **disk_utilization_evidence(disk, disk),
                        **_disk_threshold_evidence(rule),
                    })),
                ))

        if (
            oversize_rule
            and oversize_rule.enabled
            and "PREMIUM" in sku_upper
            and disk_utilization_gate(disk, "disk_read_bps", "disk_write_bps", allow_inventory_only=True)
            and is_idle_io(disk, max_bps=oversize_rule.disk_io_idle_bps) is True
            and _peak_iops_allows_downgrade(disk)
            and not metrics_block_disk_downgrade(
                disk, disk, threshold_pct=oversize_rule.disk_iops_block_downgrade_pct,
            )
        ):
            pricing, savings = _tier_savings(
                disk,
                size_gb=size_gb,
                sku_name=sku_name or "Premium_LRS",
                target_tier=oversize_target,
                billed_mtd=est,
            )
            if savings > 0:
                out.append(engine._finding(
                    rule=oversize_rule,
                    subscription_id=subscription_id,
                    resource=disk,
                    detail=(
                        f"Disk '{disk.get('name')}' uses Premium SSD with combined I/O below "
                        f"{oversize_rule.disk_io_idle_bps:,.0f} B/s — consider Standard SSD."
                    ),
                    recommendation=oversize_rec,
                    savings=savings,
                    waste_score=48,
                    confidence=_confidence(disk, "DISK_OVERSIZE_EXTENDED", 72),
                    priority="P3",
                    impact="Premium-to-Standard disk tier savings",
                    evidence=augment_finding_evidence("DISK_OVERSIZE_EXTENDED", monitor_evidence(disk, {
                        "disk_state": state, "size_gb": size_gb, "sku": sku_name,
                        "monthly_cost_usd": est, **pricing, **disk_utilization_evidence(disk, disk),
                        **_disk_threshold_evidence(oversize_rule),
                    })),
                ))

        if (
            under_rule
            and under_rule.enabled
            and ("PREMIUM" in sku_upper or "ULTRA" in sku_upper)
            and disk_utilization_gate(disk, "disk_read_iops", "disk_write_iops", allow_inventory_only=True)
            and is_disk_underprovisioned(
                disk, disk, threshold_pct=under_rule.disk_iops_high_util_pct,
            ) is True
        ):
            util_evidence = disk_utilization_evidence(disk, disk)
            iops_util = util_evidence.get("disk_iops_utilization_pct")
            throughput_util = util_evidence.get("disk_throughput_utilization_pct")
            util_text = (
                f"{iops_util:.1f}% of provisioned IOPS"
                if iops_util is not None
                else f"{throughput_util:.1f}% of provisioned throughput"
            )
            out.append(engine._finding(
                rule=under_rule,
                subscription_id=subscription_id,
                resource=disk,
                detail=(
                    f"Disk '{disk.get('name')}' is using {util_text} over the evaluation window "
                    f"(threshold: {under_rule.disk_iops_high_util_pct:.0f}%) — "
                    "headroom is below the recommended 20–40% buffer."
                ),
                recommendation=under_rec,
                savings=0,
                waste_score=35,
                confidence=_confidence(disk, "DISK_UNDERPROVISIONED", 78),
                priority="P2",
                impact="Disk performance headroom",
                evidence=augment_finding_evidence("DISK_UNDERPROVISIONED", monitor_evidence(disk, {
                    "disk_state": state,
                    "size_gb": size_gb,
                    "sku": sku_name,
                    "monthly_cost_usd": est,
                    **util_evidence,
                    **_disk_threshold_evidence(under_rule),
                })),
            ))

        capacity_rule = engine.rules.get("DISK_CAPACITY_RIGHTSIZE_EXTENDED")
        queue_rule = engine.rules.get("DISK_QUEUE_DEPTH_EXTENDED")
        _append_metrics_draft(out, engine, subscription_id, disk, capacity_rule, evaluate_disk_capacity_rightsize(disk, est, capacity_rule))
        _append_metrics_draft(out, engine, subscription_id, disk, queue_rule, evaluate_disk_queue_depth(disk, est, queue_rule))

        grace_period_rule = engine.rules.get("DISK_NEW_GRACE_PERIOD")
        grace_days = grace_period_days()
        if grace_period_rule and grace_period_rule.enabled:
            time_created_str = props.get("timeCreated")
            if time_created_str:
                try:
                    time_created = datetime.fromisoformat(time_created_str.replace("Z", "+00:00"))
                    age_days = (datetime.now(timezone.utc) - time_created).days
                    if age_days < grace_days:
                        continue
                except (ValueError, TypeError):
                    pass

        ultra_rule_premium = engine.rules.get("DISK_ULTRA_DOWNGRADE_PREMIUM")
        ultra_rule_ssd = engine.rules.get("DISK_ULTRA_DOWNGRADE_SSD")
        ultra_premium_th = rule_utilization_thresholds("DISK_ULTRA_DOWNGRADE_PREMIUM")
        ultra_ssd_th = rule_utilization_thresholds("DISK_ULTRA_DOWNGRADE_SSD")

        if state.lower() == "attached" and "ULTRA" in sku_upper and disk_utilization_gate(disk, "disk_read_iops", "disk_write_iops"):
            util_evidence = disk_utilization_evidence(disk, disk)
            iops_util = util_evidence.get("disk_iops_utilization_pct")
            throughput_util = util_evidence.get("disk_throughput_utilization_pct")

            if (
                ultra_rule_premium
                and ultra_rule_premium.enabled
                and iops_util is not None
                and iops_util < ultra_premium_th["iops_pct"]
                and (throughput_util is None or throughput_util < ultra_premium_th["throughput_pct"])
            ):
                target = rule_target_tier("DISK_ULTRA_DOWNGRADE_PREMIUM") or "Premium_LRS"
                pricing, savings = _tier_savings(
                    disk, size_gb=size_gb, sku_name=sku_name or "UltraSSD_LRS",
                    target_tier=target, billed_mtd=est,
                )
                if savings >= ultra_premium_th["min_savings"]:
                    out.append(engine._finding(
                        rule=ultra_rule_premium,
                        subscription_id=subscription_id,
                        resource=disk,
                        detail=(
                            f"Disk '{disk.get('name')}' uses UltraSSD with IOPS utilization {iops_util:.1f}% "
                            f"— Premium SSD is more cost-effective."
                        ),
                        recommendation=rule_recommendation_text("DISK_ULTRA_DOWNGRADE_PREMIUM") or (
                            "Downgrade Ultra SSD to Premium SSD"
                        ),
                        savings=savings,
                        waste_score=72,
                        confidence=_confidence(disk, "DISK_ULTRA_DOWNGRADE_PREMIUM", 85),
                        priority="P2",
                        impact="Ultra→Premium disk tier savings",
                        evidence=augment_finding_evidence("DISK_ULTRA_DOWNGRADE_PREMIUM", monitor_evidence(disk, {
                            "disk_state": state, "size_gb": size_gb, "sku": sku_name,
                            "monthly_cost_usd": est, **pricing, **util_evidence,
                            **_disk_threshold_evidence(ultra_rule_premium),
                        })),
                    ))

            elif (
                ultra_rule_ssd
                and ultra_rule_ssd.enabled
                and iops_util is not None
                and iops_util < ultra_ssd_th["iops_pct"]
                and (throughput_util is None or throughput_util < ultra_ssd_th["throughput_pct"])
            ):
                target = rule_target_tier("DISK_ULTRA_DOWNGRADE_SSD") or "StandardSSD_LRS"
                pricing, savings = _tier_savings(
                    disk, size_gb=size_gb, sku_name=sku_name or "UltraSSD_LRS",
                    target_tier=target, billed_mtd=est,
                )
                if savings >= ultra_ssd_th["min_savings"]:
                    out.append(engine._finding(
                        rule=ultra_rule_ssd,
                        subscription_id=subscription_id,
                        resource=disk,
                        detail=(
                            f"Disk '{disk.get('name')}' uses UltraSSD with very low utilization {iops_util:.1f}% "
                            f"— workload can be served by Standard SSD."
                        ),
                        recommendation=rule_recommendation_text("DISK_ULTRA_DOWNGRADE_SSD") or (
                            "Downgrade Ultra SSD to Standard SSD"
                        ),
                        savings=savings,
                        waste_score=78,
                        confidence=_confidence(disk, "DISK_ULTRA_DOWNGRADE_SSD", 82),
                        priority="P2",
                        impact="Ultra→StandardSSD disk tier savings",
                        evidence=augment_finding_evidence("DISK_ULTRA_DOWNGRADE_SSD", monitor_evidence(disk, {
                            "disk_state": state, "size_gb": size_gb, "sku": sku_name,
                            "monthly_cost_usd": est, **pricing, **util_evidence,
                            **_disk_threshold_evidence(ultra_rule_ssd),
                        })),
                    ))

        premium_hdd_rule = engine.rules.get("DISK_PREMIUM_DOWNGRADE_HDD")
        premium_hdd_th = rule_utilization_thresholds("DISK_PREMIUM_DOWNGRADE_HDD")
        if (
            premium_hdd_rule
            and premium_hdd_rule.enabled
            and "PREMIUM" in sku_upper
            and state.lower() == "unattached"
            and disk_utilization_gate(disk, "disk_read_iops", "disk_write_iops")
        ):
            util_evidence = disk_utilization_evidence(disk, disk)
            iops_util = util_evidence.get("disk_iops_utilization_pct")
            throughput_util = util_evidence.get("disk_throughput_utilization_pct")

            if (
                iops_util is not None
                and iops_util < premium_hdd_th["iops_pct"]
                and (throughput_util is None or throughput_util < premium_hdd_th["throughput_pct"])
            ):
                target = rule_target_tier("DISK_PREMIUM_DOWNGRADE_HDD") or "Standard_LRS"
                pricing, savings = _tier_savings(
                    disk, size_gb=size_gb, sku_name=sku_name or "Premium_LRS",
                    target_tier=target, billed_mtd=est,
                )
                if savings >= premium_hdd_th["min_savings"]:
                    out.append(engine._finding(
                        rule=premium_hdd_rule,
                        subscription_id=subscription_id,
                        resource=disk,
                        detail=(
                            f"Unattached Premium disk '{disk.get('name')}' with minimal measured I/O "
                            f"({iops_util:.1f}% of provisioned) — Standard HDD provides full compatibility at lower cost."
                        ),
                        recommendation=rule_recommendation_text("DISK_PREMIUM_DOWNGRADE_HDD") or (
                            "Downgrade unattached Premium to Standard HDD"
                        ),
                        savings=savings,
                        waste_score=62,
                        confidence=_confidence(disk, "DISK_PREMIUM_DOWNGRADE_HDD", 79),
                        priority="P3",
                        impact="Premium→Standard disk tier savings",
                        evidence=augment_finding_evidence("DISK_PREMIUM_DOWNGRADE_HDD", monitor_evidence(disk, {
                            "disk_state": state, "size_gb": size_gb, "sku": sku_name,
                            "monthly_cost_usd": est, **pricing, **util_evidence,
                            **_disk_threshold_evidence(premium_hdd_rule),
                        })),
                    ))

        ssd_hdd_rule = engine.rules.get("DISK_SSD_DOWNGRADE_HDD")
        ssd_hdd_th = rule_utilization_thresholds("DISK_SSD_DOWNGRADE_HDD")
        if ssd_hdd_rule and ssd_hdd_rule.enabled and "STANDARDSSD" in sku_upper and disk_utilization_gate(disk, "disk_read_iops", "disk_write_iops"):
            util_evidence = disk_utilization_evidence(disk, disk)
            iops_util = util_evidence.get("disk_iops_utilization_pct")
            throughput_util = util_evidence.get("disk_throughput_utilization_pct")

            if (
                iops_util is not None
                and iops_util < ssd_hdd_th["iops_pct"]
                and (throughput_util is None or throughput_util < ssd_hdd_th["throughput_pct"])
            ):
                target = rule_target_tier("DISK_SSD_DOWNGRADE_HDD") or "Standard_LRS"
                pricing, savings = _tier_savings(
                    disk, size_gb=size_gb, sku_name=sku_name or "StandardSSD_LRS",
                    target_tier=target, billed_mtd=est,
                )
                if savings >= ssd_hdd_th["min_savings"]:
                    out.append(engine._finding(
                        rule=ssd_hdd_rule,
                        subscription_id=subscription_id,
                        resource=disk,
                        detail=(
                            f"Disk '{disk.get('name')}' uses StandardSSD but I/O profile matches Standard HDD "
                            f"capabilities ({iops_util:.1f}% utilization)."
                        ),
                        recommendation=rule_recommendation_text("DISK_SSD_DOWNGRADE_HDD") or (
                            "Downgrade Standard SSD to Standard HDD"
                        ),
                        savings=savings,
                        waste_score=48,
                        confidence=_confidence(disk, "DISK_SSD_DOWNGRADE_HDD", 74),
                        priority="P3",
                        impact="StandardSSD→Standard disk tier savings",
                        evidence=augment_finding_evidence("DISK_SSD_DOWNGRADE_HDD", monitor_evidence(disk, {
                            "disk_state": state, "size_gb": size_gb, "sku": sku_name,
                            "monthly_cost_usd": est, **pricing, **util_evidence,
                            **_disk_threshold_evidence(ssd_hdd_rule),
                        })),
                    ))

    return out

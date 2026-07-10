"""Managed Disks optimization analysis rules."""
from __future__ import annotations

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
    check_metric_staleness,
    metrics_status,
)
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import is_idle_io
from app.resource_utilization import monitor_evidence
from app.resource_utilization import utilization_gate
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
        evidence=draft.evidence,
    ))


def _disk_threshold_evidence(rule) -> dict[str, float | int]:
    """Persist rule thresholds on findings for evidence tables and overrides."""
    return {
        key: getattr(rule, key)
        for key in (
            "max_unattached_disk_days",
            "disk_io_idle_bps",
            "disk_idle_min_size_gb",
            "disk_iops_block_downgrade_pct",
            "disk_iops_high_util_pct",
            "evaluation_window_days",
        )
        if getattr(rule, key, None) is not None
    }


def _peak_iops_allows_downgrade(disk: dict, *, threshold_pct: float = 50.0) -> bool:
    """Only downgrade when peak IOPS stay below threshold of provisioned capacity."""
    peak_util = peak_disk_iops_utilization_pct(disk, disk)
    if peak_util is None:
        return True
    return peak_util < threshold_pct


def analyze_disks(engine, subscription_id: str, disks: list[dict], cost_by_resource: dict[str, float]) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules["DISK_UNUSED_EXTENDED"]
    oversize_rule = engine.rules.get("DISK_OVERSIZE_EXTENDED")
    under_rule = engine.rules.get("DISK_UNDERPROVISIONED")
    for disk in disks:
        props = disk.get("properties") or {}
        state = (props.get("diskState") or disk.get("state") or "").strip()
        size_gb = props.get("diskSizeGB") or 0
        sku_name = ((disk.get("sku") or {}).get("name") or "")
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
                recommendation="Delete unused disks or snapshot only what must be retained for recovery requirements.",
                savings=est,
                waste_score=90 if stale_ctx.age_days and stale_ctx.age_days >= rule.max_unattached_disk_days * 2 else 86,
                confidence=confidence_with_monitor(96, disk, boost=4),
                priority="P1",
                impact="Direct storage cost reduction",
                evidence=monitor_evidence(disk, augment_disk_evidence({
                    "disk_state": state,
                    "size_gb": size_gb,
                    "sku": sku_name,
                    "monthly_cost_usd": est,
                    **staleness_evidence(stale_ctx),
                    **_disk_threshold_evidence(rule),
                }, props, disk_resource=disk)),
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
            and _peak_iops_allows_downgrade(disk, threshold_pct=50.0)
            and not metrics_block_disk_downgrade(
                disk, disk, threshold_pct=rule.disk_iops_block_downgrade_pct,
            )
        ):
            location = (disk.get("location") or "").strip()
            pricing = estimate_disk_tier_savings(
                location,
                size_gb,
                sku_name or "Premium_LRS",
                "StandardSSD_LRS",
                actual_monthly_cost=est if est > 0 else None,
            )
            savings = savings_from_disk_pricing(pricing, billed_mtd=est)
            if savings > 0:
                out.append(engine._finding(
                    rule=rule,
                    subscription_id=subscription_id,
                    resource=disk,
                    detail=(
                        f"Disk '{disk.get('name')}' is attached but shows combined I/O below "
                        f"{rule.disk_io_idle_bps:,.0f} B/s — consider a lower performance tier."
                    ),
                    recommendation="Move to Standard SSD or HDD if premium IOPS are not required, or detach if unused.",
                    savings=savings,
                    waste_score=58,
                    confidence=confidence_with_monitor(
                        76, disk, required_keys=("disk_read_bps", "disk_write_bps"),
                    ),
                    priority="P3",
                    impact="Disk SKU optimization based on utilization",
                    evidence=monitor_evidence(disk, {
                        "disk_state": state, "size_gb": size_gb, "sku": sku_name,
                        "monthly_cost_usd": est, **pricing, **disk_utilization_evidence(disk, disk),
                        **_disk_threshold_evidence(rule),
                    }),
                ))

        if (
            oversize_rule
            and oversize_rule.enabled
            and "PREMIUM" in sku_upper
            and disk_utilization_gate(disk, "disk_read_bps", "disk_write_bps", allow_inventory_only=True)
            and is_idle_io(disk, max_bps=oversize_rule.disk_io_idle_bps) is True
            and _peak_iops_allows_downgrade(disk, threshold_pct=50.0)
            and not metrics_block_disk_downgrade(
                disk, disk, threshold_pct=oversize_rule.disk_iops_block_downgrade_pct,
            )
        ):
            location = (disk.get("location") or "").strip()
            pricing = estimate_disk_tier_savings(
                location,
                size_gb,
                sku_name or "Premium_LRS",
                "StandardSSD_LRS",
                actual_monthly_cost=est if est > 0 else None,
            )
            savings = savings_from_disk_pricing(pricing, billed_mtd=est)
            if savings > 0:
                out.append(engine._finding(
                    rule=oversize_rule,
                    subscription_id=subscription_id,
                    resource=disk,
                    detail=(
                        f"Disk '{disk.get('name')}' uses Premium SSD with combined I/O below "
                        f"{oversize_rule.disk_io_idle_bps:,.0f} B/s — consider Standard SSD."
                    ),
                    recommendation="Downgrade to Standard SSD or HDD if premium IOPS are not required.",
                    savings=savings,
                    waste_score=48,
                    confidence=confidence_with_monitor(
                        72, disk, required_keys=("disk_read_bps", "disk_write_bps"),
                    ),
                    priority="P3",
                    impact="Premium-to-Standard disk tier savings",
                    evidence=monitor_evidence(disk, {
                        "disk_state": state, "size_gb": size_gb, "sku": sku_name,
                        "monthly_cost_usd": est, **pricing, **disk_utilization_evidence(disk, disk),
                        **_disk_threshold_evidence(oversize_rule),
                    }),
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
                recommendation="Increase disk size (Premium) or move to Ultra SSD before applying cost reductions on this disk.",
                savings=0,
                waste_score=35,
                confidence=confidence_with_monitor(
                    78, disk, required_keys=("disk_read_iops", "disk_write_iops"),
                ),
                priority="P2",
                impact="Disk performance headroom",
                evidence=monitor_evidence(disk, {
                    "disk_state": state,
                    "size_gb": size_gb,
                    "sku": sku_name,
                    "monthly_cost_usd": est,
                    **util_evidence,
                    **_disk_threshold_evidence(under_rule),
                }),
            ))

        capacity_rule = engine.rules.get("DISK_CAPACITY_RIGHTSIZE_EXTENDED")
        queue_rule = engine.rules.get("DISK_QUEUE_DEPTH_EXTENDED")
        _append_metrics_draft(out, engine, subscription_id, disk, capacity_rule, evaluate_disk_capacity_rightsize(disk, est, capacity_rule))
        _append_metrics_draft(out, engine, subscription_id, disk, queue_rule, evaluate_disk_queue_depth(disk, est, queue_rule))

        # NEW RULES - Comprehensive tier downgrade analysis

        # Skip all optimization for very new disks (grace period)
        grace_period_rule = engine.rules.get("DISK_NEW_GRACE_PERIOD")
        if grace_period_rule and grace_period_rule.enabled:
            from datetime import datetime, timezone, timedelta
            time_created_str = (disk.get("properties") or {}).get("timeCreated")
            if time_created_str:
                try:
                    time_created = datetime.fromisoformat(time_created_str.replace('Z', '+00:00'))
                    age_days = (datetime.now(timezone.utc) - time_created).days
                    if age_days < 7:
                        # Skip to next disk - too new for recommendations
                        continue
                except (ValueError, TypeError):
                    pass

        # UltraSSD downgrade rules
        ultra_rule_premium = engine.rules.get("DISK_ULTRA_DOWNGRADE_PREMIUM")
        ultra_rule_ssd = engine.rules.get("DISK_ULTRA_DOWNGRADE_SSD")

        if state.lower() == "attached" and "ULTRA" in sku_upper and disk_utilization_gate(disk, "disk_read_iops", "disk_write_iops"):
            util_evidence = disk_utilization_evidence(disk, disk)
            iops_util = util_evidence.get("disk_iops_utilization_pct")
            throughput_util = util_evidence.get("disk_throughput_utilization_pct")

            # Try UltraSSD → Premium downgrade
            if ultra_rule_premium and ultra_rule_premium.enabled and iops_util is not None and iops_util < 50.0 and (throughput_util is None or throughput_util < 50.0):
                location = (disk.get("location") or "").strip()
                pricing = estimate_disk_tier_savings(
                    location, size_gb, sku_name or "UltraSSD_LRS", "Premium_LRS",
                    actual_monthly_cost=est if est > 0 else None,
                )
                savings = savings_from_disk_pricing(pricing, billed_mtd=est)
                if savings >= 50:  # Minimum $50/month
                    out.append(engine._finding(
                        rule=ultra_rule_premium,
                        subscription_id=subscription_id,
                        resource=disk,
                        detail=(
                            f"Disk '{disk.get('name')}' uses UltraSSD with IOPS utilization {iops_util:.1f}% "
                            f"(50% below 160,000 baseline) — Premium SSD is more cost-effective."
                        ),
                        recommendation=(
                            "1. Create snapshot of UltraSSD disk for backup\n"
                            "2. Create Premium_LRS disk from snapshot\n"
                            "3. Detach UltraSSD from VM\n"
                            "4. Attach Premium_LRS disk to VM\n"
                            "5. Delete UltraSSD after 30-day retention"
                        ),
                        savings=savings,
                        waste_score=72,
                        confidence=confidence_with_monitor(85, disk, required_keys=("disk_read_iops", "disk_write_iops")),
                        priority="P2",
                        impact="Ultra→Premium disk tier savings",
                        evidence=monitor_evidence(disk, {
                            "disk_state": state, "size_gb": size_gb, "sku": sku_name,
                            "monthly_cost_usd": est, **pricing, **util_evidence, **_disk_threshold_evidence(ultra_rule_premium),
                        }),
                    ))

            # Try UltraSSD → StandardSSD downgrade (more aggressive)
            elif ultra_rule_ssd and ultra_rule_ssd.enabled and iops_util is not None and iops_util < 30.0 and (throughput_util is None or throughput_util < 30.0):
                location = (disk.get("location") or "").strip()
                pricing = estimate_disk_tier_savings(
                    location, size_gb, sku_name or "UltraSSD_LRS", "StandardSSD_LRS",
                    actual_monthly_cost=est if est > 0 else None,
                )
                savings = savings_from_disk_pricing(pricing, billed_mtd=est)
                if savings >= 100:  # Minimum $100/month
                    out.append(engine._finding(
                        rule=ultra_rule_ssd,
                        subscription_id=subscription_id,
                        resource=disk,
                        detail=(
                            f"Disk '{disk.get('name')}' uses UltraSSD with very low utilization {iops_util:.1f}% "
                            f"— workload can be served by StandardSSD (500 IOPS, 60 MB/s)."
                        ),
                        recommendation=(
                            "1. Create snapshot of UltraSSD disk\n"
                            "2. Create StandardSSD_LRS disk from snapshot\n"
                            "3. Detach UltraSSD from VM\n"
                            "4. Attach StandardSSD_LRS disk to VM\n"
                            "5. Verify I/O performance is acceptable\n"
                            "6. Delete UltraSSD after 30-day retention"
                        ),
                        savings=savings,
                        waste_score=78,
                        confidence=confidence_with_monitor(82, disk, required_keys=("disk_read_iops", "disk_write_iops")),
                        priority="P2",
                        impact="Ultra→StandardSSD disk tier savings",
                        evidence=monitor_evidence(disk, {
                            "disk_state": state, "size_gb": size_gb, "sku": sku_name,
                            "monthly_cost_usd": est, **pricing, **util_evidence, **_disk_threshold_evidence(ultra_rule_ssd),
                        }),
                    ))

        # Premium → Standard HDD downgrade (unattached only - safer)
        premium_hdd_rule = engine.rules.get("DISK_PREMIUM_DOWNGRADE_HDD")
        if (premium_hdd_rule and premium_hdd_rule.enabled and "PREMIUM" in sku_upper and
            state.lower() == "unattached" and disk_utilization_gate(disk, "disk_read_iops", "disk_write_iops")):
            util_evidence = disk_utilization_evidence(disk, disk)
            iops_util = util_evidence.get("disk_iops_utilization_pct")
            throughput_util = util_evidence.get("disk_throughput_utilization_pct")

            if iops_util is not None and iops_util < 15.0 and (throughput_util is None or throughput_util < 15.0):
                location = (disk.get("location") or "").strip()
                pricing = estimate_disk_tier_savings(
                    location, size_gb, sku_name or "Premium_LRS", "Standard_LRS",
                    actual_monthly_cost=est if est > 0 else None,
                )
                savings = savings_from_disk_pricing(pricing, billed_mtd=est)
                if savings >= 10:  # Minimum $10/month
                    out.append(engine._finding(
                        rule=premium_hdd_rule,
                        subscription_id=subscription_id,
                        resource=disk,
                        detail=(
                            f"Unattached Premium disk '{disk.get('name')}' with minimal measured I/O "
                            f"({iops_util:.1f}% of provisioned) — Standard HDD provides full compatibility at lower cost."
                        ),
                        recommendation=(
                            "1. Create snapshot of Premium disk for backup\n"
                            "2. Create Standard_LRS disk from snapshot\n"
                            "3. Store for potential reattachment if needed\n"
                            "4. Delete Premium disk after retention period"
                        ),
                        savings=savings,
                        waste_score=62,
                        confidence=confidence_with_monitor(79, disk, required_keys=("disk_read_iops", "disk_write_iops")),
                        priority="P3",
                        impact="Premium→Standard disk tier savings",
                        evidence=monitor_evidence(disk, {
                            "disk_state": state, "size_gb": size_gb, "sku": sku_name,
                            "monthly_cost_usd": est, **pricing, **util_evidence, **_disk_threshold_evidence(premium_hdd_rule),
                        }),
                    ))

        # StandardSSD → Standard HDD downgrade
        ssd_hdd_rule = engine.rules.get("DISK_SSD_DOWNGRADE_HDD")
        if ssd_hdd_rule and ssd_hdd_rule.enabled and "STANDARDSSD" in sku_upper and disk_utilization_gate(disk, "disk_read_iops", "disk_write_iops"):
            util_evidence = disk_utilization_evidence(disk, disk)
            iops_util = util_evidence.get("disk_iops_utilization_pct")
            throughput_util = util_evidence.get("disk_throughput_utilization_pct")

            if iops_util is not None and iops_util < 20.0 and (throughput_util is None or throughput_util < 20.0):
                location = (disk.get("location") or "").strip()
                pricing = estimate_disk_tier_savings(
                    location, size_gb, sku_name or "StandardSSD_LRS", "Standard_LRS",
                    actual_monthly_cost=est if est > 0 else None,
                )
                savings = savings_from_disk_pricing(pricing, billed_mtd=est)
                if savings >= 2:  # Minimum $2/month
                    out.append(engine._finding(
                        rule=ssd_hdd_rule,
                        subscription_id=subscription_id,
                        resource=disk,
                        detail=(
                            f"Disk '{disk.get('name')}' uses StandardSSD but I/O profile matches Standard HDD "
                            f"capabilities ({iops_util:.1f}% utilization, {throughput_util or 'N/A'} MB/s)."
                        ),
                        recommendation=(
                            "1. Create snapshot of StandardSSD disk\n"
                            "2. Create Standard_LRS disk from snapshot\n"
                            "3. Detach StandardSSD from VM (if attached)\n"
                            "4. Attach Standard_LRS disk to VM\n"
                            "5. Verify application performance\n"
                            "6. Delete StandardSSD after retention period"
                        ),
                        savings=savings,
                        waste_score=48,
                        confidence=confidence_with_monitor(74, disk, required_keys=("disk_read_iops", "disk_write_iops")),
                        priority="P3",
                        impact="StandardSSD→Standard disk tier savings",
                        evidence=monitor_evidence(disk, {
                            "disk_state": state, "size_gb": size_gb, "sku": sku_name,
                            "monthly_cost_usd": est, **pricing, **util_evidence, **_disk_threshold_evidence(ssd_hdd_rule),
                        }),
                    ))

    return out

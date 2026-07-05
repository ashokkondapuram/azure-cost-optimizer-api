"""Managed Disks optimization analysis rules."""
from __future__ import annotations

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.azure_retail_pricing import estimate_disk_tier_savings
from app.disk_staleness import augment_disk_evidence
from app.disk_staleness import evaluate_unattached_disk
from app.disk_staleness import staleness_evidence
from app.disk_utilization import (
    disk_utilization_evidence,
    is_disk_underprovisioned,
    metrics_block_disk_downgrade,
    peak_disk_iops_utilization_pct,
)
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import is_idle_io
from app.resource_utilization import monitor_evidence
from app.resource_utilization import utilization_gate


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
            and utilization_gate(disk, "disk_read_bps", "disk_write_bps", allow_inventory_only=False)
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
            savings = savings_from_retail_or_none(pricing)
            if savings is not None and savings > 0:
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
            and utilization_gate(disk, "disk_read_bps", "disk_write_bps", allow_inventory_only=False)
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
            savings = savings_from_retail_or_none(pricing)
            if savings is not None and savings > 0:
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
            and utilization_gate(disk, "disk_read_iops", "disk_write_iops", allow_inventory_only=False)
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
    return out

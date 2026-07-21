"""Managed disk optimization decision rules — capacity and queue depth metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.compute_pricing import estimate_disk_capacity_savings
from app.managed_disk_catalog import parse_disk_arm
from it_services.compute_disk.assessment_bridge import (
    augment_finding_evidence,
    rule_recommendation_text,
)
from it_services.compute_disk.managed_disk_catalog import optimization_thresholds
from app.resource_utilization import (
    confidence_with_monitor,
    fact_value,
    make_check,
    monitor_facts_status,
    structured_evidence,
)


@dataclass(frozen=True)
class ComputeFindingDraft:
    rule_id: str
    detail: str
    recommendation: str
    savings: float
    waste_score: int
    confidence: int
    priority: str
    impact: str
    evidence: dict[str, Any]


def _thresholds(rule: Any) -> dict[str, float]:
    defaults = optimization_thresholds()
    return {
        "capacity_used_pct_max": float(
            getattr(rule, "disk_capacity_used_pct_max", defaults.get("capacity_used_pct_max", 30.0))
        ),
        "queue_depth": float(getattr(rule, "disk_queue_depth_contention", defaults.get("disk_queue_depth_contention", 10.0))),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 3.0))),
    }


def evaluate_disk_capacity_rightsize(
    disk: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> ComputeFindingDraft | None:
    ctx = parse_disk_arm(disk)
    if ctx["disk_state"].lower() != "attached" or not ctx["size_gb"]:
        return None
    th = _thresholds(rule)
    if monitor_facts_status(disk, "disk_used_pct") != "available":
        return None
    used_pct = fact_value(disk, "disk_used_pct")
    if used_pct is None or float(used_pct) > th["capacity_used_pct_max"]:
        return None
    name = disk.get("name") or ""
    savings = estimate_disk_capacity_savings(
        monthly_cost,
        ctx["size_gb"],
        ctx["sku_name"],
        savings_factor=0.25,
        min_savings=th["min_savings"],
    )
    return ComputeFindingDraft(
        rule_id="DISK_CAPACITY_RIGHTSIZE_EXTENDED",
        detail=(
            f"Disk '{name}' ({ctx['size_gb']} GB {ctx['sku_name']}) uses only "
            f"{float(used_pct):.1f}% of provisioned capacity."
        ),
        recommendation=rule_recommendation_text("DISK_CAPACITY_RIGHTSIZE_EXTENDED") or (
            "Downsize disk to the next smaller SKU tier after confirming growth headroom requirements."
        ),
        savings=savings,
        waste_score=52,
        confidence=confidence_with_monitor(74, disk),
        priority="P3",
        impact="Capacity right-sizing reduces monthly disk charges",
        evidence=augment_finding_evidence(
            "DISK_CAPACITY_RIGHTSIZE_EXTENDED",
            structured_evidence(
            disk,
            determination="low_capacity_utilization",
            summary="Provisioned disk size exceeds measured utilization.",
            checks=[
                make_check("Used capacity %", used_pct, f"<= {th['capacity_used_pct_max']:.0f}%", passed=True),
                make_check("Provisioned size (GB)", ctx["size_gb"], "Review", passed=True),
            ],
            extra={"sku": ctx["sku_name"], "monthly_cost_usd": monthly_cost},
        ),
        ),
    )


def evaluate_disk_queue_depth(
    disk: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> ComputeFindingDraft | None:
    ctx = parse_disk_arm(disk)
    if ctx["disk_state"].lower() != "attached":
        return None
    th = _thresholds(rule)
    if monitor_facts_status(disk, "disk_queue_depth") != "available":
        return None
    depth = fact_value(disk, "disk_queue_depth")
    if depth is None or float(depth) <= th["queue_depth"]:
        return None
    name = disk.get("name") or ""
    return ComputeFindingDraft(
        rule_id="DISK_QUEUE_DEPTH_EXTENDED",
        detail=(
            f"Disk '{name}' shows queue depth of {float(depth):.1f} "
            f"(threshold {th['queue_depth']:.0f}) — I/O contention risk."
        ),
        recommendation=rule_recommendation_text("DISK_QUEUE_DEPTH_EXTENDED") or (
            "Investigate I/O patterns before tier downgrade — consider Premium SSD or disk caching improvements."
        ),
        savings=0.0,
        waste_score=64,
        confidence=confidence_with_monitor(82, disk),
        priority="P1",
        impact="Prevent conflicting storage recommendations when I/O is saturated",
        evidence=augment_finding_evidence(
            "DISK_QUEUE_DEPTH_EXTENDED",
            structured_evidence(
            disk,
            determination="disk_queue_contention",
            summary="Disk queue depth indicates I/O contention.",
            checks=[
                make_check("Queue depth", depth, f"> {th['queue_depth']:.0f}", passed=True),
            ],
            extra={"sku": ctx["sku_name"], "monthly_cost_usd": monthly_cost},
        ),
        ),
    )

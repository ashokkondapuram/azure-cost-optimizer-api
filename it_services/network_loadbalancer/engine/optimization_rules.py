"""Load Balancer optimization decision rules — SNAT and throughput intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.network_pricing import (
    estimate_decommission_savings,
    estimate_load_balancer_hourly,
    estimate_rightsizing_savings,
)
from app.load_balancer_catalog import basic_sku_retirement_date, optimization_thresholds, parse_load_balancer_arm
from app.resource_utilization import (
    confidence_with_monitor,
    fact_value,
    is_low_traffic,
    make_check,
    monitor_evidence,
    structured_evidence,
)


@dataclass(frozen=True)
class NetworkFindingDraft:
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
        "snat_pressure_pct": float(getattr(rule, "lb_snat_pressure_pct", defaults.get("snat_pressure_pct", 70.0))),
        "throughput_low_pct": float(getattr(rule, "lb_throughput_low_pct_of_peak", defaults.get("throughput_low_pct_of_peak", 10.0))),
        "idle_bytes": float(getattr(rule, "lb_idle_byte_threshold", defaults.get("idle_byte_threshold", 1_000_000.0))),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 5.0))),
    }


def evaluate_lb_idle_no_backends(
    lb: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    if not ctx.get("all_backends_empty"):
        return None
    th = _thresholds(rule)
    low_traffic = is_low_traffic(lb, byte_threshold=th["idle_bytes"])
    name = lb.get("name") or ""
    detail = f"Load balancer '{name}' has backend pools with no active backend addresses."
    if low_traffic is True:
        detail += " Monitor metrics confirm negligible traffic volume."
    savings = estimate_decommission_savings(
        monthly_cost,
        hourly_usd=estimate_load_balancer_hourly(),
        min_savings=th["min_savings"],
    )
    return NetworkFindingDraft(
        rule_id="LOAD_BALANCER_IDLE_EXTENDED",
        detail=detail,
        recommendation="Delete idle load balancers or attach them to active backend resources.",
        savings=savings,
        waste_score=82,
        confidence=confidence_with_monitor(88, lb, boost=8 if low_traffic is True else 0),
        priority="P2",
        impact="Direct network cost reduction and cleaner topology",
        evidence={
            "determination": "idle_no_backends",
            "backend_pool_count": ctx.get("backend_pool_count"),
            "all_backends_empty": True,
            "sku": ctx.get("sku_name"),
            "monthly_cost_usd": monthly_cost,
            "checks": [
                {
                    "signal": "Backend pools with active targets",
                    "value": ctx.get("backend_pool_count"),
                    "threshold": "≥ 1 pool with backends",
                    "passed": False,
                    "status": "fail",
                },
            ],
            "summary": (
                f"Load balancer has {ctx.get('backend_pool_count')} backend pool(s) but none have "
                "active backend IP configurations or addresses."
            ),
            **monitor_evidence(lb),
        },
    )


def evaluate_lb_low_traffic(
    lb: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    if ctx.get("all_backends_empty"):
        return None
    th = _thresholds(rule)
    if is_low_traffic(lb, byte_threshold=th["idle_bytes"]) is not True:
        return None
    savings = estimate_rightsizing_savings(
        monthly_cost,
        savings_factor=0.5,
        hourly_usd=estimate_load_balancer_hourly(),
        min_savings=th["min_savings"],
    )
    name = lb.get("name") or ""
    return NetworkFindingDraft(
        rule_id="LOAD_BALANCER_BACKEND_CONSOLIDATION",
        detail=f"Load balancer '{name}' has backends configured but very low traffic in Azure Monitor.",
        recommendation="Consolidate workloads, remove unused backends, or delete the load balancer if no longer required.",
        savings=savings,
        waste_score=68,
        confidence=confidence_with_monitor(80, lb),
        priority="P3",
        impact="Network cost reduction for underutilized load balancer",
        evidence=monitor_evidence(lb, {
            "determination": "low_traffic",
            "backend_pool_count": ctx.get("backend_pool_count"),
            "monthly_cost_usd": monthly_cost,
        }),
    )


def evaluate_lb_snat_pressure(
    lb: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    snat_pct = fact_value(lb, "snat_port_usage_pct")
    if snat_pct is None or snat_pct < th["snat_pressure_pct"]:
        return None
    name = lb.get("name") or ""
    return NetworkFindingDraft(
        rule_id="LOAD_BALANCER_SNAT_PRESSURE",
        detail=f"Load balancer '{name}' SNAT port usage is {snat_pct:.0f}% — outbound connections may fail.",
        recommendation="Offload outbound SNAT to a NAT Gateway or add frontend/backend capacity per Azure guidance.",
        savings=0.0,
        waste_score=40,
        confidence=confidence_with_monitor(90, lb),
        priority="P1",
        impact="Prevent outbound connection exhaustion",
        evidence=structured_evidence(
            lb,
            determination="snat_pressure",
            summary="Load balancer SNAT port utilization exceeds safe threshold.",
            checks=[make_check("SNAT port usage %", snat_pct, f"≥ {th['snat_pressure_pct']:.0f}%", passed=True)],
            extra={"monthly_cost_usd": monthly_cost},
        ),
    )


def evaluate_lb_throughput_rightsize(
    lb: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    th = _thresholds(rule)
    avg_bytes = fact_value(lb, "byte_count")
    peak_bytes = fact_value(lb, "byte_count_peak")
    if avg_bytes is None or peak_bytes is None or peak_bytes <= 0:
        return None
    pct_of_peak = round(avg_bytes / peak_bytes * 100.0, 2)
    if pct_of_peak >= th["throughput_low_pct"]:
        return None
    savings = estimate_rightsizing_savings(
        monthly_cost,
        savings_factor=0.3,
        hourly_usd=estimate_load_balancer_hourly(),
        min_savings=th["min_savings"],
    )
    name = lb.get("name") or ""
    return NetworkFindingDraft(
        rule_id="LOAD_BALANCER_THROUGHPUT_RIGHTSIZE",
        detail=f"Load balancer '{name}' average throughput is {pct_of_peak:.0f}% of peak — likely over-provisioned.",
        recommendation="Review backend pool sizing, remove unused rules, or consolidate traffic to a smaller footprint.",
        savings=savings,
        waste_score=58,
        confidence=confidence_with_monitor(82, lb),
        priority="P2",
        impact="Reduce data processing charges",
        evidence=structured_evidence(
            lb,
            determination="throughput_rightsize",
            summary="Sustained throughput is far below peak utilization.",
            checks=[
                make_check("Avg vs peak bytes %", pct_of_peak, f"< {th['throughput_low_pct']:.0f}%", passed=True),
            ],
            extra={"byte_count_avg": avg_bytes, "byte_count_peak": peak_bytes, "monthly_cost_usd": monthly_cost},
        ),
    )


def evaluate_lb_basic_sku_migration(
    lb: dict[str, Any],
    ctx: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> NetworkFindingDraft | None:
    sku = (ctx.get("sku_name") or "").strip()
    if sku.lower() != "basic" and not ctx.get("sku_retiring"):
        return None
    name = lb.get("name") or ""
    target = ctx.get("migrate_to_sku") or "Standard"
    return NetworkFindingDraft(
        rule_id="LOAD_BALANCER_BASIC_SKU_MIGRATION",
        detail=f"Load balancer '{name}' uses Basic SKU, retiring on {basic_sku_retirement_date()}.",
        recommendation=f"Migrate to {target} SKU before retirement for SLA and feature continuity.",
        savings=0.0,
        waste_score=50,
        confidence=98,
        priority="P2",
        impact="Continuity before Basic SKU retirement",
        evidence=structured_evidence(
            lb,
            determination="basic_sku_migration",
            summary=f"Basic load balancer must migrate to {target}.",
            checks=[make_check("SKU", sku, "Basic", passed=True)],
            extra={"current_sku": sku, "target_sku": target, "monthly_cost_usd": monthly_cost},
        ),
    )

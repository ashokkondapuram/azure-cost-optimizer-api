"""ADX optimization decision rules — ingestion volume and cluster cost."""

from __future__ import annotations

from typing import Any

from app.resource_utilization import fact_value, make_check, monitor_facts_status, utilization_gate
from app.service_thresholds import threshold_values
from app.stub_engine_common import StubFindingDraft, cost_finding_draft, metric_finding_draft

_CANONICAL = "analytics/adx"


def _thresholds(rule: Any) -> dict[str, float]:
    return threshold_values(
        rule,
        _CANONICAL,
        min_cost="min_monthly_cost_usd",
        ingestion_low_mb="ingestion_low_mb",
        savings_factor="savings_factor",
        ingestion_savings_factor="ingestion_savings_factor",
        min_savings="min_monthly_savings_usd",
    )


def evaluate_adx_ingestion_cost(
    cluster: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    return cost_finding_draft(
        rule_id="ADX_INGESTION_EXTENDED",
        resource=cluster,
        monthly=monthly_cost,
        detail_suffix="Review ingestion batching and retention policies.",
        recommendation=(
            "Review ingestion batching, retention policies, cache policy, "
            "and scale down dev/test clusters when idle."
        ),
        savings_factor=th["savings_factor"],
        waste_score=55,
        priority="P2",
        impact="Analytics compute cost optimization",
        min_savings=th["min_savings"],
    )


def evaluate_adx_low_ingestion(
    cluster: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> StubFindingDraft | None:
    th = _thresholds(rule)
    if monthly_cost < th["min_cost"]:
        return None
    if not utilization_gate(cluster, "ingestion_bytes", allow_inventory_only=False):
        return None
    ingestion = fact_value(cluster, "ingestion_bytes")
    if ingestion is None:
        return None
    ingestion_mb = float(ingestion)
    if ingestion_mb >= th["ingestion_low_mb"]:
        return None
    name = cluster.get("name") or ""
    return metric_finding_draft(
        rule_id="ADX_LOW_INGESTION_EXTENDED",
        resource=cluster,
        monthly=monthly_cost,
        detail=(
            f"ADX cluster '{name}' ingested {ingestion_mb:.1f} MB in the evaluation window "
            f"(threshold: {th['ingestion_low_mb']:.0f} MB)."
        ),
        recommendation="Scale down or stop dev/test clusters with low ingestion volume.",
        savings=monthly_cost * th["ingestion_savings_factor"] if monthly_cost > 0 else 0.0,
        waste_score=52,
        priority="P2",
        impact="Right-size ADX cluster capacity to ingestion volume",
        determination="low_ingestion",
        summary="ADX cluster ingestion is below optimization threshold.",
        checks=[make_check("Ingestion (MB)", round(ingestion_mb, 1), f"< {th['ingestion_low_mb']:.0f}", passed=True)],
        extra={"ingestion_mb": round(ingestion_mb, 2)},
        required_keys=("ingestion_bytes",),
    )

"""Storage account optimization decision rules — egress and cool tier migration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.compute_pricing import estimate_egress_savings, estimate_storage_tier_savings_fallback
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import (
    confidence_with_monitor,
    fact_value,
    is_low_request_volume,
    monitor_facts_status,
    structured_evidence,
)
from app.storage_account_catalog import access_tier_spec, optimization_thresholds
from app.service_display import (
    format_access_tier,
    format_bytes_threshold_gb,
    format_replication_sku,
    format_storage_fact,
    format_transaction_threshold,
    make_storage_check,
    storage_cool_tier_recommendation,
    storage_egress_recommendation,
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
        "egress_bytes": float(getattr(rule, "storage_egress_bytes_monthly", defaults.get("egress_bytes_monthly", 0))),
        "cool_after_days": float(getattr(rule, "storage_cool_after_days", defaults.get("cool_tier_days_since_access", 30.0))),
        "tx_low": float(getattr(rule, "storage_transaction_low", defaults.get("transaction_low_count", 5000.0))),
        "min_savings": float(getattr(rule, "min_monthly_savings_usd", defaults.get("min_monthly_savings_usd", 5.0))),
    }


def evaluate_storage_egress_high(
    acct: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> ComputeFindingDraft | None:
    th = _thresholds(rule)
    if th["egress_bytes"] <= 0:
        return None
    if monitor_facts_status(acct, "egress_bytes") != "available":
        return None
    egress = fact_value(acct, "egress_bytes")
    if egress is None or float(egress) < th["egress_bytes"]:
        return None
    name = acct.get("name") or ""
    egress_gb = float(egress) / (1024**3)
    savings = estimate_egress_savings(
        float(egress),
        monthly_cost,
        egress_factor=0.20,
        min_savings=th["min_savings"],
    )
    threshold_label = format_bytes_threshold_gb(th["egress_bytes"])
    return ComputeFindingDraft(
        rule_id="STORAGE_EGRESS_HIGH_EXTENDED",
        detail=(
            f"Storage account '{name}' transferred about {egress_gb:,.0f} GB of egress data "
            f"in the evaluation window (threshold: {threshold_label.replace('/month', '')})."
        ),
        recommendation=storage_egress_recommendation(),
        savings=savings,
        waste_score=52,
        confidence=confidence_with_monitor(75, acct),
        priority="P2",
        impact="High egress increases storage bandwidth cost",
        evidence=structured_evidence(
            acct,
            determination="high_egress",
            summary="Storage egress exceeds the monthly review threshold.",
            checks=[
                make_storage_check(
                    "Monthly egress",
                    "egress_bytes",
                    egress,
                    f"≥ {threshold_label}",
                    passed=True,
                ),
            ],
            extra={
                "egress_gb": round(egress_gb, 1),
                "egress_display": format_storage_fact("egress_bytes", egress),
                "monthly_cost_usd": monthly_cost,
            },
        ),
    )


def evaluate_storage_cool_tier_candidate(
    acct: dict[str, Any],
    monthly_cost: float,
    rule: Any,
) -> ComputeFindingDraft | None:
    th = _thresholds(rule)
    props = acct.get("properties") or {}
    tier = props.get("accessTier") or "Hot"
    if tier != "Hot":
        return None
    if monitor_facts_status(acct, "transaction_count") != "available":
        return None
    tx_value = fact_value(acct, "transaction_count")
    if is_low_request_volume(acct, threshold=th["tx_low"]) is not True:
        return None
    name = acct.get("name") or ""
    from app.azure_retail_pricing import estimate_service_tier_savings

    pricing = estimate_service_tier_savings(
        acct.get("location") or "",
        "Storage",
        "Hot",
        "Cool",
        cache_prefix="storage_tier",
        actual_monthly_cost=monthly_cost if monthly_cost > 0 else None,
    )
    savings = savings_from_retail_or_none(pricing) or 0.0
    hot_rate = access_tier_spec("Hot").get("per_gb_month_usd", 0.024)
    cool_rate = access_tier_spec("Cool").get("per_gb_month_usd", 0.012)
    savings_pct = int((1 - float(cool_rate) / float(hot_rate)) * 100) if hot_rate else 50
    if savings < th["min_savings"]:
        savings = estimate_storage_tier_savings_fallback(
            hot_rate_per_gb=float(hot_rate),
            cool_rate_per_gb=float(cool_rate),
            min_savings=th["min_savings"],
        )
    cool_days = int(th["cool_after_days"])
    tier_label = format_access_tier(tier)
    tx_threshold = format_transaction_threshold(th["tx_low"])
    return ComputeFindingDraft(
        rule_id="STORAGE_COOL_TIER_CANDIDATE_EXTENDED",
        detail=(
            f"Storage account '{name}' is on {tier_label} with low activity "
            f"({format_storage_fact('transaction_count', tx_value)}). "
            "Data may be infrequently accessed."
        ),
        recommendation=storage_cool_tier_recommendation(cool_days=cool_days, savings_pct=savings_pct),
        savings=savings,
        waste_score=46,
        confidence=confidence_with_monitor(68, acct),
        priority="P3",
        impact="Access tier optimization reduces blob storage cost for cold data",
        evidence=structured_evidence(
            acct,
            determination="cool_tier_candidate",
            summary="Hot tier storage with low activity is a Cool tier migration candidate.",
            checks=[
                make_storage_check("Access tier", "access_tier", tier, tier_label, passed=True),
                make_storage_check(
                    "Monthly transactions",
                    "transaction_count",
                    tx_value,
                    tx_threshold,
                    passed=True,
                ),
            ],
            extra={"access_tier": tier, "access_tier_display": tier_label, **(pricing or {})},
        ),
    )

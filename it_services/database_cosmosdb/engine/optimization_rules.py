"""Cosmos DB optimization decision rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.azure_retail_pricing import estimate_cosmos_throughput_savings
from app.cost_utils import savings_from_factor
from app.cosmosdb_catalog import load_cosmosdb_pricing_models, optimization_thresholds, parse_cosmos_arm_account
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import (
    confidence_with_monitor,
    fact_value,
    is_low_request_volume,
    make_check,
    metrics_block_rightsize,
    monitor_evidence,
    structured_evidence,
    utilization_gate,
)


@dataclass(frozen=True)
class CosmosFindingDraft:
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
        "ru_low_pct": float(getattr(rule, "cosmos_ru_low_pct", defaults.get("ru_low_pct", 20.0))),
        "ru_high_pct": float(getattr(rule, "cosmos_ru_high_pct", defaults.get("ru_high_pct", 80.0))),
        "ru_throttle_pct": float(getattr(rule, "cosmos_throttle_ru_pct", defaults.get("ru_throttle_pct", 95.0))),
        "serverless_ru_threshold": float(getattr(rule, "cosmos_serverless_ru_threshold", defaults.get("serverless_ru_threshold_7d", 50000.0))),
        "index_to_data_ratio": float(getattr(rule, "cosmos_index_to_data_ratio", defaults.get("index_to_data_ratio", 1.5))),
        "large_item_bytes": float(getattr(rule, "cosmos_large_item_bytes", defaults.get("large_item_bytes", 2097152.0))),
        "hot_partition_skew_ratio": float(getattr(rule, "cosmos_hot_partition_skew_ratio", defaults.get("hot_partition_skew_ratio", 2.5))),
        "replication_lag_ms": float(getattr(rule, "cosmos_replication_lag_ms", defaults.get("replication_lag_ms", 100.0))),
        "autoscale_util_pct": float(getattr(rule, "cosmos_autoscale_candidate_utilization_pct", 25.0)),
    }


def _passes_min_savings(rule: Any, savings: float) -> bool:
    min_savings = float(getattr(rule, "min_monthly_savings_usd", 0.0) or 0.0)
    return savings <= 0 or savings >= min_savings


def _env_tag(account: dict[str, Any], rule: Any) -> str:
    tags = account.get("tags") or {}
    return str(tags.get("environment") or tags.get("env") or "").lower()


def _is_nonprod(env: str, rule: Any) -> bool:
    return env in [v.lower() for v in getattr(rule, "nonprod_tag_values", ["dev", "test", "qa", "staging", "sandbox"])]


def _cosmos_metric_evidence(account: dict[str, Any], ctx: dict[str, Any], extra: dict | None = None) -> dict[str, Any]:
    payload = {
        **ctx,
        "request_count": fact_value(account, "request_count"),
        "total_ru": fact_value(account, "total_ru"),
        "normalized_ru_pct": fact_value(account, "normalized_ru_pct"),
        "normalized_ru_peak_pct": fact_value(account, "normalized_ru_peak_pct"),
        "provisioned_throughput": fact_value(account, "provisioned_throughput"),
        "data_usage_bytes": fact_value(account, "data_usage_bytes"),
        "index_usage_bytes": fact_value(account, "index_usage_bytes"),
        "document_count": fact_value(account, "document_count"),
        "replication_latency_ms": fact_value(account, "replication_latency_ms"),
        "server_latency_ms": fact_value(account, "server_latency_ms"),
    }
    base = monitor_evidence(account, payload)
    if extra:
        base.update(extra)
    return base


def _throughput_savings(account: dict[str, Any], monthly: float, target: str) -> tuple[float, dict[str, Any]]:
    pricing = estimate_cosmos_throughput_savings(
        account.get("location") or "",
        "provisioned",
        target,
        actual_monthly_cost=monthly if monthly > 0 else None,
    )
    savings = savings_from_retail_or_none(pricing)
    if savings is None and monthly > 0:
        savings = savings_from_factor(monthly, 0.30)
    return float(savings or 0.0), pricing


def evaluate_cosmos_provisioned_extended(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled or ctx.get("serverless_enabled"):
        return None
    name = account.get("name") or ""
    return CosmosFindingDraft(
        rule_id="COSMOS_PROVISIONED_EXTENDED",
        detail=f"Cosmos DB account '{name}' uses provisioned throughput without serverless capability.",
        recommendation="Evaluate autoscale or serverless for variable or low-throughput workloads.",
        savings=0.0,
        waste_score=38,
        confidence=68,
        priority="P3",
        impact="Potential RU/s cost optimization for low-volume accounts",
        evidence={"capabilities": ctx.get("capabilities"), "serverless_enabled": False, **ctx},
    )


def evaluate_cosmos_autoscale_extended(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled or ctx.get("serverless_enabled"):
        return None
    if metrics_block_rightsize(account):
        return None
    if not utilization_gate(account, "request_count", allow_inventory_only=False):
        return None
    thresholds = _thresholds(rule)
    normalized = fact_value(account, "normalized_ru_pct")
    requests = fact_value(account, "request_count")
    total_ru = fact_value(account, "total_ru")
    low_volume = is_low_request_volume(account, threshold=thresholds["serverless_ru_threshold"])
    low_util = normalized is not None and normalized <= thresholds["autoscale_util_pct"]
    if low_volume is not True and not low_util:
        return None
    savings, pricing = _throughput_savings(account, monthly, "serverless")
    if not _passes_min_savings(rule, savings):
        return None
    name = account.get("name") or ""
    detail = f"Cosmos DB account '{name}' shows low utilization in Azure Monitor."
    if normalized is not None:
        detail += f" Normalized RU consumption averages {normalized:.1f}%."
    return CosmosFindingDraft(
        rule_id="COSMOS_AUTOSCALE_EXTENDED",
        detail=detail,
        recommendation="Evaluate autoscale or serverless based on request volume variance and RU utilization.",
        savings=savings,
        waste_score=50,
        confidence=confidence_with_monitor(64, account, boost=16),
        priority="P3",
        impact="Potential RU/s spend optimization",
        evidence=structured_evidence(
            account,
            determination="autoscale_candidate",
            summary="Non-serverless Cosmos account shows low request or RU utilization.",
            checks=[
                make_check("Request count (7d)", requests, f"< {thresholds['serverless_ru_threshold']:,.0f}", passed=low_volume is True),
                make_check("Normalized RU %", normalized, f"≤ {thresholds['autoscale_util_pct']}%", passed=low_util),
                make_check("Total RU (7d)", total_ru, f"< {thresholds['serverless_ru_threshold']:,.0f}", passed=total_ru is not None and total_ru < thresholds["serverless_ru_threshold"]),
            ],
            extra={**pricing, **ctx},
        ),
    )


def evaluate_cosmos_serverless(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled or ctx.get("serverless_enabled"):
        return None
    if not utilization_gate(account, "total_ru", allow_inventory_only=False):
        return None
    thresholds = _thresholds(rule)
    total_ru = fact_value(account, "total_ru")
    if total_ru is None or total_ru >= thresholds["serverless_ru_threshold"]:
        return None
    savings, pricing = _throughput_savings(account, monthly, "serverless")
    if not _passes_min_savings(rule, savings):
        return None
    name = account.get("name") or ""
    return CosmosFindingDraft(
        rule_id="COSMOS_SERVERLESS",
        detail=f"Cosmos DB account '{name}' consumed {total_ru:,.0f} RUs in Azure Monitor — below the serverless threshold.",
        recommendation="Migrate to serverless throughput to pay per million RUs instead of fixed provisioned capacity.",
        savings=savings,
        waste_score=52,
        confidence=confidence_with_monitor(70, account, required_keys=("total_ru",)),
        priority="P2",
        impact="RU consumption cost optimization",
        evidence=_cosmos_metric_evidence(account, ctx, {**pricing, "determination": "serverless_candidate"}),
    )


def evaluate_cosmos_ru_rightsizing_under(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled or ctx.get("serverless_enabled"):
        return None
    if not utilization_gate(account, "normalized_ru_pct", allow_inventory_only=False):
        return None
    thresholds = _thresholds(rule)
    normalized = fact_value(account, "normalized_ru_pct")
    if normalized is None or normalized >= thresholds["ru_low_pct"]:
        return None
    provisioned = fact_value(account, "provisioned_throughput")
    savings = savings_from_factor(monthly, 0.35) if monthly > 0 else 0.0
    if not _passes_min_savings(rule, savings):
        return None
    name = account.get("name") or ""
    return CosmosFindingDraft(
        rule_id="COSMOS_RU_RIGHT_SIZING_UNDER",
        detail=f"Cosmos DB '{name}' normalized RU consumption is {normalized:.1f}% — below the {thresholds['ru_low_pct']:.0f}% threshold.",
        recommendation="Downscale provisioned RU/s or switch to autoscale/serverless after validating workload trends.",
        savings=savings,
        waste_score=55,
        confidence=confidence_with_monitor(72, account, required_keys=("normalized_ru_pct",)),
        priority="P3",
        impact="Provisioned throughput right-sizing",
        evidence=_cosmos_metric_evidence(account, ctx, {"provisioned_throughput": provisioned, "determination": "ru_underutilized"}),
    )


def evaluate_cosmos_ru_rightsizing_over(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled or ctx.get("serverless_enabled"):
        return None
    if not utilization_gate(account, "normalized_ru_pct", allow_inventory_only=False):
        return None
    thresholds = _thresholds(rule)
    normalized = fact_value(account, "normalized_ru_pct")
    if normalized is None or normalized < thresholds["ru_high_pct"]:
        return None
    name = account.get("name") or ""
    return CosmosFindingDraft(
        rule_id="COSMOS_RU_RIGHT_SIZING_OVER",
        detail=f"Cosmos DB '{name}' normalized RU consumption is {normalized:.1f}% — above the {thresholds['ru_high_pct']:.0f}% threshold.",
        recommendation="Increase provisioned RU/s or enable autoscale max throughput to add headroom.",
        savings=0.0,
        waste_score=70,
        confidence=confidence_with_monitor(78, account, required_keys=("normalized_ru_pct",)),
        priority="P2",
        impact="Prevents throttling and latency spikes",
        evidence=_cosmos_metric_evidence(account, ctx, {"determination": "ru_overutilized"}),
    )


def evaluate_cosmos_throttling(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled or ctx.get("serverless_enabled"):
        return None
    thresholds = _thresholds(rule)
    peak = fact_value(account, "normalized_ru_peak_pct")
    avg = fact_value(account, "normalized_ru_pct")
    value = peak if peak is not None else avg
    if value is None or value < thresholds["ru_throttle_pct"]:
        return None
    name = account.get("name") or ""
    return CosmosFindingDraft(
        rule_id="COSMOS_THROTTLING_DETECTED",
        detail=f"Cosmos DB '{name}' normalized RU consumption reached {value:.1f}% — throttling risk is elevated.",
        recommendation="Increase provisioned RU/s or enable autoscale immediately to avoid 429 throttling.",
        savings=0.0,
        waste_score=78,
        confidence=confidence_with_monitor(80, account, required_keys=("normalized_ru_pct",)),
        priority="P1",
        impact="Availability and latency under load",
        evidence=_cosmos_metric_evidence(account, ctx, {"determination": "throttling_risk"}),
    )


def evaluate_cosmos_hot_container(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    skew = fact_value(account, "ru_skew_ratio")
    thresholds = _thresholds(rule)
    if skew is None or skew < thresholds["hot_partition_skew_ratio"]:
        return None
    name = account.get("name") or ""
    return CosmosFindingDraft(
        rule_id="COSMOS_HOT_CONTAINER_DETECTED",
        detail=f"Cosmos DB '{name}' shows uneven RU consumption (peak/average ratio {skew:.1f}x) — possible hot partition.",
        recommendation="Review partition key design and rebalance throughput across containers.",
        savings=0.0,
        waste_score=62,
        confidence=confidence_with_monitor(65, account, required_keys=("normalized_ru_peak_pct", "normalized_ru_pct")),
        priority="P2",
        impact="Performance and cost efficiency from partition skew",
        evidence=_cosmos_metric_evidence(account, ctx, {"ru_skew_ratio": skew, "determination": "hot_partition"}),
    )


def evaluate_cosmos_api_cost_variance(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    api_type = ctx.get("api_type") or "Sql"
    if api_type == "Sql":
        return None
    multiplier = float(ctx.get("api_ru_multiplier") or 1.0)
    if multiplier <= 1.0:
        return None
    name = account.get("name") or ""
    premium_pct = round((multiplier - 1.0) * 100.0, 1)
    return CosmosFindingDraft(
        rule_id="COSMOS_API_COST_VARIANCE",
        detail=f"Cosmos DB '{name}' uses the {api_type} API (~{premium_pct:.0f}% RU premium vs SQL API).",
        recommendation="Review whether SQL API or a different data model could reduce RU cost for this workload.",
        savings=savings_from_factor(monthly, min(0.2, multiplier - 1.0)) if monthly > 0 else 0.0,
        waste_score=48,
        confidence=75,
        priority="P3",
        impact="API choice RU cost optimization",
        evidence={**ctx, "api_type": api_type, "determination": "api_cost_variance"},
    )


def evaluate_cosmos_consistency_overprovisioned(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    level = ctx.get("consistency_level") or ""
    if level not in ("Strong", "BoundedStaleness"):
        return None
    env = _env_tag(account, rule)
    if not _is_nonprod(env, rule) and level != "Strong":
        return None
    if level == "Strong" and not _is_nonprod(env, rule):
        return None
    multiplier = float(ctx.get("consistency_ru_multiplier") or 1.0)
    name = account.get("name") or ""
    return CosmosFindingDraft(
        rule_id="COSMOS_CONSISTENCY_OVERPROVISIONED",
        detail=f"Cosmos DB '{name}' uses {level} consistency ({multiplier:.1f}x RU multiplier).",
        recommendation="Relax consistency to Session or Eventual if application SLAs allow — can reduce RU cost up to 50%.",
        savings=savings_from_factor(monthly, 0.25) if monthly > 0 else 0.0,
        waste_score=50,
        confidence=62,
        priority="P3",
        impact="Read/write RU cost reduction",
        evidence={**ctx, "determination": "consistency_review"},
    )


def evaluate_cosmos_large_items(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    data_bytes = fact_value(account, "data_usage_bytes")
    doc_count = fact_value(account, "document_count")
    if data_bytes is None or doc_count is None or doc_count <= 0:
        return None
    thresholds = _thresholds(rule)
    avg_size = data_bytes / doc_count
    if avg_size < thresholds["large_item_bytes"]:
        return None
    name = account.get("name") or ""
    return CosmosFindingDraft(
        rule_id="COSMOS_LARGE_ITEMS_DETECTED",
        detail=f"Cosmos DB '{name}' average item size is {avg_size / (1024 * 1024):.2f} MB in Azure Monitor.",
        recommendation="Move large blobs to Azure Blob Storage and store references in Cosmos DB items.",
        savings=savings_from_factor(monthly, 0.15) if monthly > 0 else 0.0,
        waste_score=54,
        confidence=confidence_with_monitor(68, account, required_keys=("data_usage_bytes", "document_count")),
        priority="P3",
        impact="Storage and RU efficiency",
        evidence=_cosmos_metric_evidence(account, ctx, {"avg_item_bytes": avg_size, "determination": "large_items"}),
    )


def evaluate_cosmos_indexing_overprovisioned(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    index_bytes = fact_value(account, "index_usage_bytes")
    data_bytes = fact_value(account, "data_usage_bytes")
    if index_bytes is None or data_bytes is None or data_bytes <= 0:
        return None
    thresholds = _thresholds(rule)
    ratio = index_bytes / data_bytes
    if ratio < thresholds["index_to_data_ratio"]:
        return None
    name = account.get("name") or ""
    return CosmosFindingDraft(
        rule_id="COSMOS_INDEXING_OVERPROVISIONED",
        detail=f"Cosmos DB '{name}' index size is {ratio:.1f}x data size in Azure Monitor.",
        recommendation="Implement a custom indexing policy to exclude unused paths and reduce write RU and storage.",
        savings=savings_from_factor(monthly, 0.2) if monthly > 0 else 0.0,
        waste_score=52,
        confidence=confidence_with_monitor(66, account, required_keys=("index_usage_bytes", "data_usage_bytes")),
        priority="P3",
        impact="Index storage and write RU optimization",
        evidence=_cosmos_metric_evidence(account, ctx, {"index_to_data_ratio": ratio, "determination": "index_overprovisioned"}),
    )


def evaluate_cosmos_multi_write_unnecessary(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if not ctx.get("multi_write_enabled"):
        return None
    env = _env_tag(account, rule)
    if not _is_nonprod(env, rule) and ctx.get("region_count", 1) <= 2:
        return None
    region_count = int(ctx.get("region_count") or 1)
    savings = savings_from_factor(monthly, max(0.0, (region_count - 1) / max(region_count, 1) * 0.5)) if monthly > 0 else 0.0
    if not _passes_min_savings(rule, savings):
        return None
    name = account.get("name") or ""
    return CosmosFindingDraft(
        rule_id="COSMOS_MULTI_WRITE_UNNECESSARY",
        detail=f"Cosmos DB '{name}' has multi-region writes enabled across {region_count} regions.",
        recommendation="Use single-write region with read replicas unless global writes are required.",
        savings=savings,
        waste_score=58,
        confidence=65,
        priority="P3",
        impact="Multi-region write cost reduction",
        evidence={**ctx, "determination": "multi_write_review"},
    )


def evaluate_cosmos_failover_unnecessary(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if not ctx.get("automatic_failover_enabled"):
        return None
    env = _env_tag(account, rule)
    if not _is_nonprod(env, rule):
        return None
    name = account.get("name") or ""
    return CosmosFindingDraft(
        rule_id="COSMOS_FAILOVER_UNNECESSARY",
        detail=f"Cosmos DB '{name}' has automatic failover enabled in a non-production environment.",
        recommendation="Disable automatic failover for dev/test unless you are validating disaster recovery.",
        savings=0.0,
        waste_score=42,
        confidence=60,
        priority="P3",
        impact="Operational complexity and regional cost review",
        evidence={**ctx, "determination": "failover_review", "environment": env},
    )


def evaluate_cosmos_free_tier_suboptimal(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled:
        return None
    if not ctx.get("free_tier_enabled"):
        return None
    total_ru = fact_value(account, "total_ru")
    provisioned = fact_value(account, "provisioned_throughput")
    if total_ru is None and provisioned is None:
        return None
    over_free = (total_ru is not None and total_ru > 1000 * 7 * 24) or (provisioned is not None and provisioned > 1000)
    if not over_free:
        return None
    name = account.get("name") or ""
    return CosmosFindingDraft(
        rule_id="COSMOS_FREE_TIER_SUBOPTIMAL",
        detail=f"Cosmos DB '{name}' has free tier enabled but usage exceeds the 1,000 RU/s allowance.",
        recommendation="Evaluate paid provisioned, autoscale, or serverless instead of relying on free-tier burst limits.",
        savings=0.0,
        waste_score=46,
        confidence=confidence_with_monitor(62, account),
        priority="P3",
        impact="Free tier constraint vs workload fit",
        evidence=_cosmos_metric_evidence(account, ctx, {"determination": "free_tier_review"}),
    )


def evaluate_cosmos_reserved_capacity(
    account: dict[str, Any],
    ctx: dict[str, Any],
    monthly: float,
    rule: Any,
) -> CosmosFindingDraft | None:
    if not rule or not rule.enabled or ctx.get("serverless_enabled"):
        return None
    if not utilization_gate(account, "normalized_ru_pct", allow_inventory_only=False):
        return None
    normalized = fact_value(account, "normalized_ru_pct")
    if normalized is None:
        return None
    thresholds = _thresholds(rule)
    if normalized < thresholds["ru_low_pct"] or normalized > thresholds["ru_high_pct"]:
        return None
    if monthly <= 0:
        return None
    specs = load_cosmosdb_pricing_models()
    ri = specs.get("reserved_capacity") or {}
    discount = float(ri.get("one_year_discount_pct_max", 38)) / 100.0
    savings = round(monthly * discount, 2)
    if not _passes_min_savings(rule, savings):
        return None
    name = account.get("name") or ""
    return CosmosFindingDraft(
        rule_id="COSMOS_RESERVED_CAPACITY_ELIGIBLE",
        detail=f"Cosmos DB '{name}' shows stable RU utilization ({normalized:.1f}%) suitable for reserved capacity.",
        recommendation="Evaluate 1-year or 3-year Cosmos DB reserved capacity for predictable provisioned throughput.",
        savings=savings,
        waste_score=45,
        confidence=confidence_with_monitor(70, account, required_keys=("normalized_ru_pct",)),
        priority="P3",
        impact="Long-term RU cost reduction",
        evidence=_cosmos_metric_evidence(account, ctx, {"determination": "reserved_capacity_candidate", "estimated_ri_discount_pct": discount * 100}),
    )

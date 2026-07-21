"""Compute signals.* fields for assessment scoring caps."""

from __future__ import annotations

from typing import Any

from app.assessment.derived_signals import compute_derived_signals
from app.assessment.metric_enrichment import enrich_assessment_metric_stats
from app.assessment.pillar_signals import compute_pillar_signals
from app.assessment.region_governance import compute_region_signals

# Map flat monitor fact keys to nested assessment metric paths (metrics.*).
_ASSESSMENT_METRIC_NESTING: dict[str, tuple[str, ...]] = {
    "transaction_count": ("transactions",),
    "used_capacity_bytes": ("usedcapacity",),
    "egress_bytes": ("egress",),
    "ingress_bytes": ("ingress",),
    "byte_count": ("egress",),
    "avg_cpu_pct": ("cpu", "avg"),
    "avg_memory_pct": ("memory", "avg"),
    "storage_pct": ("usedcapacity", "utilization_pct"),
    "incoming_messages": ("incomingmessages",),
    "outgoing_messages": ("outgoingmessages",),
    "active_messages": ("activemessages",),
    "deadletter_messages": ("deadletteredmessages",),
    "server_errors": ("servererrors",),
}


def nest_flat_metrics_for_assessment(
    metrics: dict[str, Any] | None,
    *,
    assessment: dict[str, Any] | None = None,
    canonical_type: str | None = None,
    metrics_payload: dict[str, Any] | None = None,
    monitor_raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose monitor facts under metrics.* paths expected by assessment JSON rules."""
    out: dict[str, Any] = dict(metrics or {})
    for fact_key, path in _ASSESSMENT_METRIC_NESTING.items():
        val = out.get(fact_key)
        if val is None:
            continue
        node: dict[str, Any] = out
        for part in path[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        leaf = path[-1]
        if node.get(leaf) is None:
            node[leaf] = val
    return enrich_assessment_metric_stats(
        out,
        flat_metrics=metrics,
        assessment=assessment,
        canonical_type=canonical_type,
        metrics_payload=metrics_payload,
        monitor_raw=monitor_raw,
    )


def _has_cost(cost: dict[str, Any] | None) -> bool:
    if not cost:
        return False
    for key in ("monthlyActualCost", "monthly_cost_usd", "monthlyCostUsd", "mtdCostUsd"):
        val = cost.get(key)
        if val is not None and val != "":
            try:
                if float(val) >= 0:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def _has_metrics(metrics: dict[str, Any] | None, required_keys: list[str] | None = None) -> bool:
    if not metrics:
        return False
    if not required_keys:
        return bool(metrics)
    for key in required_keys:
        if metrics.get(key) is None:
            return False
    return True


def _owner_from_tags(tags: dict[str, Any] | None) -> str | None:
    if not tags:
        return None
    for key in ("Owner", "owner", "CreatedBy", "createdBy", "Contact", "contact"):
        val = tags.get(key)
        if val:
            return str(val)
    return None


def compute_signals(
    record: dict[str, Any],
    *,
    required_metric_keys: list[str] | None = None,
    assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive signals used by pythonAssessment scoring caps."""
    metrics = record.get("metrics") or {}
    cost = record.get("cost") or {}
    tags = record.get("tags") or {}
    policy = record.get("policy") or {}

    missing_metrics = not _has_metrics(metrics, required_metric_keys)
    missing_cost = not _has_cost(cost)

    env = (tags.get("Environment") or tags.get("environment") or "").strip().lower()
    is_prod = env in {"prod", "production", "prd"}
    owner = _owner_from_tags(tags)

    signals: dict[str, Any] = {
        "missingRequiredMetrics": missing_metrics,
        "missingCostData": missing_cost,
        "requiredMetricsPresent": not missing_metrics,
        "costDataComplete": not missing_cost,
        "partialMetrics": bool(metrics.get("_partial")),
        "unknownProductionOwner": bool(is_prod and not owner),
        "anyCriticalSecurityFinding": bool(policy.get("anyCriticalSecurityFinding")),
        "anyHighSecurityFinding": bool(policy.get("anyHighSecurityFinding")),
        "anyHighReliabilityFinding": bool(policy.get("anyHighReliabilityFinding")),
    }

    for key, val in metrics.items():
        if key.startswith("p95") or key.endswith("UtilizationPct") or key.endswith("_pct"):
            signals[key] = val

    signals.update(compute_region_signals(record, assessment=assessment))
    signals.update(compute_pillar_signals(record, assessment=assessment))
    signals.update(compute_derived_signals(record, signals))

    return signals

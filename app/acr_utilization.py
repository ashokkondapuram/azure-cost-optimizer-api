"""Container registry SKU, storage, and premium-feature helpers for cost rules."""

from __future__ import annotations

from typing import Any

from app.metrics_triggers import TRAFFIC_THRESHOLDS
from app.resource_utilization import fact_value


def _props(registry: dict[str, Any]) -> dict[str, Any]:
    return dict(registry.get("properties") or {})


def acr_sku_name(registry: dict[str, Any]) -> str:
    facts = registry.get("_technical_facts") or {}
    raw = facts.get("sku")
    if raw:
        return str(raw).lower()
    sku = registry.get("sku") or {}
    return str(sku.get("name") or "").lower()


def replication_count(registry: dict[str, Any]) -> int:
    facts = registry.get("_technical_facts") or {}
    raw = facts.get("replication_count")
    if raw is not None:
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            pass
    props = _props(registry)
    reps = props.get("_replications") or props.get("replications") or []
    if isinstance(reps, list) and reps:
        return len(reps)
    count = props.get("replicationCount")
    if count is not None:
        try:
            return max(0, int(count))
        except (TypeError, ValueError):
            pass
    return 0


def private_endpoint_count(registry: dict[str, Any]) -> int:
    facts = registry.get("_technical_facts") or {}
    raw = facts.get("private_endpoint_count")
    if raw is not None:
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            pass
    props = _props(registry)
    conns = props.get("privateEndpointConnections") or []
    return len(conns) if isinstance(conns, list) else 0


def zone_redundancy_enabled(registry: dict[str, Any]) -> bool:
    facts = registry.get("_technical_facts") or {}
    raw = facts.get("zone_redundancy")
    if raw is not None:
        return str(raw).lower() == "enabled"
    return str(_props(registry).get("zoneRedundancy") or "").lower() == "enabled"


def retention_policy_status(registry: dict[str, Any]) -> tuple[bool, int | None]:
    facts = registry.get("_technical_facts") or {}
    enabled_raw = facts.get("retention_policy_enabled")
    days_raw = facts.get("retention_policy_days")
    if enabled_raw is not None:
        enabled = str(enabled_raw).lower() in {"true", "enabled", "1"}
        days = int(days_raw) if days_raw is not None else None
        return enabled, days
    policies = _props(registry).get("policies") or {}
    retention = policies.get("retentionPolicy") or {}
    status = str(retention.get("status") or "").lower()
    days = retention.get("days")
    return status == "enabled", int(days) if days is not None else None


def has_network_restrictions(registry: dict[str, Any]) -> bool:
    facts = registry.get("_technical_facts") or {}
    action = facts.get("network_default_action")
    if action and str(action).lower() == "deny":
        return True
    props = _props(registry)
    rule_set = props.get("networkRuleSet") or {}
    if str(rule_set.get("defaultAction") or "").lower() == "deny":
        return True
    ip_rules = rule_set.get("ipRules") or []
    return bool(ip_rules)


def premium_features_in_use(registry: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if replication_count(registry) > 0:
        blockers.append("geo_replication")
    if zone_redundancy_enabled(registry):
        blockers.append("zone_redundancy")
    if private_endpoint_count(registry) > 0:
        blockers.append("private_link")
    if has_network_restrictions(registry):
        blockers.append("network_rules")
    enabled, _ = retention_policy_status(registry)
    if enabled:
        blockers.append("retention_policy")
    return blockers


def blocks_acr_sku_downgrade(registry: dict[str, Any]) -> bool:
    return bool(premium_features_in_use(registry))


def storage_used_gb(registry: dict[str, Any]) -> float | None:
    raw = fact_value(registry, "storage_used_bytes")
    if raw is None:
        return None
    try:
        return float(raw) / (1024 ** 3)
    except (TypeError, ValueError):
        return None


def is_low_pull_volume(
    registry: dict[str, Any],
    *,
    threshold: float | None = None,
) -> bool | None:
    pulls = fact_value(registry, "pull_count")
    if pulls is None:
        return None
    limit = threshold if threshold is not None else TRAFFIC_THRESHOLDS["acr_pull_count_low"]
    return float(pulls) < limit


def is_low_push_volume(
    registry: dict[str, Any],
    *,
    threshold: float | None = None,
) -> bool | None:
    pushes = fact_value(registry, "push_count")
    if pushes is None:
        return None
    limit = threshold if threshold is not None else TRAFFIC_THRESHOLDS["acr_push_count_low"]
    return float(pushes) < limit


def is_low_acr_activity(
    registry: dict[str, Any],
    *,
    pull_threshold: float | None = None,
    push_threshold: float | None = None,
) -> bool | None:
    low_pull = is_low_pull_volume(registry, threshold=pull_threshold)
    low_push = is_low_push_volume(registry, threshold=push_threshold)
    if low_pull is None and low_push is None:
        return None
    if low_pull is False or low_push is False:
        return False
    return True


def is_high_acr_storage(
    registry: dict[str, Any],
    *,
    min_gb: float | None = None,
) -> bool | None:
    used = storage_used_gb(registry)
    if used is None:
        return None
    minimum = min_gb if min_gb is not None else TRAFFIC_THRESHOLDS["acr_storage_high_gb"]
    return used >= minimum


def meets_acr_savings_gate(
    monthly_cost: float,
    *,
    min_monthly_savings_usd: float | None = None,
) -> bool:
    minimum = min_monthly_savings_usd if min_monthly_savings_usd is not None else 0.0
    return monthly_cost >= minimum


def is_nonprod_registry(registry: dict[str, Any], *, nonprod_values: list[str] | tuple[str, ...]) -> bool:
    tags = registry.get("tags") or {}
    env = str(tags.get("environment") or tags.get("env") or "").lower()
    if not env:
        return True
    return env in {v.lower() for v in nonprod_values}


def acr_threshold_evidence(rule) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in (
        "acr_pull_count_low",
        "acr_storage_high_gb",
        "acr_push_count_low",
        "min_monthly_savings_usd",
    ):
        val = getattr(rule, key, None)
        if val is not None:
            out[key] = val
    return out


def acr_inventory_evidence(registry: dict[str, Any]) -> dict[str, Any]:
    enabled, days = retention_policy_status(registry)
    blockers = premium_features_in_use(registry)
    out: dict[str, Any] = {
        "sku": acr_sku_name(registry),
        "replication_count": replication_count(registry),
        "private_endpoint_count": private_endpoint_count(registry),
        "zone_redundancy": "Enabled" if zone_redundancy_enabled(registry) else "Disabled",
        "retention_policy_enabled": enabled,
        "premium_blockers": blockers,
    }
    if days is not None:
        out["retention_policy_days"] = days
    props = _props(registry)
    reps = props.get("_replications") or []
    if isinstance(reps, list) and reps:
        regions = [r.get("location") for r in reps if r.get("location")]
        if regions:
            out["replication_regions"] = regions
    storage_gb = storage_used_gb(registry)
    if storage_gb is not None:
        out["storage_used_gb"] = round(storage_gb, 2)
    pulls = fact_value(registry, "pull_count")
    if pulls is not None:
        out["pull_count"] = pulls
    pushes = fact_value(registry, "push_count")
    if pushes is not None:
        out["push_count"] = pushes
    return out

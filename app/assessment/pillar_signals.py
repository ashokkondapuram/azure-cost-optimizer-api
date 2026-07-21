"""Compute cross-cutting pillar signals from DB-backed metrics, cost, properties, and policy."""

from __future__ import annotations

from typing import Any

from app.assessment.shared_config import merge_pillar_triggers


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_num(source: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        val = source.get(key)
        if val is None:
            val = source.get(key.lower())
        num = _num(val)
        if num is not None:
            return num
    return None


def _nested_num(metrics: dict[str, Any], *paths: tuple[str, ...]) -> float | None:
    for path in paths:
        node: Any = metrics
        for part in path:
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(part)
        num = _num(node)
        if num is not None:
            return num
    return None


def _thresholds(assessment: dict[str, Any] | None = None) -> dict[str, Any]:
    return (merge_pillar_triggers(assessment).get("threshold_defaults") or {})


def _is_service_bus(resource_type: str | None) -> bool:
    rt = (resource_type or "").lower()
    return "microsoft.servicebus/" in rt


def _public_access_enabled(properties: dict[str, Any]) -> bool:
    for key in (
        "publicNetworkAccess",
        "public_network_access",
        "properties.publicNetworkAccess",
    ):
        val = properties.get(key)
        if isinstance(val, str):
            return val.strip().lower() not in {"disabled", "false", "none"}
    pna = properties.get("publicNetworkAccess")
    if isinstance(pna, str):
        return pna.strip().lower() != "disabled"
    return False


def _encryption_disabled(properties: dict[str, Any]) -> bool:
    for key in ("disableLocalAuth",):
        _ = properties.get(key)
    for key in (
        "encryption",
        "encryption.keySource",
        "properties.encryption.keySource",
    ):
        val = properties.get(key)
        if isinstance(val, dict):
            val = val.get("keySource")
        if isinstance(val, str) and val.strip().lower() == "microsoft.storage":
            return False
    return False


def compute_pillar_signals(
    record: dict[str, Any],
    *,
    assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive cost/performance/reliability/security signals used by assessment rules."""
    metrics = record.get("metrics") or {}
    cost = record.get("cost") or {}
    properties = record.get("properties") or {}
    resource = record.get("resource") or {}
    resource_type = record.get("resource_type") or resource.get("type")
    thresholds = _thresholds(assessment)
    cost_t = thresholds.get("cost") or {}
    perf_t = thresholds.get("performance") or {}
    rel_t = thresholds.get("reliability") or {}

    monthly = _first_num(cost, "monthlyActualCost", "monthly_cost_usd", "monthlyCostUsd", "mtdCostUsd")
    daily_anomaly = _first_num(cost, "dailyCostAnomalyPct")
    weekly_anomaly = _first_num(cost, "weeklyCostAnomalyPct")
    monthly_increase = _first_num(cost, "monthlyCostIncreasePct")

    cpu = _first_num(metrics, "avg_cpu_pct", "cpuPct", "cpu_pct")
    if cpu is None:
        cpu = _nested_num(metrics, ("cpu", "avg"), ("cpu", "p95"))
    memory = _first_num(metrics, "avg_memory_pct", "memoryPct", "memory_pct")
    if memory is None:
        memory = _nested_num(metrics, ("memory", "avg"), ("memory", "p95"))

    cpu_sat_threshold = _num(perf_t.get("cpu_saturation_pct")) or 80
    mem_sat_threshold = _num(perf_t.get("memory_saturation_pct")) or 85
    idle_days_threshold = int(_num(rel_t.get("days_since_activity_idle")) or _num(cost_t.get("idle_days")) or 14)

    incoming = _first_num(
        metrics,
        "incoming_messages",
        "incomingmessages",
        "incomingrequests",
        "incomingrequests_total",
    )
    if incoming is None:
        incoming = _nested_num(metrics, ("incomingmessages",), ("incomingmessages", "total"))

    deadletters = _first_num(
        metrics,
        "deadletter_messages",
        "deadletteredmessages",
        "deadlettermessages",
    )
    if deadletters is None:
        deadletters = _nested_num(metrics, ("deadletteredmessages",), ("deadlettermessages",))

    server_errors = _first_num(metrics, "servererrors", "server_errors")
    throttled = _first_num(metrics, "throttledrequests", "throttled_requests", "usererrors")

    days_idle = _first_num(metrics, "days_since_last_activity", "idle_days", "daysSinceLastActivity")

    sku = (resource.get("sku") or properties.get("sku") or "")
    if isinstance(sku, dict):
        sku = sku.get("name") or sku.get("tier") or ""
    sku_text = str(sku).lower()
    premium_units = _first_num(metrics, "premiumMessagingUnits", "premium_messaging_units")

    premium_underutilized = False
    if "premium" in sku_text:
        cpu_max = _num(cost_t.get("premium_cpu_utilization_max_pct")) or 30
        mem_max = _num(cost_t.get("premium_memory_utilization_max_pct")) or 40
        incoming_max = _num(cost_t.get("premium_underutilized_incoming_messages_max")) or 5000
        low_cpu = cpu is None or cpu < cpu_max
        low_mem = memory is None or memory < mem_max
        low_traffic = incoming is None or incoming < incoming_max
        premium_underutilized = low_cpu and low_mem and low_traffic

    zone_redundant = properties.get("zoneRedundant")
    if zone_redundant is None:
        zone_redundant = properties.get("zone_redundant")
    single_az_risk = zone_redundant is False

    signals: dict[str, Any] = {
        "monthlyActualCost": monthly,
        "costAnomalyDetected": bool(
            (daily_anomaly is not None and daily_anomaly >= (_num(cost_t.get("daily_cost_anomaly_pct")) or 15))
            or (weekly_anomaly is not None and weekly_anomaly >= (_num(cost_t.get("weekly_cost_anomaly_pct")) or 10))
        ),
        "idleDays": int(days_idle) if days_idle is not None else None,
        "cpuSaturation": bool(cpu is not None and cpu >= cpu_sat_threshold),
        "memorySaturation": bool(memory is not None and memory >= mem_sat_threshold),
        "throttlingDetected": bool(
            (throttled is not None and throttled >= (_num(perf_t.get("throttle_events_min")) or 1))
            or (server_errors is not None and server_errors >= (_num(perf_t.get("server_errors_min")) or 1))
        ),
        "throttledOrServerErrors": bool(
            (throttled is not None and throttled >= 1)
            or (server_errors is not None and server_errors >= 1)
        ),
        "deadletterMessages": deadletters,
        "premiumUnderutilized": premium_underutilized,
        "publicAccessEnabled": _public_access_enabled(properties),
        "encryptionAtRestDisabled": _encryption_disabled(properties),
        "deprecatedSkuOrVersion": bool(properties.get("deprecated") or properties.get("deprecatedSku")),
        "singleAzRisk": single_az_risk,
        "steadyUsage": bool(incoming is not None and incoming > 0),
        "productionCritical": bool(
            str((record.get("tags") or {}).get("Environment") or (record.get("tags") or {}).get("environment") or "")
            .strip()
            .lower()
            in {"prod", "production", "prd"}
        ),
        "daysSinceLastActivity": int(days_idle) if days_idle is not None else None,
        "criticalCostOrSecurityRisk": bool(
            (record.get("policy") or {}).get("anyCriticalSecurityFinding")
            or (monthly is not None and monthly_increase is not None and monthly_increase >= 50)
        ),
        "regionPriceVariancePct": _first_num(metrics, "regionPriceVariancePct", "region_price_variance_pct"),
        "newerGenerationBetterPricePerformance": bool(properties.get("newerGenerationAvailable")),
    }

    if monthly_increase is not None:
        signals["monthlyCostIncreasePct"] = monthly_increase

    if _is_service_bus(resource_type):
        idle_max = 100
        sb_overrides = ((merge_pillar_triggers(assessment).get("service_overrides") or {})
                        .get("Microsoft.ServiceBus/namespaces") or {})
        sb_metrics = sb_overrides.get("metric_thresholds") or {}
        idle_max = int(_num(sb_metrics.get("incoming_messages_idle_max")) or idle_max)
        if days_idle is None and incoming is not None and incoming < idle_max and monthly and monthly > 0:
            signals["idleDays"] = idle_days_threshold
        if premium_units is not None:
            signals["premiumMessagingUnits"] = premium_units

    return {k: v for k, v in signals.items() if v is not None}

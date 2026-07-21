"""Derive cross-cutting optimization signals from normalized DB records."""

from __future__ import annotations

from typing import Any

from app.assessment.shared_config import load_pillar_triggers


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


def _prop_bool(properties: dict[str, Any], *keys: str, default: bool | None = None) -> bool | None:
    for key in keys:
        val = properties.get(key)
        if val is None:
            continue
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            lowered = val.strip().lower()
            if lowered in {"true", "enabled", "enabledforkeyvault"}:
                return True
            if lowered in {"false", "disabled", "none"}:
                return False
    return default


def _is_prod(tags: dict[str, Any]) -> bool:
    env = (tags.get("Environment") or tags.get("environment") or "").strip().lower()
    return env in {"prod", "production", "prd"}


def compute_derived_signals(record: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    """Compute standard optimization signals referenced across assessment JSON rules."""
    metrics = record.get("metrics") or {}
    cost = record.get("cost") or {}
    properties = record.get("properties") or {}
    policy = record.get("policy") or {}
    tags = record.get("tags") or {}
    thresholds = (load_pillar_triggers().get("threshold_defaults") or {})
    perf_t = thresholds.get("performance") or {}
    cost_t = thresholds.get("cost") or {}

    cpu = _first_num(metrics, "avg_cpu_pct", "cpuPct", "cpu_pct", "p95CpuPct")
    if cpu is None:
        cpu = _nested_num(metrics, ("cpu", "avg"), ("cpu", "p95"))
    memory = _first_num(metrics, "avg_memory_pct", "memoryPct", "memory_pct", "p95MemoryPct")
    if memory is None:
        memory = _nested_num(metrics, ("memory", "avg"), ("memory", "p95"))

    cpu_sat_threshold = _num(perf_t.get("cpu_saturation_pct")) or 80
    mem_sat_threshold = _num(perf_t.get("memory_saturation_pct")) or 85
    low_util_threshold = _num(cost_t.get("premium_cpu_utilization_max_pct")) or 30

    performance_saturated = bool(
        existing.get("cpuSaturation")
        or existing.get("memorySaturation")
        or existing.get("throttlingDetected")
        or (cpu is not None and cpu >= cpu_sat_threshold)
        or (memory is not None and memory >= mem_sat_threshold)
    )

    low_utilization = False
    if cpu is not None or memory is not None:
        cpu_low = cpu is None or cpu < low_util_threshold
        mem_low = memory is None or memory < (_num(cost_t.get("premium_memory_utilization_max_pct")) or 40)
        low_utilization = cpu_low and mem_low and not performance_saturated

    headroom_values: list[float] = []
    if cpu is not None:
        headroom_values.append(max(0.0, 100.0 - cpu))
    if memory is not None:
        headroom_values.append(max(0.0, 100.0 - memory))
    performance_headroom_pct = min(headroom_values) if headroom_values else None

    monthly = existing.get("monthlyActualCost")
    if monthly is None:
        monthly = _first_num(cost, "monthlyActualCost", "monthly_cost_usd", "monthlyCostUsd", "mtdCostUsd")

    idle_days = existing.get("idleDays")
    if idle_days is None:
        idle_days = existing.get("daysSinceLastActivity")

    incoming = _first_num(metrics, "incoming_messages", "incomingmessages", "incomingrequests")
    no_recent_usage = bool(
        (idle_days is not None and idle_days >= int(_num(cost_t.get("idle_days")) or 14))
        or (incoming is not None and incoming <= 0)
    )

    public_access = bool(existing.get("publicAccessEnabled"))
    encryption_disabled = bool(existing.get("encryptionAtRestDisabled"))
    security_baseline_gap = bool(
        public_access
        or encryption_disabled
        or policy.get("anyCriticalSecurityFinding")
        or policy.get("anyHighSecurityFinding")
    )

    reliability_baseline_gap = bool(
        existing.get("singleAzRisk")
        or policy.get("anyHighReliabilityFinding")
        or (_num(existing.get("deadletterMessages")) or 0) > 0
    )

    diagnostics_enabled = _prop_bool(
        properties,
        "diagnosticSettingsEnabled",
        "diagnosticsEnabled",
        "enableHttpLogs",
        "logsEnabled",
    )
    if diagnostics_enabled is None:
        diagnostics = properties.get("diagnosticSettings") or properties.get("diagnostics")
        if isinstance(diagnostics, list):
            diagnostics_enabled = len(diagnostics) > 0
        elif isinstance(diagnostics, dict):
            diagnostics_enabled = bool(diagnostics)

    disable_local_auth = _prop_bool(properties, "disableLocalAuth", "disable_local_auth")
    local_auth_enabled = None if disable_local_auth is None else not disable_local_auth

    key_source = properties.get("encryption.keySource") or properties.get("keySource")
    encryption = properties.get("encryption")
    if isinstance(encryption, dict) and not key_source:
        key_source = encryption.get("keySource")
    uses_cmk = None
    if isinstance(key_source, str):
        uses_cmk = key_source.strip().lower() in {"microsoft.keyvault", "keyvault"}

    zone_redundant = _prop_bool(properties, "zoneRedundant", "zone_redundant", "zoneRedundancy")
    geo_redundant = _prop_bool(properties, "geoRedundant", "geo_redundant", "geoReplicationEnabled")

    tls_version = properties.get("minimumTlsVersion") or properties.get("minTlsVersion")
    tls_latest_enabled = None
    if isinstance(tls_version, str):
        tls_latest_enabled = tls_version.strip().lower() in {"1.2", "1.3", "tls1_2", "tls1_3"}

    private_endpoint = properties.get("privateEndpointConnections") or properties.get("privateEndpoint")
    private_endpoint_configured = None
    if isinstance(private_endpoint, list):
        private_endpoint_configured = len(private_endpoint) > 0
    elif isinstance(private_endpoint, dict):
        private_endpoint_configured = bool(private_endpoint)

    autoscale = properties.get("autoscaleSettings") or properties.get("autoscale") or properties.get("profiles")
    autoscale_configured = None
    if isinstance(autoscale, list):
        autoscale_configured = len(autoscale) > 0
    elif isinstance(autoscale, dict):
        autoscale_configured = bool(autoscale)

    premium_features_unused = bool(existing.get("premiumUnderutilized"))

    signals: dict[str, Any] = {
        "performanceSaturated": performance_saturated,
        "securityBaselineGap": security_baseline_gap,
        "reliabilityBaselineGap": reliability_baseline_gap,
        "lowUtilization": low_utilization,
        "rightSizeCandidate": bool(low_utilization and monthly and monthly > 0),
        "utilizationWithinTarget": bool(not low_utilization and not performance_saturated),
        "noRecentUsage": no_recent_usage,
        "hasHighOrCriticalFinding": bool(
            policy.get("anyCriticalSecurityFinding")
            or policy.get("anyHighSecurityFinding")
            or policy.get("anyHighReliabilityFinding")
        ),
        "businessCriticalityUnknown": bool(_is_prod(tags) and not (tags.get("BusinessCriticality") or tags.get("businessCriticality"))),
        "orphanedOrUnattached": bool(
            properties.get("diskState") == "Unattached"
            or properties.get("managedBy") in {None, ""}
            and properties.get("diskState") == "Unattached"
        ),
        "recentlyChanged": bool(properties.get("recentlyChanged") or properties.get("lastModifiedWithinDays", 999) <= 7),
        "conflictingRightsizeSignals": bool(low_utilization and performance_saturated),
        "premiumFeatureUsed": bool(not premium_features_unused and "premium" in str(properties.get("sku") or "").lower()),
        "excessHeadroomPct": performance_headroom_pct,
        "meterBreakdownAvailable": bool(cost.get("meterBreakdown") or cost.get("meters")),
        "budgetAlertConfigured": bool(policy.get("budgetAlertConfigured") or tags.get("BudgetAlert")),
        "scheduleConfigured": bool(properties.get("autoShutdownSchedule") or properties.get("schedule")),
        "commitmentEligible": bool(existing.get("steadyUsage") and monthly and monthly >= 100),
        "commitmentCoveragePct": _first_num(cost, "commitmentCoveragePct", "reservationCoveragePct"),
        "variableDemand": bool(existing.get("steadyUsage") is False or autoscale_configured),
        "premiumFeaturesUnused": premium_features_unused,
        "geoRedundancyRequired": bool(_is_prod(tags) and geo_redundant is False),
        "retentionOverPolicy": bool(
            policy.get("maxRetentionDays") is not None
            and (_num(properties.get("retentionDays") or properties.get("softDeleteRetentionInDays")) or 0)
            > (_num(policy.get("maxRetentionDays")) or 0)
        ),
        "retentionBelowPolicy": bool(
            policy.get("minRetentionDays") is not None
            and (_num(properties.get("retentionDays")) or 0) < (_num(policy.get("minRetentionDays")) or 0)
        ),
        "sensitiveWorkload": bool(
            _is_prod(tags)
            or str(tags.get("DataClassification") or tags.get("dataClassification") or "").lower() in {"confidential", "restricted", "pii"}
        ),
        "hybridBenefitEligible": bool(properties.get("licenseType") in {None, "", "None"} and "windows" in str(properties.get("osType") or "").lower()),
        "hybridBenefitApplied": bool(str(properties.get("licenseType") or "").lower() in {"windows_server", "windowsclient"}),
        "storageTierMismatch": bool(properties.get("accessTierMismatch") or properties.get("storageTierMismatch")),
        "identityAuthSupported": bool(properties.get("identity") or properties.get("managedIdentity")),
        "cmkSupported": bool(properties.get("encryption") or properties.get("customerManagedKey")),
        "tlsLatestSupported": bool(tls_version is not None),
        "orphanedChildResourceCost": _first_num(cost, "orphanedChildResourceCost"),
        "unusedChildResourceCount": _first_num(metrics, "unusedChildResourceCount"),
        "readReplicaUtilizationPct": _first_num(metrics, "readReplicaUtilizationPct"),
        "replicaCount": _first_num(properties, "replicaCount") or _first_num(metrics, "replicaCount"),
        "diagnosticIngestionCostPct": _first_num(cost, "diagnosticIngestionCostPct"),
        "logRetentionDays": _num(properties.get("retentionInDays") or properties.get("logRetentionDays")),
        "longRetentionRequired": bool(policy.get("longRetentionRequired")),
        "privateEndpointTrafficPct": _first_num(metrics, "privateEndpointTrafficPct"),
        "publicTrafficPct": _first_num(metrics, "publicTrafficPct"),
        "oldRecoveryPointCost": _first_num(cost, "oldRecoveryPointCost"),
        "autoscaleAtMinPct": _first_num(metrics, "autoscaleAtMinPct"),
        "autoscaleAtMaxPct": _first_num(metrics, "autoscaleAtMaxPct"),
        "expectedLifetimeDays": _num(properties.get("expectedLifetimeDays") or tags.get("ExpectedLifetimeDays")),
        "unusedDays": idle_days,
        "hasHaArchitecture": bool(zone_redundant or geo_redundant),
        "backupConfigured": bool(properties.get("backup") or properties.get("backupPolicyId")),
        "policyNonCompliant": bool(policy.get("nonCompliant") or policy.get("policyNonCompliant")),
        "missingPriceData": bool(cost.get("missingPriceData")),
    }

    optional_bools = {
        "diagnosticsEnabled": diagnostics_enabled,
        "localAuthEnabled": local_auth_enabled,
        "usesCustomerManagedKey": uses_cmk,
        "zoneRedundant": zone_redundant,
        "geoRedundant": geo_redundant,
        "tlsLatestEnabled": tls_latest_enabled,
        "privateEndpointConfigured": private_endpoint_configured,
        "autoscaleConfigured": autoscale_configured,
    }
    for key, val in optional_bools.items():
        if val is not None:
            signals[key] = val

    if performance_headroom_pct is not None:
        signals["performanceHeadroomPct"] = performance_headroom_pct

    for key in (
        "errorRatePct",
        "storageFreePct",
        "app5xxRatePct",
        "availabilityScore",
        "availabilityPct",
        "failureRatePct",
        "p95CpuPct",
        "p95MemoryPct",
        "p05AvailableMemoryPct",
        "p95StoragePct",
        "p95IopsConsumedPct",
        "p95IopsUtilizationPct",
        "p95LatencyMs",
        "p95ResponseTimeMs",
        "p95ThroughputUtilizationPct",
        "p95BandwidthConsumedPct",
        "capacityPct",
        "capacityUnitPct",
        "throttleRatePct",
        "samplingMissingAndHighVolume",
        "tlsBelowPolicy",
        "backupFailures",
        "httpsOnly",
        "planP95CpuPct",
        "planP95MemoryPct",
    ):
        val = _first_num(metrics, key, key.lower())
        if val is not None:
            signals[key] = val

    for key in (
        "overPrivilegedRoleCount",
        "orphanedAssignmentCount",
        "hasHighOrCriticalFinding",
    ):
        val = policy.get(key)
        if val is not None:
            signals[key] = val

    _keep_false = {
        "lowUtilization",
        "performanceSaturated",
        "securityBaselineGap",
        "reliabilityBaselineGap",
        "noRecentUsage",
        "rightSizeCandidate",
        "utilizationWithinTarget",
        "premiumFeaturesUnused",
        "diagnosticsEnabled",
        "localAuthEnabled",
        "usesCustomerManagedKey",
        "zoneRedundant",
        "geoRedundant",
        "privateEndpointConfigured",
        "autoscaleConfigured",
    }
    return {
        k: v
        for k, v in signals.items()
        if v is not None and (v is not False or k in _keep_false)
    }

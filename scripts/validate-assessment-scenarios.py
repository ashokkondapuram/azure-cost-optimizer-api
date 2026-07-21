#!/usr/bin/env python3
"""Validate assessment JSON files for runtime scenario coverage."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))

from app.assessment.catalog import get_assessment_for_arm_type  # noqa: E402
from app.assessment.runtime import evaluate_condition_group  # noqa: E402
from app.assessment.signals import compute_signals  # noqa: E402
from app.assessment.what_if import lookup_what_if_scenario  # noqa: E402

ALLOWED_OPERATORS = {
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "not_in",
    "contains",
    "missing",
    "present",
    "is_true",
    "is_false",
}

# Signals computed in backend (signals.py, pillar_signals, region_governance, derived_signals).
BACKEND_SIGNAL_ROOTS = {
    "missingRequiredMetrics",
    "missingCostData",
    "requiredMetricsPresent",
    "costDataComplete",
    "partialMetrics",
    "unknownProductionOwner",
    "anyCriticalSecurityFinding",
    "anyHighSecurityFinding",
    "anyHighReliabilityFinding",
    "currentRegion",
    "regionClassification",
    "regionApproved",
    "recommendedRegion",
    "recommendedRegionDisplay",
    "regionMoveAllowed",
    "regionMigrationRequired",
    "monthlyActualCost",
    "costAnomalyDetected",
    "idleDays",
    "cpuSaturation",
    "memorySaturation",
    "throttlingDetected",
    "throttledOrServerErrors",
    "deadletterMessages",
    "premiumUnderutilized",
    "publicAccessEnabled",
    "encryptionAtRestDisabled",
    "deprecatedSkuOrVersion",
    "singleAzRisk",
    "steadyUsage",
    "productionCritical",
    "daysSinceLastActivity",
    "criticalCostOrSecurityRisk",
    "regionPriceVariancePct",
    "newerGenerationBetterPricePerformance",
    "monthlyCostIncreasePct",
    "premiumMessagingUnits",
    "performanceSaturated",
    "securityBaselineGap",
    "reliabilityBaselineGap",
    "lowUtilization",
    "rightSizeCandidate",
    "utilizationWithinTarget",
    "noRecentUsage",
    "hasHighOrCriticalFinding",
    "businessCriticalityUnknown",
    "orphanedOrUnattached",
    "recentlyChanged",
    "conflictingRightsizeSignals",
    "premiumFeatureUsed",
    "excessHeadroomPct",
    "performanceHeadroomPct",
    "meterBreakdownAvailable",
    "budgetAlertConfigured",
    "scheduleConfigured",
    "commitmentEligible",
    "commitmentCoveragePct",
    "variableDemand",
    "premiumFeaturesUnused",
    "geoRedundancyRequired",
    "retentionOverPolicy",
    "retentionBelowPolicy",
    "sensitiveWorkload",
    "hybridBenefitEligible",
    "hybridBenefitApplied",
    "storageTierMismatch",
    "identityAuthSupported",
    "cmkSupported",
    "tlsLatestSupported",
    "orphanedChildResourceCost",
    "unusedChildResourceCount",
    "readReplicaUtilizationPct",
    "replicaCount",
    "diagnosticIngestionCostPct",
    "logRetentionDays",
    "longRetentionRequired",
    "privateEndpointTrafficPct",
    "publicTrafficPct",
    "oldRecoveryPointCost",
    "autoscaleAtMinPct",
    "autoscaleAtMaxPct",
    "expectedLifetimeDays",
    "unusedDays",
    "hasHaArchitecture",
    "backupConfigured",
    "policyNonCompliant",
    "missingPriceData",
    "diagnosticsEnabled",
    "localAuthEnabled",
    "usesCustomerManagedKey",
    "zoneRedundant",
    "geoRedundant",
    "tlsLatestEnabled",
    "privateEndpointConfigured",
    "autoscaleConfigured",
}

COLLECTOR_DERIVED_PREFIXES = ("p95", "p05", "metrics.")


COLLECTOR_DERIVED_SUFFIXES = ("Pct", "Count", "Score", "Ms", "GiB", "Hours", "Ratio", "Rate")
COLLECTOR_DERIVED_HINTS = (
    "Mismatch",
    "Enabled",
    "Disabled",
    "Idle",
    "Underutilized",
    "Required",
    "Supported",
    "Allowed",
    "Attached",
    "Missing",
    "High",
    "Low",
    "Mode",
    "Tier",
    "Unused",
    "Orphaned",
    "Over",
    "Under",
    "Stale",
    "Expired",
    "Churn",
    "Lag",
    "Spike",
    "Waste",
    "Growth",
    "Safe",
    "Interruptible",
    "Production",
    "Burstable",
    "Replication",
    "Provisioned",
    "Meets",
    "Configured",
    "Detected",
    "Candidate",
    "Exposure",
    "Saturation",
    "Supports",
    "Premium",
    "Export",
    "Profile",
)


def _signal_supported(path: str) -> bool:
    if not path.startswith("signals."):
        return True
    leaf = path[len("signals.") :]
    root = leaf.split(".")[0]
    if root in BACKEND_SIGNAL_ROOTS or leaf in BACKEND_SIGNAL_ROOTS:
        return True
    if root.startswith(COLLECTOR_DERIVED_PREFIXES) or root.endswith("UtilizationPct") or root.endswith("_pct"):
        return True
    if any(root.endswith(suffix) for suffix in COLLECTOR_DERIVED_SUFFIXES):
        return True
    if any(hint in root for hint in COLLECTOR_DERIVED_HINTS):
        return True
    if leaf.startswith("costDrivers."):
        return True
    return False


def _actionable_rules(data: dict) -> list[dict]:
    rules: list[dict] = []
    for section in ("recommendationRules", "bestOptimizationRules"):
        rules.extend(data.get(section) or [])
    return rules


def _iter_rule_sections(data: dict) -> list[tuple[str, dict]]:
    rules: list[tuple[str, dict]] = []
    for section in (
        "recommendationRules",
        "assessmentRules",
        "bestOptimizationRules",
        "metricAssessmentRules",
        "propertyAssessmentRules",
        "actionOutcomeRules",
    ):
        for rule in data.get(section) or []:
            rules.append((section, rule))
    return rules


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON: {exc}"]

    unsupported_signals: Counter[str] = Counter()
    missing_what_if: list[str] = []
    bad_operators: list[str] = []

    for section, rule in _iter_rule_sections(data):
        rule_id = str(rule.get("id") or "")
        condition = rule.get("condition") or {}
        if not isinstance(condition, dict):
            errors.append(f"{path.name}: {section}.{rule_id} condition must be object")
            continue
        check_signals = section in {"recommendationRules", "bestOptimizationRules"}
        for cond in condition.get("conditions") or []:
            op = cond.get("operator")
            if op and op not in ALLOWED_OPERATORS:
                bad_operators.append(f"{rule_id}:{op}")
            field = str(cond.get("field") or cond.get("path") or "")
            if check_signals and field.startswith("signals.") and not _signal_supported(field):
                unsupported_signals[field] += 1

        if rule_id and section in {"recommendationRules", "bestOptimizationRules"}:
            if not lookup_what_if_scenario(data, rule_id, rule=rule):
                missing_what_if.append(rule_id)

    if bad_operators:
        errors.append(f"{path.name}: unsupported operators: {', '.join(sorted(set(bad_operators))[:8])}")

    top_unsupported = [p for p, _ in unsupported_signals.most_common(5)]
    schema = str(data.get("schema_version") or data.get("schemaVersion") or "")
    is_v2 = schema.startswith("2")
    if top_unsupported and not is_v2 and path.name in {
        "servicebus-assessment.json",
        "disk-assessment.json",
        "storage-account-assessment.json",
    }:
        errors.append(
            f"{path.name}: unsupported signal paths (top): {', '.join(top_unsupported)}"
        )

    if missing_what_if[:3] and not is_v2 and path.name in {
        "servicebus-assessment.json",
        "disk-assessment.json",
        "storage-account-assessment.json",
    }:
        errors.append(
            f"{path.name}: missing what-if for sample rules: {', '.join(missing_what_if[:3])}"
        )

    if data.get("regionGovernance") and not data["regionGovernance"].get("approvedRegions"):
        errors.append(f"{path.name}: regionGovernance.approvedRegions is empty")

    return errors


def smoke_evaluate_resource_types() -> list[str]:
  errors: list[str] = []
  samples = [
      "Microsoft.ServiceBus/namespaces",
      "Microsoft.Compute/disks",
      "Microsoft.Storage/storageAccounts",
  ]
  for arm_type in samples:
      assessment = get_assessment_for_arm_type(arm_type)
      if not assessment:
          errors.append(f"missing assessment for {arm_type}")
          continue
      record = {
          "resource_id": f"/subscriptions/sub/resourceGroups/rg/providers/{arm_type}/sample",
          "resource_type": arm_type,
          "resource": {"name": "sample", "location": "eastus", "type": arm_type},
          "location": "eastus",
          "properties": {},
          "metrics": {"incoming_messages": 10},
          "cost": {"monthlyActualCost": 100},
          "tags": {"Environment": "prod"},
          "policy": {},
      }
      record["signals"] = compute_signals(record, assessment=assessment)
      if record["signals"].get("recommendedRegion") is None:
          errors.append(f"{arm_type}: recommendedRegion not computed")
  return errors


def validate_matrix_assessment_files() -> list[str]:
    errors: list[str] = []
    matrix_path = DATA / "assessment-case-matrix.json"
    if not matrix_path.is_file():
        return ["assessment-case-matrix.json missing"]
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    disk_files = {
        path.name
        for path in DATA.glob("*-assessment.json")
        if path.name != "assessment-case-matrix.json"
    }
    for resource_type, entry in (matrix.get("resourceCaseThresholds") or {}).items():
        assessment_file = str((entry or {}).get("assessmentFile") or "")
        if assessment_file and assessment_file not in disk_files:
            errors.append(
                f"assessment-case-matrix.json: {resource_type} references missing file {assessment_file}"
            )
    return errors


def validate_index_counts() -> list[str]:
    errors: list[str] = []
    index_path = DATA / "assessment-index.json"
    if not index_path.is_file():
        return ["assessment-index.json missing"]
    index = json.loads(index_path.read_text(encoding="utf-8"))
    disk_count = len(
        [
            path
            for path in DATA.glob("*-assessment.json")
            if path.name != "assessment-case-matrix.json"
        ]
    )
    declared = index.get("totalAssessmentFiles")
    if declared != disk_count:
        errors.append(
            f"assessment-index.json: totalAssessmentFiles={declared} but {disk_count} files on disk"
        )
    return errors


def main() -> int:
    paths = sorted(DATA.glob("*-assessment.json"))
    all_errors: list[str] = []
    for path in paths:
        if path.name == "assessment-case-matrix.json":
            continue
        all_errors.extend(validate_file(path))
    all_errors.extend(smoke_evaluate_resource_types())
    all_errors.extend(validate_matrix_assessment_files())
    all_errors.extend(validate_index_counts())

    if all_errors:
        print("FAILED")
        for err in all_errors[:50]:
            print(f"- {err}")
        if len(all_errors) > 50:
            print(f"... and {len(all_errors) - 50} more")
        return 1

    print("PASSED")
    print(f"assessment_files={len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

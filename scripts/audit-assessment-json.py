#!/usr/bin/env python3
"""Audit assessment JSON files: used vs unused, index/matrix parity, quality gaps."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))

from app.assessment.catalog import get_assessment_for_arm_type  # noqa: E402
from app.assessment.what_if import lookup_what_if_scenario  # noqa: E402
from app.resource_type_map import ARM_PROVIDER_TO_INTERNAL  # noqa: E402
from app.resources.registry import ALL_RESOURCE_MODULES  # noqa: E402

REGION_BLOCK = {
    "policyFile": "region-governance-policy.json",
    "primaryApprovedRegion": "canadacentral",
    "secondaryApprovedRegion": "canadaeast",
    "approvedRegions": ["canadacentral", "canadaeast"],
}

ACTIONABLE_ACTIONS = frozenset({"downgrade", "upgrade", "stop_or_delete", "investigate"})
RULE_SECTIONS = (
    "recommendationRules",
    "assessmentRules",
    "bestOptimizationRules",
    "metricAssessmentRules",
    "propertyAssessmentRules",
    "actionOutcomeRules",
)
SKIP_ASSESSMENT_NAMES = frozenset({"assessment-case-matrix.json"})


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def assessment_paths() -> list[Path]:
    return sorted(
        path
        for path in DATA.glob("*-assessment.json")
        if path.name not in SKIP_ASSESSMENT_NAMES
    )


def monitor_arm_types() -> set[str]:
    types: set[str] = set()
    for mod in ALL_RESOURCE_MODULES:
        profile = getattr(mod, "MONITOR_PROFILE", None)
        if profile is not None:
            types.add(profile.monitor_arm_type.lower())
    return types


def consolidated_child_types(data: dict[str, Any]) -> set[str]:
    children = data.get("consolidatedChildResourceTypes") or []
    return {str(item) for item in children}


def audit() -> dict[str, Any]:
    index = _load_json(DATA / "assessment-index.json")
    matrix = _load_json(DATA / "assessment-case-matrix.json")
    thresholds = matrix.get("resourceCaseThresholds") or {}

    disk_files = {path.name for path in assessment_paths()}
    indexed_by_file: dict[str, list[str]] = defaultdict(list)
    indexed_types: list[str] = []
    consolidated_index_types: dict[str, str] = {}
    for item in index.get("items") or []:
        arm_type = str(item.get("resourceType") or "")
        assessment_file = str(item.get("assessmentFile") or "")
        if arm_type:
            indexed_types.append(arm_type)
        if assessment_file:
            indexed_by_file[assessment_file].append(arm_type)
            if item.get("consolidatedInto"):
                consolidated_index_types[arm_type] = str(item["consolidatedInto"])

    indexed_file_set = set(indexed_by_file)
    indexed_type_set = set(indexed_types)

    orphan_files = sorted(disk_files - indexed_file_set)
    missing_files = sorted(indexed_file_set - disk_files)

    matrix_stale_files: list[dict[str, str]] = []
    for resource_type, entry in thresholds.items():
        assessment_file = str(entry.get("assessmentFile") or "")
        if assessment_file and assessment_file not in disk_files:
            matrix_stale_files.append(
                {"resourceType": resource_type, "assessmentFile": assessment_file}
            )

    matrix_missing_index = sorted(set(thresholds) - indexed_type_set)
    index_missing_matrix = sorted(indexed_type_set - set(thresholds))

    type_mismatches: list[dict[str, str]] = []
    quality_gaps: dict[str, list[str]] = defaultdict(list)
    within_section_dupes: list[dict[str, Any]] = []

    for path in assessment_paths():
        data = _load_json(path)
        file_type = str(data.get("resourceType") or "")
        children = consolidated_child_types(data)

        for indexed_type in indexed_by_file.get(path.name, []):
            if indexed_type == file_type:
                continue
            if indexed_type in children:
                continue
            if consolidated_index_types.get(indexed_type) == file_type:
                continue
            type_mismatches.append(
                    {
                        "file": path.name,
                        "indexedType": indexed_type,
                        "fileType": file_type or "(missing)",
                    }
                )

        if not data.get("regionGovernance"):
            quality_gaps["missing_regionGovernance"].append(path.name)
        elif data["regionGovernance"].get("approvedRegions") != REGION_BLOCK["approvedRegions"]:
            quality_gaps["stale_regionGovernance"].append(path.name)

        if not data.get("pillarTriggers"):
            quality_gaps["missing_pillarTriggers"].append(path.name)

        if "best_unapproved_region" not in (data.get("whatIfScenarios") or {}):
            quality_gaps["missing_whatIf_best_unapproved_region"].append(path.name)

        section_ids: dict[str, list[str]] = defaultdict(list)
        for section in RULE_SECTIONS:
            for rule in data.get(section) or []:
                rule_id = str(rule.get("id") or "")
                if not rule_id:
                    continue
                section_ids[section].append(rule_id)
                if section not in {"recommendationRules", "bestOptimizationRules"}:
                    continue
                output = rule.get("output") or {}
                action = (
                    output.get("action")
                    or output.get("recommendationAction")
                    or rule.get("recommendationAction")
                )
                if action in ACTIONABLE_ACTIONS and not lookup_what_if_scenario(
                    data, rule_id, rule=rule
                ):
                    quality_gaps["missing_actionable_whatIf"].append(f"{path.name}:{rule_id}")

        for section, ids in section_ids.items():
            dupes = [rule_id for rule_id, count in Counter(ids).items() if count > 1]
            if dupes:
                within_section_dupes.append(
                    {"file": path.name, "section": section, "duplicateIds": dupes[:5]}
                )

    registry_types = monitor_arm_types()
    indexed_not_in_registry = sorted(
        arm_type
        for arm_type in indexed_types
        if arm_type.lower() not in registry_types
        and arm_type.lower() not in ARM_PROVIDER_TO_INTERNAL
    )

    catalog_misses = [
        arm_type
        for arm_type in indexed_types
        if get_assessment_for_arm_type(arm_type) is None
    ]

    return {
        "counts": {
            "assessmentFilesOnDisk": len(disk_files),
            "indexItems": len(indexed_types),
            "indexUniqueFiles": len(indexed_file_set),
            "indexTotalAssessmentFilesField": index.get("totalAssessmentFiles"),
            "matrixResourceTypes": len(thresholds),
            "registryMonitorArmTypes": len(registry_types),
        },
        "orphanFilesOnDisk": orphan_files,
        "indexedButMissingOnDisk": missing_files,
        "matrixStaleAssessmentFiles": matrix_stale_files,
        "matrixTypesMissingFromIndex": matrix_missing_index,
        "indexTypesMissingFromMatrix": index_missing_matrix,
        "indexTypeMismatches": type_mismatches,
        "catalogLookupMisses": catalog_misses,
        "indexedNotInResourceRegistry": indexed_not_in_registry,
        "qualityGaps": dict(quality_gaps),
        "withinSectionDuplicateRuleIds": within_section_dupes,
    }


def _print_report(report: dict[str, Any], *, verbose: bool) -> None:
    counts = report["counts"]
    print("=== Assessment JSON audit ===")
    print(
        f"files on disk: {counts['assessmentFilesOnDisk']} | "
        f"index items: {counts['indexItems']} | "
        f"unique indexed files: {counts['indexUniqueFiles']} | "
        f"index.totalAssessmentFiles: {counts['indexTotalAssessmentFilesField']}"
    )
    print(f"matrix resource types: {counts['matrixResourceTypes']}")

    sections = [
        ("orphanFilesOnDisk", "Orphan assessment files (disk, not in index)"),
        ("indexedButMissingOnDisk", "Indexed files missing on disk"),
        ("matrixTypesMissingFromIndex", "Matrix types missing from index"),
        ("indexTypesMissingFromMatrix", "Index types missing from matrix"),
        ("catalogLookupMisses", "Index types with catalog lookup miss"),
    ]
    for key, title in sections:
        items = report.get(key) or []
        print(f"\n{title}: {len(items)}")
        for item in items[:20 if not verbose else None]:
            print(f"  - {item}")
        if not verbose and len(items) > 20:
            print(f"  ... and {len(items) - 20} more")

    stale = report.get("matrixStaleAssessmentFiles") or []
    print(f"\nMatrix stale assessmentFile refs: {len(stale)}")
    for item in stale:
        print(f"  - {item['resourceType']} -> {item['assessmentFile']}")

    mismatches = report.get("indexTypeMismatches") or []
    print(f"\nIndex/file resourceType mismatches: {len(mismatches)}")
    for item in mismatches[:20 if not verbose else None]:
        print(
            f"  - {item['file']}: index={item['indexedType']} file={item['fileType']}"
        )

    gaps = report.get("qualityGaps") or {}
    print("\nQuality gaps:")
    for gap_name, items in sorted(gaps.items()):
        print(f"  {gap_name}: {len(items)}")
        if verbose and items:
            for item in items[:10]:
                print(f"    - {item}")

    dupes = report.get("withinSectionDuplicateRuleIds") or []
    print(f"\nWithin-section duplicate rule IDs: {len(dupes)}")
    if verbose and dupes:
        for item in dupes[:10]:
            print(f"  - {item['file']} {item['section']}: {item['duplicateIds']}")

    if counts["indexTotalAssessmentFilesField"] != counts["assessmentFilesOnDisk"]:
        print(
            "\nNOTE: assessment-index.json totalAssessmentFiles should equal "
            f"{counts['assessmentFilesOnDisk']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--verbose", action="store_true", help="Print detailed gap listings")
    args = parser.parse_args()

    report = audit()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report, verbose=args.verbose)

    critical = (
        report["orphanFilesOnDisk"]
        or report["indexedButMissingOnDisk"]
        or report["matrixStaleAssessmentFiles"]
        or report["matrixTypesMissingFromIndex"]
        or report["indexTypesMissingFromMatrix"]
        or report["catalogLookupMisses"]
        or report["indexTypeMismatches"]
        or report["qualityGaps"].get("missing_regionGovernance")
        or report["qualityGaps"].get("missing_pillarTriggers")
        or report["qualityGaps"].get("missing_actionable_whatIf")
        or report["withinSectionDuplicateRuleIds"]
        or report["counts"]["indexTotalAssessmentFilesField"]
        != report["counts"]["assessmentFilesOnDisk"]
    )
    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())

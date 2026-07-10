#!/usr/bin/env python3
"""Audit MONITOR_PROFILE metrics against Azure Monitor reference JSON.

Run: python3 scripts/audit-azure-monitor-profiles.py
Exit 1 when profile metrics are not documented for the ARM type.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REF_DIR = ROOT / "data" / "azure_monitor_reference"
sys.path.insert(0, str(ROOT))

from app.resources.registry import RESOURCE_MONITOR_PROFILES  # noqa: E402


def _load_reference(canonical_type: str) -> dict[str, Any] | None:
    path = REF_DIR / f"{canonical_type.replace('/', '-')}.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _documented_names(ref: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for row in ref.get("azure_documented_metrics") or []:
        if isinstance(row, str):
            names.add(row)
        elif isinstance(row, dict) and row.get("rest_api_name"):
            names.add(str(row["rest_api_name"]))
    return names


def _profile_rows(profile) -> list[dict[str, str]]:
    rows = []
    for metric in profile.metrics or ():
        rows.append({
            "metric_name": metric.metric_name,
            "fact_key": metric.fact_key,
        })
    return rows


def audit() -> int:
    issues: list[str] = []
    summary: list[dict[str, Any]] = []

    for profile in RESOURCE_MONITOR_PROFILES.values():
        ctype = profile.canonical_type
        ref = _load_reference(ctype)
        profile_metrics = _profile_rows(profile)

        entry: dict[str, Any] = {
            "canonical_type": ctype,
            "monitor_arm_type": profile.monitor_arm_type,
            "doc_ref": profile.doc_ref,
            "profile_metric_count": len(profile_metrics),
            "reference_file": bool(ref),
        }

        if not ref:
            entry["status"] = "missing_reference"
            issues.append(f"{ctype}: no reference file {ctype.replace('/', '-')}.json")
        else:
            documented = _documented_names(ref)
            undocumented = [
                m["metric_name"]
                for m in profile_metrics
                if m["metric_name"] not in documented
            ]
            entry["documented_metric_count"] = len(documented)
            entry["undocumented_profile_metrics"] = undocumented
            if undocumented:
                entry["status"] = "undocumented_metrics"
                issues.append(
                    f"{ctype}: profile metrics not in Azure doc: {', '.join(undocumented)}",
                )
            else:
                entry["status"] = "ok"

        summary.append(entry)

    print(json.dumps({"resources": summary, "issue_count": len(issues)}, indent=2))
    for issue in issues:
        print(f"ISSUE: {issue}", file=sys.stderr)

    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(audit())

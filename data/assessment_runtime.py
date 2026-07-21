#!/usr/bin/env python3
"""CLI wrapper for deterministic assessment runtime (validation / ad-hoc runs)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.assessment.catalog import get_assessment_for_arm_type, indexed_arm_types
from app.assessment.runtime import assess_resource


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Azure assessment runtime")
    parser.add_argument("input", help="Normalized resource JSON object or list")
    args = parser.parse_args()

    payload = load_json(Path(args.input))
    resources = payload if isinstance(payload, list) else [payload]
    results = []

    for resource in resources:
        resource_type = resource.get("resource_type")
        assessment = get_assessment_for_arm_type(resource_type or "")
        if not assessment:
            results.append({
                "resource_id": resource.get("resource_id"),
                "resource_type": resource_type,
                "error": "No assessment file for resource_type",
                "indexed_types": len(indexed_arm_types()),
            })
            continue
        results.append(assess_resource(assessment, resource))

    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

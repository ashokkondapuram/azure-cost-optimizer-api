#!/usr/bin/env python3
"""Add whatIfScenarios blocks to all assessment JSON files from recommendation rules."""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

sys.path.insert(0, str(ROOT))

from app.assessment.what_if import build_what_if_index  # noqa: E402


def main() -> int:
    updated = 0
    for path in sorted(DATA.glob("*-assessment.json")):
        if path.name == "assessment-case-matrix.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        scenarios = build_what_if_index(data)
        if not scenarios:
            continue
        data["whatIfScenarios"] = scenarios
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        updated += 1
        print(f"enriched {path.name} ({len(scenarios)} scenarios)")
    print(f"done: {updated} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Export optimization rules to frontend/src/data/rulesCatalog.json."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.optimizer.rule_catalog import list_all_rules, list_components

OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "src", "data", "rulesCatalog.json",
)

def main():
    data = {"components": list_components(), "rules": list_all_rules()}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"Wrote {len(data['rules'])} rules to {OUT}")

if __name__ == "__main__":
    main()

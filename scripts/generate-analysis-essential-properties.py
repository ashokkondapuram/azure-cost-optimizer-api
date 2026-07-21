#!/usr/bin/env python3
"""Generate analysisEssentialProperties.data.json from backend technical fetch specs."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.resources import list_technical_fetch_specs

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "src" / "utils" / "analysisEssentialProperties.data.json"

CORE_MATCHERS = [
    "status", "state", "powerstate", "power state",
    "sku", "type", "resourceid", "resource-id", "resource id",
    "provisioningstate", "provisioning state",
    "diskstate", "disk state",
    "lastsynced", "last synced",
    "version", "nodes", "kubernetesversion", "kubernetes version",
    "tier", "kind", "size", "vmsize", "vm size",
    "backend pools", "health probes",
]


def source_to_matchers(source: str) -> set[str]:
    matchers: set[str] = set()
    if source.startswith("props:"):
        path = source[6:]
        matchers.add(path.lower())
        leaf = path.split(".")[-1]
        matchers.add(leaf.lower())
        snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", leaf).lower()
        matchers.add(snake.replace("_", ""))
    elif source.startswith("row:"):
        matchers.add(source[4:].lower())
    elif source.startswith("sku:"):
        matchers.add("sku")
        matchers.add(source[4:].lower())
    elif source.startswith("tag:"):
        matchers.add(f"tag:{source[4:].lower()}")
        matchers.add(source[4:].lower())
    elif source.startswith("computed:"):
        matchers.add(source[9:].lower().replace("_", ""))
    return matchers


def main() -> None:
    by_type: dict[str, dict] = {}
    for spec in list_technical_fetch_specs():
        ct = spec["canonical_type"]
        matchers: set[str] = set()
        labels: set[str] = set()
        fact_keys: set[str] = set()
        for field in spec["technical_fields"]:
            if field["rules"]:
                fact_keys.add(field["fact_key"])
                labels.add(field["label"].lower())
                matchers.update(source_to_matchers(field["source"]))
        by_type[ct] = {
            "factKeys": sorted(fact_keys),
            "matchers": sorted(matchers),
            "labels": sorted(labels),
        }

    payload = {"coreMatchers": CORE_MATCHERS, "byCanonicalType": by_type}
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(by_type)} resource types)")


if __name__ == "__main__":
    main()

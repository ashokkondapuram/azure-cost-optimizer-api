"""Azure disk snapshot retention policy — loaded from data/snapshot_retention_policy.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "snapshot_retention_policy.json"


@lru_cache(maxsize=1)
def load_snapshot_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_snapshot_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def retention_policy() -> dict[str, Any]:
    return dict(load_snapshot_specifications().get("retention_policy") or {})


def pricing_config() -> dict[str, Any]:
    return dict(load_snapshot_specifications().get("pricing") or {})

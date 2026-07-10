"""Azure Storage Account metrics thresholds — loaded from data/storage_account_metrics_thresholds.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "storage_account_metrics_thresholds.json"


@lru_cache(maxsize=1)
def load_storage_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_storage_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def access_tier_spec(tier_name: str | None) -> dict[str, Any]:
    specs = load_storage_specifications()
    tiers = specs.get("access_tiers") or {}
    key = (tier_name or "Hot").strip().title()
    return dict(tiers.get(key) or tiers.get("Hot") or {})

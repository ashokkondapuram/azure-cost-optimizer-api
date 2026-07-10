"""Azure Container Registry tier specifications — loaded from data/acr_tier_specifications.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "acr_tier_specifications.json"


@lru_cache(maxsize=1)
def load_acr_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_acr_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def tier_spec(tier_name: str | None) -> dict[str, Any]:
    specs = load_acr_specifications()
    tiers = specs.get("tiers") or {}
    key = (tier_name or "Standard").strip().title()
    if key not in tiers and tier_name:
        key = tier_name.strip()
    return dict(tiers.get(key) or tiers.get("Standard") or {})

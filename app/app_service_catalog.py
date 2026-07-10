"""Azure App Service tier specifications — loaded from data/app_service_tier_specifications.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "app_service_tier_specifications.json"


@lru_cache(maxsize=1)
def load_app_service_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_app_service_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def tier_spec(tier_name: str | None) -> dict[str, Any]:
    specs = load_app_service_specifications()
    tiers = specs.get("tiers") or {}
    key = (tier_name or "Standard").strip().title()
    return dict(tiers.get(key) or {})

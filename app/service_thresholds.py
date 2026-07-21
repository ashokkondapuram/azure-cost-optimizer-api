"""Load per-service optimization thresholds from *-assessment.json (single source per type)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.assessment.config_resolver import load_optimization_thresholds, load_resource_config


@lru_cache(maxsize=32)
def load_service_specifications(canonical_type: str) -> dict[str, Any]:
    return load_resource_config(canonical_type)


def optimization_thresholds(canonical_type: str) -> dict[str, float]:
    return load_optimization_thresholds(canonical_type)


def threshold_values(rule: Any, canonical_type: str, **keys: str) -> dict[str, float]:
    """Merge JSON defaults with rule overrides for named threshold keys."""
    defaults = optimization_thresholds(canonical_type)
    out: dict[str, float] = {}
    for out_key, src_key in keys.items():
        rule_attr = src_key if hasattr(rule, src_key) else out_key
        default = defaults.get(src_key, defaults.get(out_key, 0.0))
        out[out_key] = float(getattr(rule, rule_attr, default) or default)
    return out

"""Resource-level filters and severity context for the optimization engine."""

from __future__ import annotations

import re
from typing import Any

NONPROD_ENV_VALUES = frozenset({
    "dev", "development", "test", "testing", "qa", "staging", "stage", "sandbox", "nonprod", "non-prod",
})

DEFAULT_GLOBAL_CONFIG: dict[str, Any] = {
    "exclude_tags": {"doNotOptimize": {"true", "1", "yes"}},
    "exclude_resource_group_patterns": [],
    "exclude_resource_types": [],
    "nonprod_tag_keys": ("environment", "env"),
    "nonprod_severity_cap": "MEDIUM",
}


def merge_global_config(overrides: dict | None) -> dict[str, Any]:
    merged = dict(DEFAULT_GLOBAL_CONFIG)
    if overrides:
        merged.update(overrides)
    return merged


def _tag_value_matches(tags: dict, key: str, blocked: set[str]) -> bool:
    val = str(tags.get(key) or "").strip().lower()
    return val in {v.lower() for v in blocked}


def should_skip_resource(resource: dict, global_config: dict | None = None) -> bool:
    """True when tag/RG/type filters exclude a resource from analysis."""
    cfg = merge_global_config(global_config)
    tags = resource.get("tags") or {}
    for tag_key, blocked_vals in (cfg.get("exclude_tags") or {}).items():
        blocked = blocked_vals if isinstance(blocked_vals, set) else set(blocked_vals or [])
        if _tag_value_matches(tags, tag_key, blocked):
            return True

    rtype = (resource.get("type") or "").strip().lower()
    excluded_types = {t.lower() for t in (cfg.get("exclude_resource_types") or [])}
    if rtype and rtype in excluded_types:
        return True

    rg = (resource.get("resourceGroup") or resource.get("resource_group") or "").strip()
    for pattern in cfg.get("exclude_resource_group_patterns") or []:
        if pattern and re.search(str(pattern), rg, re.IGNORECASE):
            return True
    return False


def resource_environment(tags: dict | None) -> str:
    tags = tags or {}
    for key in ("environment", "env", "Environment", "Env"):
        val = str(tags.get(key) or "").strip().lower()
        if val:
            return val
    return "prod"


def is_nonprod_resource(resource: dict) -> bool:
    return resource_environment(resource.get("tags") or {}) in NONPROD_ENV_VALUES


def effective_severity(rule_severity: str, resource: dict, global_config: dict | None = None) -> str:
    """Cap severity for non-prod workloads when configured."""
    cfg = merge_global_config(global_config)
    cap = str(cfg.get("nonprod_severity_cap") or "").upper()
    sev = str(rule_severity or "MEDIUM").upper()
    if not cap or not is_nonprod_resource(resource):
        return sev
    order = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
    if sev in order and cap in order and order.index(sev) < order.index(cap):
        return cap
    return sev


def apply_waste_score_multiplier(score: int, overrides: dict | None) -> int:
    multiplier = float((overrides or {}).get("waste_score_multiplier") or 1.0)
    return max(0, min(100, int(round(score * multiplier))))

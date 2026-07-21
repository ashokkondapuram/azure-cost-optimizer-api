"""Configurable weights and tier thresholds for the advanced optimization engine."""
from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_WEIGHTS: dict[str, float] = {
    "cost": 0.30,
    "safety": 0.25,
    "effort": 0.15,
    "workload": 0.20,
    "business": 0.10,
}

TIER_THRESHOLDS = {
    "tier1_min_overall": 75.0,
    "tier1_max_perf_risk": 20.0,
    "tier1_max_blast_radius": 1,
    "tier2_min_overall": 60.0,
    "tier2_max_perf_risk": 40.0,
    "tier2_max_blast_radius": 3,
    "tier3_min_overall": 40.0,
}

CRITICALITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
SLA_RISK = {"gold": 90.0, "silver": 50.0, "bronze": 25.0, "none": 0.0}

BUSINESS_TAG_KEYS = (
    "business-criticality",
    "businesscriticality",
    "criticality",
)
SLA_TAG_KEYS = ("sla-tier", "slatier", "sla")
ENV_TAG_KEYS = ("environment", "env")
COMPLIANCE_LOCK_KEYS = ("compliance-locked", "compliancelocked", "change-locked")


def load_weights() -> dict[str, float]:
    raw = os.environ.get("ADVANCED_ENGINE_WEIGHTS", "").strip()
    if not raw:
        return dict(DEFAULT_WEIGHTS)
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return dict(DEFAULT_WEIGHTS)
        merged = dict(DEFAULT_WEIGHTS)
        for key, value in parsed.items():
            if key in merged:
                merged[key] = float(value)
        total = sum(merged.values())
        if total <= 0:
            return dict(DEFAULT_WEIGHTS)
        return {k: v / total for k, v in merged.items()}
    except (TypeError, ValueError, json.JSONDecodeError):
        return dict(DEFAULT_WEIGHTS)


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, round(value, 2)))

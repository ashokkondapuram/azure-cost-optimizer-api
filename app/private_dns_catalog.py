"""Azure Private DNS zone cost model — loaded from data/private_dns_zone_cost_model.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "private_dns_zone_cost_model.json"


@lru_cache(maxsize=1)
def load_private_dns_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_private_dns_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def pricing_config() -> dict[str, Any]:
    return dict(load_private_dns_specifications().get("pricing") or {})


def zone_monthly_usd() -> float:
    return float(pricing_config().get("zone_monthly_usd") or 0.50)


def parse_private_dns_arm(zone: dict[str, Any]) -> dict[str, Any]:
    props = zone.get("properties") or {}
    facts = zone.get("_technical_facts") or {}
    record_count = facts.get("record_set_count")
    if record_count is None:
        record_count = props.get("numberOfRecordSets")
    return {
        "record_set_count": record_count,
        "zone_name": zone.get("name") or "",
    }

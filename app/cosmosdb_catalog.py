"""Azure Cosmos DB pricing models and ARM account parsing."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "cosmosdb_pricing_models.json"

_API_BY_CAPABILITY = {
    "enablemongo": "MongoDB",
    "enablecassandra": "Cassandra",
    "enablegremlin": "Gremlin",
    "enabletable": "Table",
}


@lru_cache(maxsize=1)
def load_cosmosdb_pricing_models() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    try:
        from it_services.database_cosmosdb.assessment_bridge import optimization_thresholds as assessment_thresholds

        raw = assessment_thresholds()
        if raw:
            return {
                "ru_low_pct": float(raw.get("ru_low_pct", raw.get("cosmos_ru_low_pct", 20.0))),
                "ru_high_pct": float(raw.get("ru_high_pct", raw.get("cosmos_ru_high_pct", 80.0))),
                "ru_throttle_pct": float(raw.get("ru_throttle_pct", raw.get("cosmos_throttle_ru_pct", 95.0))),
                "serverless_ru_threshold_7d": float(
                    raw.get("serverless_ru_threshold_7d", raw.get("cosmos_serverless_ru_threshold", 50000.0))
                ),
                "index_to_data_ratio": float(
                    raw.get("index_to_data_ratio", raw.get("cosmos_index_to_data_ratio", 1.5))
                ),
                "large_item_bytes": float(raw.get("large_item_bytes", raw.get("cosmos_large_item_bytes", 2097152.0))),
                "hot_partition_skew_ratio": float(
                    raw.get("hot_partition_skew_ratio", raw.get("cosmos_hot_partition_skew_ratio", 2.5))
                ),
                "replication_lag_ms": float(
                    raw.get("replication_lag_ms", raw.get("cosmos_replication_lag_ms", 100.0))
                ),
                "min_downgrade_savings_pct": float(raw.get("min_downgrade_savings_pct", 30.0)),
                "min_monthly_savings_usd": float(raw.get("min_monthly_savings_usd", 5.0)),
                "evaluation_window_days": float(raw.get("evaluation_window_days", 7.0)),
            }
    except Exception:
        pass
    specs = load_cosmosdb_pricing_models()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def api_type_spec(api_type: str | None) -> dict[str, Any]:
    specs = load_cosmosdb_pricing_models()
    return dict((specs.get("api_types") or {}).get(api_type or "Sql") or {})


def regional_multiplier(location: str | None) -> float:
    specs = load_cosmosdb_pricing_models()
    examples = (specs.get("regional_multipliers") or {}).get("examples") or {}
    key = (location or "").replace(" ", "").lower()
    if key in examples:
        return float(examples[key])
    return float((specs.get("regional_multipliers") or {}).get("baseline") or 1.0)


def consistency_multiplier(level: str | None) -> float:
    specs = load_cosmosdb_pricing_models()
    entry = (specs.get("consistency_levels") or {}).get(level or "Session") or {}
    return float(entry.get("ru_multiplier") or 1.0)


def _capability_names(capabilities: list[Any]) -> set[str]:
    names: set[str] = set()
    for cap in capabilities or []:
        if isinstance(cap, dict):
            name = cap.get("name") or ""
        else:
            name = str(cap)
        if name:
            names.add(str(name).lower())
    return names


def _infer_api_type(kind: str, capabilities: list[Any]) -> str:
    caps = _capability_names(capabilities)
    for cap_key, api in _API_BY_CAPABILITY.items():
        if cap_key in caps:
            return api
    kind_lower = (kind or "").lower()
    api_types = load_cosmosdb_pricing_models().get("api_types") or {}
    for api_name, meta in api_types.items():
        for arm_kind in meta.get("arm_kinds") or []:
            if kind_lower == str(arm_kind).lower():
                return api_name
    if "mongodb" in kind_lower:
        return "MongoDB"
    return "Sql"


def parse_cosmos_arm_account(account: dict[str, Any]) -> dict[str, Any]:
    """Normalize throughput model, API, regions, and consistency from ARM."""
    props = account.get("properties") or {}
    kind = (account.get("kind") or props.get("kind") or "").strip()
    capabilities = props.get("capabilities") or []
    caps = _capability_names(capabilities)
    serverless = "enableserverless" in caps
    locations = props.get("locations") or []
    region_names = [
        str(loc.get("locationName") or loc.get("name") or "").strip()
        for loc in locations
        if isinstance(loc, dict)
    ]
    region_names = [r for r in region_names if r]
    consistency = (props.get("consistencyPolicy") or {}).get("defaultConsistencyLevel") or "Session"
    api_type = _infer_api_type(kind, capabilities)
    api_meta = api_type_spec(api_type)
    return {
        "kind": kind,
        "api_type": api_type,
        "api_ru_multiplier": float(api_meta.get("ru_cost_multiplier") or 1.0),
        "serverless_enabled": serverless,
        "provisioned_model": "serverless" if serverless else "provisioned",
        "free_tier_enabled": bool(props.get("enableFreeTier")),
        "automatic_failover_enabled": bool(props.get("enableAutomaticFailover")),
        "multi_write_enabled": bool(props.get("enableMultipleWriteLocations")),
        "region_count": len(region_names) or 1,
        "regions": region_names,
        "consistency_level": consistency,
        "consistency_ru_multiplier": consistency_multiplier(consistency),
        "offer_type": props.get("databaseAccountOfferType") or "",
        "regional_multiplier": regional_multiplier(account.get("location")),
        "capabilities": list(caps),
    }

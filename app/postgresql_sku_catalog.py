"""Azure Database for PostgreSQL Flexible Server SKU specifications."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "postgresql_sku_specifications.json"

_TIER_ALIASES = {
    "burstable": "Burstable",
    "b": "Burstable",
    "generalpurpose": "GeneralPurpose",
    "gp": "GeneralPurpose",
    "memoryoptimized": "MemoryOptimized",
    "mo": "MemoryOptimized",
}


@lru_cache(maxsize=1)
def load_postgresql_sku_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_postgresql_sku_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def normalize_pg_tier_name(raw: str | None) -> str:
    text = (raw or "").strip().lower().replace("_", "").replace("-", "")
    if not text:
        return ""
    return _TIER_ALIASES.get(text, raw.strip())


def tier_spec(tier_name: str | None) -> dict[str, Any]:
    specs = load_postgresql_sku_specifications()
    tiers = specs.get("tiers") or {}
    canonical = normalize_pg_tier_name(tier_name)
    return dict(tiers.get(canonical) or {})


def ha_mode_spec(mode: str | None) -> dict[str, Any]:
    specs = load_postgresql_sku_specifications()
    modes = specs.get("ha_modes") or {}
    key = (mode or "Disabled").strip()
    if key not in modes and key.lower() == "disabled":
        return dict(modes.get("Disabled") or {})
    return dict(modes.get(key) or {})


def _parse_major_version(version: str | None) -> int | None:
    if not version:
        return None
    match = re.match(r"(\d+)", str(version).strip())
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _infer_tier_from_sku(sku_name: str, tier: str) -> str:
    normalized = normalize_pg_tier_name(tier)
    if normalized:
        return normalized
    lower = (sku_name or "").lower()
    if lower.startswith("standard_b"):
        return "Burstable"
    if lower.startswith("standard_e"):
        return "MemoryOptimized"
    if lower.startswith("standard_d"):
        return "GeneralPurpose"
    return normalized or "GeneralPurpose"


def _extract_vcores(sku_name: str) -> int | None:
    match = re.search(r"_([bde])(\d+)", (sku_name or "").lower())
    if not match:
        return None
    try:
        return int(match.group(2))
    except ValueError:
        return None


def parse_postgresql_arm_server(server: dict[str, Any]) -> dict[str, Any]:
    """Normalize tier, HA, backup, storage, and replica metadata from ARM."""
    props = server.get("properties") or {}
    sku = server.get("sku") or {}
    sku_name = (sku.get("name") or "").strip()
    tier_raw = (sku.get("tier") or "").strip()
    tier = _infer_tier_from_sku(sku_name, tier_raw)
    storage = props.get("storage") or {}
    backup = props.get("backup") or {}
    ha = props.get("highAvailability") or {}
    ha_mode = (ha.get("mode") or "Disabled").strip()
    ha_enabled = ha_mode.lower() not in ("", "disabled", "none")
    version = props.get("version") or ""
    major = _parse_major_version(version)
    supported = load_postgresql_sku_specifications().get("supported_major_versions") or []
    latest = max(supported) if supported else None
    return {
        "sku_name": sku_name,
        "tier": tier,
        "tier_raw": tier_raw,
        "vcores": _extract_vcores(sku_name),
        "storage_gb": int(storage.get("storageSizeGB") or 0),
        "storage_tier": storage.get("tier"),
        "state": (props.get("state") or "").strip(),
        "version": version,
        "major_version": major,
        "version_outdated": (
            major is not None and latest is not None
            and major < latest - int(optimization_thresholds().get("version_lag_major_releases", 2))
        ),
        "ha_mode": ha_mode,
        "ha_enabled": ha_enabled,
        "ha_cost_multiplier": float(ha_mode_spec(ha_mode).get("cost_multiplier") or 1.0),
        "backup_retention_days": int(backup.get("retentionDays") or 0),
        "geo_redundant_backup": bool(backup.get("geoRedundantBackup")),
        "is_read_replica": bool(props.get("sourceServerResourceId")),
        "source_server_id": props.get("sourceServerResourceId"),
        "replication_role": props.get("replicationRole"),
    }


def suggested_smaller_sku(sku_name: str) -> str | None:
    """Suggest next smaller D/E/B SKU within same family when possible."""
    lower = (sku_name or "").lower()
    match = re.match(r"(standard_[bde])(\d+)(s?)(_v\d+)?", lower)
    if not match:
        return None
    family, cores, suffix, version = match.groups()
    try:
        current = int(cores)
    except ValueError:
        return None
    if current <= 2:
        return None
    next_cores = max(2, current // 2)
    family_label = {"standard_b": "Standard_B", "standard_d": "Standard_D", "standard_e": "Standard_E"}[family]
    return f"{family_label}{next_cores}{suffix or ''}{version or ''}"


def suggested_larger_sku(sku_name: str) -> str | None:
    lower = (sku_name or "").lower()
    match = re.match(r"(standard_[bde])(\d+)(s?)(_v\d+)?", lower)
    if not match:
        return None
    family, cores, suffix, version = match.groups()
    try:
        current = int(cores)
    except ValueError:
        return None
    family_label = {"standard_b": "Standard_B", "standard_d": "Standard_D", "standard_e": "Standard_E"}[family]
    return f"{family_label}{current * 2}{suffix or ''}{version or ''}"

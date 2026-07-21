"""Engine configuration store — persisted in PostgreSQL.

Allows operators to:
  - Enable/disable individual rules
  - Override any rule threshold (cpu_idle_pct, node_cpu_idle, etc.)
  - Create named configuration profiles (e.g. 'aggressive', 'conservative')
  - Assign profiles per subscription or resource group
  - Inherit from a parent profile via `extends`
"""
from __future__ import annotations
import threading
import uuid
from sqlalchemy.orm import Session
from app.models import EngineConfig
import json
from cachetools import TTLCache

PROFILE_INHERITANCE: dict[str, str] = {
    "aggressive": "default",
    "conservative": "default",
}

GLOBAL_CONFIG_KEY = "__global__"

_config_cache: TTLCache = TTLCache(maxsize=64, ttl=300)
_config_cache_lock = threading.Lock()


def invalidate_engine_config_cache(profile: str | None = None) -> None:
    """Drop cached profile overrides after config CRUD."""
    with _config_cache_lock:
        if profile:
            _config_cache.pop(profile.strip().lower(), None)
        else:
            _config_cache.clear()


def _load_effective_config_uncached(db: Session, profile: str) -> dict:
    chain: list[str] = []
    current = profile
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        chain.append(current)
        current = PROFILE_INHERITANCE.get(current)

    merged: dict[str, dict] = {}
    for name in reversed(chain):
        merged.update(_load_profile_rows(db, name))
    return merged


def _load_profile_rows(db: Session, profile: str) -> dict[str, dict]:
    rows = db.query(EngineConfig).filter(EngineConfig.profile == profile).all()
    overrides: dict[str, dict] = {}
    for row in rows:
        try:
            rule_overrides = json.loads(row.overrides_json or "{}")
        except Exception:
            rule_overrides = {}
        if not row.enabled:
            rule_overrides["enabled"] = False
        overrides[row.rule_id] = rule_overrides
    return overrides


def get_effective_config(db: Session, profile: str = "default") -> dict:
    """Load rule overrides for a named profile, applying inheritance chain."""
    key = (profile or "default").strip().lower()
    with _config_cache_lock:
        if key in _config_cache:
            return dict(_config_cache[key])
    cfg = _load_effective_config_uncached(db, key)
    with _config_cache_lock:
        _config_cache[key] = dict(cfg)
    return cfg


def get_global_engine_config(db: Session, profile: str = "default") -> dict:
    """Tag/RG filters and severity context stored under __global__ rule id."""
    cfg = get_effective_config(db, profile)
    return dict(cfg.get(GLOBAL_CONFIG_KEY) or {})


def get_profile_metadata(db: Session, profile: str) -> dict:
    rows = db.query(EngineConfig).filter(EngineConfig.profile == profile).all()
    return {
        "profile": profile,
        "extends": PROFILE_INHERITANCE.get(profile),
        "rule_count": len(rows),
        "updated_rules": [r.rule_id for r in rows],
    }


def compare_profiles(db: Session, *profiles: str) -> dict:
    """Diff rule overrides across profiles for config dashboard API."""
    names = profiles or tuple(PROFILE_INHERITANCE.keys()) + ("default",)
    data = {name: get_effective_config(db, name) for name in names}
    all_rules = sorted({rid for cfg in data.values() for rid in cfg})
    return {
        "profiles": list(names),
        "rules": all_rules,
        "values": {
            rule_id: {profile: (data[profile].get(rule_id) or {}) for profile in names}
            for rule_id in all_rules
        },
    }


def validate_profile_config(db: Session, profile: str, draft: dict[str, dict] | None = None) -> dict:
    """Validate rule overrides for a profile (unknown rules, threshold bounds)."""
    from app.optimizer.rule_registry import ALL_KNOWN_RULE_IDS

    effective = get_effective_config(db, profile)
    if draft:
        effective = {**effective, **draft}
    issues: list[dict] = []
    for rule_id, overrides in effective.items():
        if rule_id == GLOBAL_CONFIG_KEY:
            continue
        if rule_id not in ALL_KNOWN_RULE_IDS:
            issues.append({"rule_id": rule_id, "field": None, "error": "Unknown rule id"})
            continue
        for key, value in (overrides or {}).items():
            if key == "enabled":
                continue
            if key == "min_monthly_savings_usd" and value is not None and float(value) < 0:
                issues.append({"rule_id": rule_id, "field": key, "error": "Must be >= 0"})
            if key == "waste_score_multiplier" and value is not None and float(value) <= 0:
                issues.append({"rule_id": rule_id, "field": key, "error": "Must be > 0"})
            if key == "evaluation_window_days" and value is not None and int(value) < 1:
                issues.append({"rule_id": rule_id, "field": key, "error": "Must be >= 1 day"})
    return {
        "profile": profile,
        "valid": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "extends": PROFILE_INHERITANCE.get(profile),
    }


def upsert_rule_config(
    db: Session,
    profile: str,
    rule_id: str,
    overrides: dict,
    enabled: bool = True,
    description: str = "",
) -> EngineConfig:
    row = db.query(EngineConfig).filter(
        EngineConfig.profile == profile,
        EngineConfig.rule_id  == rule_id,
    ).first()
    if row:
        row.overrides_json = json.dumps(overrides)
        row.enabled        = enabled
        row.description    = description
    else:
        row = EngineConfig(
            id=str(uuid.uuid4()),
            profile=profile, rule_id=rule_id,
            overrides_json=json.dumps(overrides),
            enabled=enabled, description=description,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_engine_config_cache(profile)
    return row


def delete_rule_config(db: Session, profile: str, rule_id: str) -> bool:
    row = db.query(EngineConfig).filter(
        EngineConfig.profile == profile,
        EngineConfig.rule_id  == rule_id,
    ).first()
    if row:
        db.delete(row)
        db.commit()
        invalidate_engine_config_cache(profile)
        return True
    return False

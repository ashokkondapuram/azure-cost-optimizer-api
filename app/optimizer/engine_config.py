"""Engine configuration store — persisted in PostgreSQL.

Allows operators to:
  - Enable/disable individual rules
  - Override any rule threshold (cpu_idle_pct, node_cpu_idle, etc.)
  - Create named configuration profiles (e.g. 'aggressive', 'conservative')
  - Assign profiles per subscription or resource group
"""
from __future__ import annotations
import uuid
from sqlalchemy.orm import Session
from app.models import EngineConfig
import json


def get_effective_config(db: Session, profile: str = "default") -> dict:
    """Load rule overrides for a named profile from DB."""
    rows = db.query(EngineConfig).filter(EngineConfig.profile == profile).all()
    overrides: dict = {}
    for row in rows:
        try:
            rule_overrides = json.loads(row.overrides_json or "{}")
        except Exception:
            rule_overrides = {}
        if not row.enabled:
            rule_overrides["enabled"] = False
        overrides[row.rule_id] = rule_overrides
    return overrides


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
    return row


def delete_rule_config(db: Session, profile: str, rule_id: str) -> bool:
    row = db.query(EngineConfig).filter(
        EngineConfig.profile == profile,
        EngineConfig.rule_id  == rule_id,
    ).first()
    if row:
        db.delete(row)
        db.commit()
        return True
    return False

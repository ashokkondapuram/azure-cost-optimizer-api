"""Load assessment-index.json and lazy-load per-resource assessment JSON files."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT / "data"


def assessment_data_dir() -> Path:
    override = (os.getenv("ASSESSMENT_DATA_DIR") or "").strip()
    if override:
        return Path(override)
    return DEFAULT_DATA_DIR


@lru_cache(maxsize=1)
def load_assessment_index() -> dict[str, Any]:
    path = assessment_data_dir() / "assessment-index.json"
    if not path.is_file():
        return {"items": []}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _arm_type_to_file() -> dict[str, str]:
    index = load_assessment_index()
    mapping: dict[str, str] = {}
    for item in index.get("items") or []:
        arm_type = (item.get("resourceType") or "").strip()
        assessment_file = (item.get("assessmentFile") or "").strip()
        if arm_type and assessment_file:
            mapping[arm_type.lower()] = assessment_file
    return mapping


def indexed_arm_types() -> frozenset[str]:
    return frozenset(_arm_type_to_file().keys())


@lru_cache(maxsize=256)
def get_assessment_for_arm_type(arm_type: str) -> dict[str, Any] | None:
    key = (arm_type or "").strip().lower()
    filename = _arm_type_to_file().get(key)
    if not filename:
        return None
    path = assessment_data_dir() / filename
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    data["_file"] = filename
    return data


def clear_assessment_cache() -> None:
    load_assessment_index.cache_clear()
    _arm_type_to_file.cache_clear()
    get_assessment_for_arm_type.cache_clear()
    collect_assessment_rule_ids.cache_clear()


@lru_cache(maxsize=1)
def collect_assessment_rule_ids() -> tuple[str, ...]:
    """All rule ids declared in assessment JSON recommendation/assessment sections."""
    ids: set[str] = set()
    data_dir = assessment_data_dir()
    for filename in sorted(set(_arm_type_to_file().values())):
        path = data_dir / filename
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        schema = str(data.get("schema_version") or data.get("schemaVersion") or "")
        if schema.startswith("2"):
            for rule in data.get("rules") or []:
                rid = str(rule.get("rule_id") or rule.get("id") or "").strip()
                if rid:
                    ids.add(rid)
            continue
        for section in (
            "assessmentRules",
            "recommendationRules",
            "bestOptimizationRules",
        ):
            for rule in data.get(section) or []:
                rid = str(rule.get("id") or "").strip()
                if rid:
                    ids.add(rid)
    return tuple(sorted(ids))

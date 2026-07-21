"""Load per-service Azure SKU specifications from it_services/<pkg>/data/sku_specs.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from it_services.registry import package_for_service_id, services_by_canonical_type, services_by_id

ROOT = Path(__file__).resolve().parents[1]


def sku_specs_path(package: str) -> Path:
    return ROOT / "it_services" / package / "data" / "sku_specs.json"


@lru_cache(maxsize=256)
def load_sku_specs_for_package(package: str) -> dict[str, Any]:
    path = sku_specs_path(package)
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_sku_specs_for_canonical(canonical_type: str) -> dict[str, Any]:
    row = services_by_canonical_type().get((canonical_type or "").strip().lower())
    if not row:
        return {}
    package = package_for_service_id(row["service_id"])
    return load_sku_specs_for_package(package)


def load_sku_specs_for_service_id(service_id: str) -> dict[str, Any]:
    row = services_by_id().get(service_id)
    if not row:
        return {}
    package = package_for_service_id(service_id)
    return load_sku_specs_for_package(package)


def load_sku_specs_for_arm_type(arm_type: str) -> dict[str, Any]:
    from it_services.registry import services_by_arm_type

    row = services_by_arm_type().get((arm_type or "").strip().lower())
    if not row:
        return {}
    return load_sku_specs_for_service_id(row["service_id"])


def sku_summary(spec: dict[str, Any]) -> dict[str, Any]:
    """Compact SKU block for normalized snapshots."""
    if not spec:
        return {}
    return {
        "schema_version": spec.get("schema_version"),
        "service_id": spec.get("service_id"),
        "canonical_type": spec.get("canonical_type"),
        "arm_type": spec.get("arm_type"),
        "sku_count": len(spec.get("skus") or {}),
        "documentation": spec.get("documentation") or {},
        "pricing_model": (spec.get("pricing") or {}).get("billing_model"),
        "source": spec.get("source"),
        "synced_at": spec.get("synced_at"),
    }

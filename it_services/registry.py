"""Central registry for IT service entities (profiles, engines, assessment mapping)."""

from __future__ import annotations

import importlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVICE_REGISTRY_PATH = ROOT / "packages" / "costoptimizer-core" / "service_registry.json"
ASSESSMENT_INDEX_PATH = ROOT / "data" / "assessment-index.json"


def _service_id_to_package(service_id: str) -> str:
    return service_id.replace("-", "_")


@lru_cache(maxsize=1)
def load_service_registry() -> list[dict[str, Any]]:
    with SERVICE_REGISTRY_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def services_by_id() -> dict[str, dict[str, Any]]:
    return {row["service_id"]: row for row in load_service_registry()}


@lru_cache(maxsize=1)
def services_by_arm_type() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in load_service_registry():
        arm = (row.get("arm_type") or "").strip()
        if arm:
            out[arm.lower()] = row
    return out


@lru_cache(maxsize=1)
def services_by_canonical_type() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in load_service_registry():
        canonical = (row.get("canonical_type") or "").strip().lower()
        if canonical:
            out[canonical] = row
    return out


def package_for_service_id(service_id: str) -> str:
    return _service_id_to_package(service_id)


def import_profile_module(package: str, *, filename: str = "resource_profile.py") -> Any:
    """Load a profile module without executing package __init__ (avoids engine import cycles)."""
    import importlib.util

    path = ROOT / "it_services" / package / filename
    if not path.is_file():
        raise ModuleNotFoundError(f"it_services.{package}.{filename}")
    module_name = f"it_services.{package}.{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(module_name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def import_service_entity(package: str) -> Any | None:
    try:
        return importlib.import_module(f"it_services.{package}.service")
    except ModuleNotFoundError:
        return None


@lru_cache(maxsize=1)
def _engine_meta_by_service_id() -> dict[str, dict[str, Any]]:
    path = ROOT / "it_services" / "_engine_catalog.json"
    if not path.is_file():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {row["service_id"]: row for row in rows}


def import_sub_engine_class(package: str) -> type | None:
    """Import sub-engine class on demand (avoid during registry scans)."""
    try:
        mod = importlib.import_module(f"it_services.{package}.engine.sub_engine")
    except ModuleNotFoundError:
        return None
    for attr in dir(mod):
        if attr.endswith("SubEngine") and attr != "ResourceSubEngine":
            return getattr(mod, attr)
    return None


@lru_cache(maxsize=1)
def assessment_file_by_arm_type() -> dict[str, str]:
    if not ASSESSMENT_INDEX_PATH.is_file():
        return {}
    with ASSESSMENT_INDEX_PATH.open(encoding="utf-8") as fh:
        index = json.load(fh)
    mapping: dict[str, str] = {}
    for item in index.get("items") or []:
        arm = (item.get("resourceType") or "").strip().lower()
        filename = (item.get("assessmentFile") or "").strip()
        if arm and filename:
            mapping[arm] = filename
    return mapping


def all_profile_modules() -> list[Any]:
    """Load one resource_profile module per registered service."""
    modules: list[Any] = []
    for row in load_service_registry():
        package = package_for_service_id(row["service_id"])
        try:
            modules.append(import_profile_module(package))
        except ModuleNotFoundError:
            continue
    try:
        modules.append(import_profile_module("database_sql", filename="sql_database_profile.py"))
    except ModuleNotFoundError:
        pass
    return modules


def service_entity(package: str) -> dict[str, Any]:
    """Return a plain dict describing one IT service's working entities."""
    row = next(
        (r for r in load_service_registry() if package_for_service_id(r["service_id"]) == package),
        {},
    )
    profile = import_profile_module(package)
    monitor = getattr(profile, "MONITOR_PROFILE", None)
    arm_type = (getattr(monitor, "monitor_arm_type", None) or row.get("arm_type") or "").lower()
    engine_row = _engine_meta_by_service_id().get(row.get("service_id") or "", {})
    return {
        "service_id": row.get("service_id"),
        "package": package,
        "canonical_type": row.get("canonical_type"),
        "arm_type": arm_type or row.get("arm_type"),
        "display_name": row.get("display_name"),
        "api_slug": row.get("api_slug"),
        "component": row.get("component"),
        "has_engine": bool(engine_row.get("class_name")),
        "sub_engine_class": engine_row.get("class_name"),
        "assessment_file": assessment_file_by_arm_type().get(arm_type or ""),
        "monitor_profile": monitor,
        "technical_fetch_spec": getattr(profile, "TECHNICAL_FETCH_SPEC", None),
    }


def list_service_entities() -> list[dict[str, Any]]:
    return [
        service_entity(package_for_service_id(row["service_id"]))
        for row in load_service_registry()
    ]

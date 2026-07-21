"""Load curated Azure free/trial tier metadata from Microsoft documentation."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_REFERENCE_PATH = Path(__file__).resolve().parents[1] / "data" / "azure_free_tier_reference.json"
_OFFICIAL_PATH = Path(__file__).resolve().parents[1] / "data" / "azure_official_free_services.json"


@lru_cache(maxsize=1)
def load_free_tier_reference() -> dict[str, Any]:
    if not _REFERENCE_PATH.is_file():
        return {}
    with _REFERENCE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def arm_type_free_tier_entry(arm_type: str) -> dict[str, Any] | None:
    key = (arm_type or "").strip().lower()
    if not key:
        return None
    entry = load_free_tier_reference().get("arm_types", {}).get(key)
    return dict(entry) if entry else None


def canonical_free_tier_entry(canonical_type: str) -> dict[str, Any] | None:
    key = (canonical_type or "").strip().lower()
    if not key:
        return None
    entry = load_free_tier_reference().get("canonical_types", {}).get(key)
    return dict(entry) if entry else None


def service_free_tier_entry(service_name: str) -> dict[str, Any] | None:
    name = (service_name or "").strip()
    if not name:
        return None
    services = load_free_tier_reference().get("services") or {}
    if name in services:
        return dict(services[name])
    low = name.lower()
    for svc, entry in services.items():
        if svc.lower() == low:
            return dict(entry)
    return official_free_tier_for_service(name)


def reference_metadata() -> dict[str, Any]:
    doc = load_free_tier_reference()
    return {
        "version": doc.get("version"),
        "updated_at": doc.get("updated_at"),
        "sources": list(doc.get("sources") or []),
        "account_programs": dict(doc.get("account_programs") or {}),
        "twelve_month_services": dict(doc.get("twelve_month_services") or {}),
        "arm_type_count": len(doc.get("arm_types") or {}),
        "canonical_type_count": len(doc.get("canonical_types") or {}),
        "service_override_count": len(doc.get("services") or {}),
        "official_free_services": official_free_services_catalog(),
    }


def arm_type_catalog_overrides() -> dict[str, dict[str, Any]]:
    return dict(load_free_tier_reference().get("arm_types") or {})


def canonical_type_catalog_overrides() -> dict[str, dict[str, Any]]:
    return dict(load_free_tier_reference().get("canonical_types") or {})


def service_catalog_overrides() -> dict[str, dict[str, Any]]:
    return dict(load_free_tier_reference().get("services") or {})


def merged_service_catalog_overrides() -> dict[str, dict[str, Any]]:
    """Doc reference overrides merged with official Azure free services page."""
    merged = {name: dict(override) for name, override in service_catalog_overrides().items()}
    for name, official in official_service_overrides().items():
        base = merged.get(name, {})
        free_tier = dict(official.get("free_tier") or {})
        if base.get("free_tier"):
            base_ft = dict(base["free_tier"])
            if base_ft.get("notes") and free_tier.get("notes"):
                free_tier["notes"] = f"{free_tier['notes']} {base_ft['notes']}"
            for key, val in base_ft.items():
                if key not in free_tier or key == "notes":
                    free_tier[key] = val
        merged[name] = {
            **base,
            **{k: v for k, v in official.items() if k != "free_tier"},
            "free_tier": free_tier,
        }
    return merged


@lru_cache(maxsize=1)
def load_official_free_services() -> dict[str, Any]:
    if not _OFFICIAL_PATH.is_file():
        return {}
    with _OFFICIAL_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _official_by_retail_name() -> dict[str, list[dict[str, Any]]]:
    doc = load_official_free_services()
    out: dict[str, list[dict[str, Any]]] = {}
    for bucket in ("always", "12_months_new_account"):
        duration = "always" if bucket == "always" else "12_months_new_account"
        for entry in doc.get(bucket) or []:
            row = dict(entry)
            row["duration"] = duration
            for retail in entry.get("retail_names") or []:
                out.setdefault(retail, []).append(row)
    return out


def official_free_tier_entries(service_name: str) -> list[dict[str, Any]]:
    name = (service_name or "").strip()
    if not name:
        return []
    by_retail = _official_by_retail_name()
    if name in by_retail:
        return [dict(e) for e in by_retail[name]]
    low = name.lower()
    for retail, entries in by_retail.items():
        if retail.lower() == low:
            return [dict(e) for e in entries]
    return []


def official_free_tier_for_service(service_name: str) -> dict[str, Any] | None:
    """Prefer always-free entry; fall back to 12-month new-account allowance."""
    entries = official_free_tier_entries(service_name)
    if not entries:
        return None
    always = next((e for e in entries if e.get("duration") == "always"), None)
    chosen = always or entries[0]
    return {
        "duration": chosen.get("duration"),
        "limit": chosen.get("limit"),
        "notes": chosen.get("notes"),
        "doc_ref": chosen.get("doc_url") or chosen.get("doc_ref"),
        "official_name": chosen.get("name"),
        "category": chosen.get("category"),
    }


def official_free_services_catalog() -> dict[str, Any]:
    doc = load_official_free_services()
    always = list(doc.get("always") or [])
    twelve = list(doc.get("12_months_new_account") or [])
    return {
        "version": doc.get("version"),
        "source_url": doc.get("source_url"),
        "always_count": len(always),
        "twelve_month_count": len(twelve),
        "total_count": len(always) + len(twelve),
        "always": always,
        "12_months_new_account": twelve,
    }


def official_service_overrides() -> dict[str, dict[str, Any]]:
    """Retail service name → catalog override from official Azure free services page."""
    overrides: dict[str, dict[str, Any]] = {}
    for retail, entries in _official_by_retail_name().items():
        always = next((e for e in entries if e.get("duration") == "always"), None)
        twelve = next((e for e in entries if e.get("duration") == "12_months_new_account"), None)
        primary = always or twelve
        if not primary:
            continue
        duration = primary.get("duration")
        free_tier: dict[str, Any] = {
            "duration": duration,
            "limit": primary.get("limit"),
            "doc_ref": primary.get("doc_url"),
            "official_name": primary.get("name"),
            "category": primary.get("category"),
        }
        if primary.get("notes"):
            free_tier["notes"] = primary["notes"]
        if always and twelve:
            free_tier["notes"] = (
                f"{always.get('limit', '')}; new accounts: {twelve.get('limit', '')}"
                + (f" — {always.get('notes')}" if always.get("notes") else "")
            ).strip()
        overrides[retail] = {
            "cost_type": "conditional",
            "pricing_model": (
                "free_tier_monthly"
                if duration == "always"
                else "free_tier_12_months"
            ),
            "free_tier": free_tier,
            "notes": f"Azure free services: {primary.get('name')} ({duration.replace('_', ' ')}).",
        }
    return overrides

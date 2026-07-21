"""AKS supported Kubernetes versions — fetched from Azure ARM (no hardcoded version lists).

API reference:
https://learn.microsoft.com/en-us/rest/api/aks/managed-clusters/list-kubernetes-versions
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()

# In-process cache: (subscription_id, location) -> (expires_at, payload)
_VERSION_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 3600


def normalize_k8s_minor(version: str | None) -> str:
    """Return major.minor from a full or partial Kubernetes version string."""
    text = (version or "").strip()
    if not text:
        return ""
    parts = text.split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return text


@dataclass
class AksKubernetesVersion:
    version: str
    is_default: bool = False
    is_preview: bool = False
    capabilities: dict[str, Any] = field(default_factory=dict)
    patch_versions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "isDefault": self.is_default,
            "isPreview": self.is_preview,
            "capabilities": self.capabilities,
            "patchVersions": self.patch_versions,
        }


def parse_kubernetes_versions_response(data: dict[str, Any] | None) -> list[AksKubernetesVersion]:
    """Parse ARM KubernetesVersionListResult into structured entries."""
    if not data:
        return []
    out: list[AksKubernetesVersion] = []
    for item in data.get("values") or []:
        if not isinstance(item, dict):
            continue
        version = (item.get("version") or "").strip()
        if not version:
            continue
        out.append(AksKubernetesVersion(
            version=version,
            is_default=bool(item.get("isDefault")),
            is_preview=bool(item.get("isPreview")),
            capabilities=dict(item.get("capabilities") or {}),
            patch_versions=dict(item.get("patchVersions") or {}),
        ))
    return out


def supported_minor_versions(
    versions: list[AksKubernetesVersion],
    *,
    include_preview: bool = True,
) -> set[str]:
    """Minor versions Azure lists as available for the region."""
    supported: set[str] = set()
    for entry in versions:
        if entry.is_preview and not include_preview:
            continue
        minor = normalize_k8s_minor(entry.version)
        if minor:
            supported.add(minor)
    return supported


def is_minor_version_supported(
    cluster_version: str | None,
    supported: set[str],
) -> bool | None:
    """Return True/False if supported set is known; None if we could not load versions."""
    if not supported:
        return None
    minor = normalize_k8s_minor(cluster_version)
    if not minor:
        return None
    return minor in supported


def _cache_get(key: tuple[str, str]) -> dict[str, Any] | None:
    row = _VERSION_CACHE.get(key)
    if not row:
        return None
    expires_at, payload = row
    if time.monotonic() > expires_at:
        _VERSION_CACHE.pop(key, None)
        return None
    return payload


def _cache_set(key: tuple[str, str], payload: dict[str, Any]) -> None:
    _VERSION_CACHE[key] = (time.monotonic() + _CACHE_TTL_SECONDS, payload)


def fetch_kubernetes_versions_for_location(
    subscription_id: str,
    location: str,
    *,
    db=None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Fetch supported Kubernetes versions for an Azure region from ARM.

    Returns:
        {
            "location": str,
            "subscription_id": str,
            "versions": [AksKubernetesVersion.to_dict(), ...],
            "supported_minors": [str, ...],
            "default_version": str | None,
            "source": "azure_arm",
        }
    """
    sub = (subscription_id or "").strip().lower()
    loc = (location or "").strip().lower()
    if not sub or not loc:
        return {
            "location": loc,
            "subscription_id": sub,
            "versions": [],
            "supported_minors": [],
            "default_version": None,
            "source": "azure_arm",
            "error": "subscription_id and location are required",
        }

    cache_key = (sub, loc)
    if not force_refresh:
        cached = _cache_get(cache_key)
        if cached is not None:
            return {**cached, "cached": True}

    try:
        from app.azure_resources import AzureResourcesClient
        raw = AzureResourcesClient(db=db).list_aks_kubernetes_versions(sub, loc)
    except Exception as exc:
        log.warning("aks_kubernetes_versions_fetch_failed", subscription_id=sub, location=loc, error=str(exc))
        return {
            "location": loc,
            "subscription_id": sub,
            "versions": [],
            "supported_minors": [],
            "default_version": None,
            "source": "azure_arm",
            "cached": False,
            "error": str(exc),
        }

    parsed = parse_kubernetes_versions_response(raw)
    default_version = next((v.version for v in parsed if v.is_default), None)
    payload = {
        "location": loc,
        "subscription_id": sub,
        "versions": [v.to_dict() for v in parsed],
        "supported_minors": sorted(supported_minor_versions(parsed)),
        "default_version": default_version,
        "source": "azure_arm",
        "cached": False,
    }
    _cache_set(cache_key, payload)
    return payload


def supported_minors_for_location(
    subscription_id: str,
    location: str,
    *,
    db=None,
) -> set[str]:
    """Return supported minor versions for a region; empty set if fetch failed."""
    result = fetch_kubernetes_versions_for_location(subscription_id, location, db=db)
    return set(result.get("supported_minors") or [])

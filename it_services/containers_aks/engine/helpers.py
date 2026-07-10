"""AKS analysis helpers — dynamic Kubernetes version support from Azure ARM."""
from __future__ import annotations

from typing import Any

from app.aks_versions import fetch_kubernetes_versions_for_location, supported_minors_for_location


def aks_supported_minors(
    engine: Any,
    subscription_id: str,
    location: str,
) -> set[str]:
    """Cached per-(subscription, location) supported K8s minor versions from Azure."""
    cache: dict[tuple[str, str], set[str]] = getattr(engine, "_aks_k8s_versions_cache", {})
    key = (subscription_id.strip().lower(), (location or "").strip().lower())
    if key in cache:
        return cache[key]
    minors = supported_minors_for_location(subscription_id, location)
    cache[key] = minors
    engine._aks_k8s_versions_cache = cache
    return minors


def aks_version_catalog(
    engine: Any,
    subscription_id: str,
    location: str,
) -> dict[str, Any]:
    """Full Kubernetes version metadata for a region (for evidence / API)."""
    catalog_cache: dict[tuple[str, str], dict] = getattr(engine, "_aks_k8s_catalog_cache", {})
    key = (subscription_id.strip().lower(), (location or "").strip().lower())
    if key in catalog_cache:
        return catalog_cache[key]
    payload = fetch_kubernetes_versions_for_location(subscription_id, location)
    catalog_cache[key] = payload
    engine._aks_k8s_catalog_cache = catalog_cache
    return payload

"""Azure-backed resource health classification for dashboard and summaries."""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable, TypeVar

import structlog
from sqlalchemy.orm import Session

from app.focus_mapping import normalize_arm_id
from app.models import ResourceSnapshot
from app.perf_cache import cached_azure_health_statuses
from app.vm_utils import is_scale_set_instance

log = structlog.get_logger(__name__)

_T = TypeVar("_T")

HEALTH_CATEGORIES = ("healthy", "degraded", "unavailable", "unknown")

_UNAVAILABLE_PROV_STATES = frozenset({"failed", "canceled", "cancelled"})
_DEGRADED_PROV_STATES = frozenset({
    "creating", "updating", "deleting", "rollingback", "restoring", "migrating",
})
_DEGRADED_POWER_STATES = frozenset({
    "starting", "stopping", "deallocating", "unknown",
})
_DEGRADED_APP_STATES = frozenset({"stopped", "stopping", "disabled"})

_AZURE_AVAILABILITY_MAP = {
    "available": "healthy",
    "degraded": "degraded",
    "unavailable": "unavailable",
    "unknown": "unknown",
}


def map_azure_availability_state(state: str | None) -> str:
    """Map Azure Resource Health availabilityState to a dashboard category."""
    key = (state or "").strip().lower()
    return _AZURE_AVAILABILITY_MAP.get(key, "unknown")


def _normalize_power_state(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    return text


def classify_resource_from_snapshot(
    *,
    state: str | None,
    properties: dict[str, Any] | None,
    resource_type: str | None = None,
) -> str:
    """Derive health from synced ARM state and properties when Azure RH is absent."""
    props = properties or {}
    prov = str(props.get("provisioningState") or "").strip().lower()
    if prov in _UNAVAILABLE_PROV_STATES:
        return "unavailable"
    if prov in _DEGRADED_PROV_STATES:
        return "degraded"

    rtype = (resource_type or "").strip().lower()
    if rtype == "database/redis" and prov == "failed":
        return "unavailable"

    app_state = str(props.get("state") or state or "").strip().lower()
    if app_state in _DEGRADED_APP_STATES:
        return "degraded"

    power = _normalize_power_state(props.get("powerState") or state)
    if power in _DEGRADED_POWER_STATES:
        return "degraded"

    disk_state = str(props.get("diskState") or "").strip().lower()
    if disk_state in {"activesastransactionfailed", "activesasfailed", "reserved"}:
        return "degraded"

    if prov in ("", "succeeded"):
        return "healthy"
    if prov:
        return "unknown"
    return "healthy"


def _worst_category(current: str, candidate: str) -> str:
    order = {"healthy": 0, "unknown": 1, "degraded": 2, "unavailable": 3}
    return candidate if order.get(candidate, 0) > order.get(current, 0) else current


def classify_resource_health(
    *,
    state: str | None,
    properties: dict[str, Any] | None,
    resource_type: str | None,
    azure_availability_state: str | None = None,
) -> str:
    """Pick the strongest available health signal for one resource."""
    if azure_availability_state:
        mapped = map_azure_availability_state(azure_availability_state)
        if mapped != "unknown":
            return mapped
    derived = classify_resource_from_snapshot(
        state=state,
        properties=properties,
        resource_type=resource_type,
    )
    if azure_availability_state:
        return _worst_category(derived, map_azure_availability_state(azure_availability_state))
    return derived


def _inventory_rows(db: Session, subscription_id: str) -> list[tuple[str, str, str, dict[str, Any]]]:
    sub = (subscription_id or "").strip().lower()
    rows = (
        db.query(
            ResourceSnapshot.resource_id,
            ResourceSnapshot.resource_type,
            ResourceSnapshot.state,
            ResourceSnapshot.properties_json,
        )
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
            ResourceSnapshot.is_cost_export_only.is_(False),
        )
        .all()
    )
    out: list[tuple[str, str, str, dict[str, Any]]] = []
    for rid, rtype, state, props_json in rows:
        try:
            props = json.loads(props_json or "{}")
        except Exception:
            props = {}
        if props.get("_cost_export_only"):
            continue
        if rtype == "compute/vm" and is_scale_set_instance({"id": rid, "properties": props}):
            continue
        norm = normalize_arm_id(rid)
        if not norm:
            continue
        out.append((norm, rtype or "", state or "", props))
    return out


def _azure_health_enabled() -> bool:
    """When false, dashboard health uses synced inventory only (fast local dev)."""
    val = os.getenv("DASHBOARD_AZURE_HEALTH", "1").strip().lower()
    return val not in {"0", "false", "no", "off"}


def _azure_health_timeout_sec() -> float:
    try:
        return max(1.0, float(os.getenv("DASHBOARD_AZURE_HEALTH_TIMEOUT_SEC", "8")))
    except (TypeError, ValueError):
        return 8.0


def _run_timed_loader(
    loader: Callable[[], _T],
    *,
    timeout_sec: float,
    label: str,
    fallback: _T,
) -> _T:
    """Run a blocking loader with a hard timeout; never wait on slow Azure calls."""
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rh")
    future = pool.submit(loader)
    try:
        return future.result(timeout=timeout_sec)
    except FuturesTimeoutError:
        log.warning(f"{label}.timeout", timeout_sec=timeout_sec)
        pool.shutdown(wait=False, cancel_futures=True)
        return fallback
    except Exception as exc:
        log.warning(f"{label}.failed", error=str(exc)[:200])
        pool.shutdown(wait=True, cancel_futures=True)
        return fallback
    else:
        pool.shutdown(wait=True, cancel_futures=True)


def _load_azure_availability_map(db: Session, subscription_id: str) -> dict[str, str]:
    sub = (subscription_id or "").strip().lower()
    from app.auth import cached_arm_token_available

    if not _azure_health_enabled():
        return {}

    if not cached_arm_token_available(db):
        return {}

    def fetch_statuses() -> dict[str, str]:
        from app.azure_maintenance import AzureMaintenanceClient

        client = AzureMaintenanceClient(db=db)
        statuses = client.list_availability_statuses(sub)
        mapped: dict[str, str] = {}
        for item in statuses:
            rid = normalize_arm_id(item.get("id") or "")
            state = ((item.get("properties") or {}).get("availabilityState") or "").strip()
            if rid and state:
                mapped[rid] = state
        return mapped

    def loader() -> dict[str, str]:
        return _run_timed_loader(
            fetch_statuses,
            timeout_sec=_azure_health_timeout_sec(),
            label="resource_health.azure_fetch",
            fallback={},
        )

    try:
        return cached_azure_health_statuses(sub, loader)
    except Exception as exc:
        log.warning("resource_health.azure_cache_failed", sub=sub, error=str(exc)[:200])
        return {}


def aggregate_health_counts(
    resources: list[tuple[str, str, str, dict[str, Any]]],
    azure_availability: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Count resources by health category."""
    counts = {key: 0 for key in HEALTH_CATEGORIES}
    azure_hits = 0
    azure_map = azure_availability or {}

    for rid, rtype, state, props in resources:
        azure_state = azure_map.get(rid)
        if azure_state:
            azure_hits += 1
        category = classify_resource_health(
            state=state,
            properties=props,
            resource_type=rtype,
            azure_availability_state=azure_state,
        )
        counts[category] = counts.get(category, 0) + 1

    total = sum(counts.values())
    if azure_hits:
        source = "mixed" if azure_hits < total else "azure_resource_health"
    else:
        source = "inventory_properties"

    return {
        **counts,
        "total": total,
        "azure_status_count": azure_hits,
        "source": source,
    }


def get_subscription_health_counts(db: Session, subscription_id: str) -> dict[str, Any]:
    """Subscription health breakdown using cached Azure RH + inventory fallback."""
    resources = _inventory_rows(db, subscription_id)
    azure_map = _load_azure_availability_map(db, subscription_id)
    return aggregate_health_counts(resources, azure_map)

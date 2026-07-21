"""Extract and enrich Azure SKU / item details during inventory sync."""

from __future__ import annotations

import structlog
from typing import Any

from app.resources import sku_text
from app.vm_utils import vmss_display_sku

log = structlog.get_logger(__name__)


def _first_pe_connection(props: dict[str, Any]) -> dict[str, Any]:
    for key in ("privateLinkServiceConnections", "manualPrivateLinkServiceConnections"):
        conns = props.get(key) or []
        if isinstance(conns, list) and conns:
            first = conns[0]
            return first if isinstance(first, dict) else {}
    return {}


def format_private_endpoint_connection_label(props: dict[str, Any] | None) -> str | None:
    """Human-readable target + connection state (private endpoints have no ARM sku)."""
    if not props:
        return None
    conn = _first_pe_connection(props)
    inner = conn.get("properties") if isinstance(conn.get("properties"), dict) else conn
    group_id = inner.get("groupId")
    target_id = inner.get("privateLinkServiceId") or ""
    target_name = str(target_id).rsplit("/", 1)[-1] if target_id else None
    label = str(group_id) if group_id not in (None, "") else target_name
    state_obj = inner.get("privateLinkServiceConnectionState") or {}
    state = (
        state_obj.get("status")
        if isinstance(state_obj, dict)
        else inner.get("provisioningState")
    )
    state = str(state) if state not in (None, "") else None
    if label and state:
        return f"{label} · {state}"
    return label or state


def format_private_link_service_label(props: dict[str, Any] | None) -> str | None:
    """Human-readable connection count + visibility (private link services have no ARM sku)."""
    if not props:
        return None
    conns = props.get("privateEndpointConnections") or []
    count = len(conns) if isinstance(conns, list) else 0
    conn_part = (
        f"{count} connection{'s' if count != 1 else ''}"
        if count
        else "No connections"
    )
    visibility = props.get("visibility")
    visibility = str(visibility) if visibility not in (None, "") else None
    if visibility:
        return f"{conn_part} · {visibility}"
    return conn_part


def format_private_dns_zone_label(props: dict[str, Any] | None) -> str | None:
    """Human-readable record set count + zone type (private DNS zones have no ARM sku)."""
    if not props:
        return None
    count = props.get("numberOfRecordSets")
    record_part: str | None = None
    if count is not None:
        try:
            n = int(count)
            record_part = f"{n} record set{'s' if n != 1 else ''}"
        except (TypeError, ValueError):
            record_part = None
    zone_type = props.get("zoneType")
    zone_type = str(zone_type) if zone_type not in (None, "") else None
    if record_part and zone_type:
        return f"{record_part} · {zone_type}"
    return record_part or zone_type


def format_vnet_address_space(props: dict[str, Any] | None) -> str | None:
    """Human-readable CIDR list for virtual network inventory (VNets have no ARM sku)."""
    if not props:
        return None
    address_space = props.get("addressSpace") or {}
    prefixes = address_space.get("addressPrefixes") or []
    if not prefixes:
        return None
    shown = ", ".join(str(p) for p in prefixes[:2])
    if len(prefixes) > 2:
        shown += f" (+{len(prefixes) - 2})"
    return shown


def _app_service_kind_label(kind: Any) -> str | None:
    text = str(kind or "").lower()
    if "functionapp" in text:
        return "Function"
    if "workflowapp" in text:
        return "Logic App"
    if "static" in text:
        return "Static"
    if "linux" in text:
        return "Linux"
    if "app" in text:
        return "Web"
    return None


def format_app_service_plan_sku_short(arm_resource: dict[str, Any]) -> str | None:
    """Compact plan size/tier for web app rows (e.g. P1v3)."""
    arm_sku = _arm_sku_dict(arm_resource)
    name = arm_sku.get("name") or arm_sku.get("size") or arm_sku.get("tier")
    if name not in (None, ""):
        return str(name)
    return sku_text(arm_sku) or None


def format_app_service_plan_label(arm_resource: dict[str, Any]) -> str | None:
    """Full App Service plan SKU label for plan inventory rows."""
    arm_sku = _arm_sku_dict(arm_resource)
    if not arm_sku:
        return None
    name = arm_sku.get("name") or arm_sku.get("size")
    tier = arm_sku.get("tier")
    capacity = arm_sku.get("capacity")
    parts: list[str] = []
    if name not in (None, ""):
        parts.append(str(name))
    if tier not in (None, "") and str(tier) != str(name):
        parts.append(str(tier))
    if capacity is not None:
        try:
            n = int(capacity)
            parts.append(f"{n} worker{'s' if n != 1 else ''}")
        except (TypeError, ValueError):
            pass
    if parts:
        return " · ".join(parts)
    return sku_text(arm_sku) or None


def format_app_service_webapp_label(
    props: dict[str, Any] | None,
    *,
    plan_sku: str | None = None,
) -> str | None:
    """Plan SKU + plan name (+ workload kind) for App Service web apps."""
    if not props:
        return None
    plan_id = props.get("serverFarmId") or ""
    plan_name = plan_id.rsplit("/", 1)[-1] if plan_id else ""
    plan_part: str | None = None
    if plan_sku and plan_name:
        plan_part = f"{plan_sku} · {plan_name}"
    elif plan_sku:
        plan_part = plan_sku
    elif plan_name:
        plan_part = plan_name
    kind_label = _app_service_kind_label(props.get("kind"))
    if kind_label and plan_part:
        return f"{kind_label} · {plan_part}"
    return kind_label or plan_part


def build_app_service_plan_sku_index(plans: list[dict[str, Any]]) -> dict[str, str]:
    """Map serverFarm ARM id → compact SKU label for web app enrichment."""
    index: dict[str, str] = {}
    for plan in plans:
        plan_id = (plan.get("id") or "").strip().lower()
        if not plan_id:
            continue
        label = format_app_service_plan_sku_short(plan)
        if label:
            index[plan_id] = label
    return index


def _capabilities_map(catalog_entry: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for cap in catalog_entry.get("capabilities") or []:
        name = (cap.get("name") or "").strip()
        value = cap.get("value")
        if name and value is not None:
            out[name] = str(value)
    return out


def _compact_vm_catalog(catalog_entry: dict[str, Any]) -> dict[str, Any]:
    caps = _capabilities_map(catalog_entry)
    compact: dict[str, Any] = {
        "name": catalog_entry.get("name"),
        "resource_type": catalog_entry.get("resourceType"),
        "tier": catalog_entry.get("tier"),
        "size": catalog_entry.get("size"),
        "family": catalog_entry.get("family"),
        "capabilities": caps,
    }
    if caps.get("vCPUs"):
        try:
            compact["vcpus"] = int(float(caps["vCPUs"]))
        except ValueError:
            pass
    if caps.get("MemoryGB"):
        try:
            compact["memory_gb"] = float(caps["MemoryGB"])
        except ValueError:
            pass
    if caps.get("MaxDataDiskCount"):
        try:
            compact["max_data_disks"] = int(float(caps["MaxDataDiskCount"]))
        except ValueError:
            pass
    return {k: v for k, v in compact.items() if v not in (None, "", {})}


class VmSkuCatalogCache:
    """Lazy per-location VM SKU catalog from the Resource SKUs API."""

    def __init__(self, client: Any, subscription_id: str):
        self._client = client
        self._subscription_id = subscription_id
        self._by_location: dict[str, dict[str, dict[str, Any]]] = {}

    def lookup(self, location: str | None, vm_size: str | None) -> dict[str, Any] | None:
        loc = (location or "").strip().replace(" ", "").lower()
        size = (vm_size or "").strip()
        if not loc or not size:
            return None
        if loc not in self._by_location:
            self._load(loc)
        return self._by_location.get(loc, {}).get(size.lower())

    def _load(self, location: str) -> None:
        try:
            rows = self._client.list_vm_skus(self._subscription_id, location)
            index: dict[str, dict[str, Any]] = {}
            for row in rows:
                name = (row.get("name") or "").strip().lower()
                if name:
                    index[name] = row
            self._by_location[location] = index
            log.info("vm_sku_catalog.loaded", location=location, count=len(index))
        except Exception as exc:
            log.warning("vm_sku_catalog.failed", location=location, error=str(exc))
            self._by_location[location] = {}


def _arm_sku_dict(arm_resource: dict[str, Any]) -> dict[str, Any]:
    """ARM sku on the resource or nested under properties (App Gateway, Firewall, Key Vault, etc.)."""
    sku = arm_resource.get("sku")
    if not isinstance(sku, dict) or not sku:
        props_sku = (arm_resource.get("properties") or {}).get("sku")
        if isinstance(props_sku, dict):
            sku = props_sku
    if isinstance(sku, dict):
        return {k: v for k, v in sku.items() if v is not None}
    return {}


def extract_arm_sku_payload(arm_resource: dict[str, Any], canonical_type: str) -> dict[str, Any]:
    """Build a normalized SKU payload from a full ARM resource."""
    canonical = (canonical_type or "").strip().lower()
    props = arm_resource.get("properties") or {}
    arm_sku = _arm_sku_dict(arm_resource)
    payload: dict[str, Any] = {"canonical_type": canonical}

    if arm_sku:
        payload["arm"] = arm_sku

    if canonical == "compute/vm":
        vm_size = (props.get("hardwareProfile") or {}).get("vmSize")
        if vm_size:
            payload["name"] = vm_size
            payload["vm_size"] = vm_size
    elif canonical == "compute/vmss":
        vm_size = (
            (props.get("virtualMachineProfile") or {})
            .get("hardwareProfile", {})
            .get("vmSize")
        )
        if vm_size:
            payload["vm_size"] = vm_size
            payload["name"] = vm_size
        if arm_sku.get("capacity") is not None:
            payload["capacity"] = arm_sku["capacity"]
    elif canonical == "containers/aks":
        tier = arm_sku.get("tier") or arm_sku.get("name")
        if tier:
            payload["name"] = tier
            payload["tier"] = tier
        pools = props.get("agentPoolProfiles") or []
        if pools:
            payload["node_pools"] = [
                {
                    "name": p.get("name"),
                    "vm_size": p.get("vmSize"),
                    "count": p.get("count"),
                    "mode": p.get("mode"),
                    "os_type": p.get("osType"),
                    "sku": p.get("sku"),
                }
                for p in pools
            ]
    elif canonical == "appservice/webapp":
        plan_id = props.get("serverFarmId") or ""
        if plan_id:
            payload["app_service_plan_id"] = plan_id
            payload["plan_name"] = plan_id.rsplit("/", 1)[-1]
        kind = props.get("kind")
        if kind not in (None, ""):
            payload["kind"] = kind
        plan_sku = arm_resource.get("_plan_sku")
        if plan_sku not in (None, ""):
            payload["plan_sku"] = plan_sku
    elif canonical == "appservice/plan":
        plan_label = format_app_service_plan_label(arm_resource)
        if plan_label:
            payload["name"] = plan_label
        for key in ("tier", "size", "family"):
            if arm_sku.get(key) is not None:
                payload[key] = arm_sku[key]
    elif canonical == "database/redis":
        for key in ("name", "family", "capacity"):
            if arm_sku.get(key) is not None:
                payload[key] = arm_sku[key]
    elif canonical == "network/vnet":
        prefixes_label = format_vnet_address_space(props)
        if prefixes_label:
            payload["address_prefixes"] = list(props.get("addressSpace", {}).get("addressPrefixes") or [])
            payload["name"] = prefixes_label
        subnets = props.get("subnets") or []
        if subnets:
            payload["subnet_count"] = len(subnets)
    elif canonical == "network/privateendpoint":
        connection_label = format_private_endpoint_connection_label(props)
        if connection_label:
            payload["name"] = connection_label
        conn = _first_pe_connection(props)
        inner = conn.get("properties") if isinstance(conn.get("properties"), dict) else conn
        if inner.get("groupId"):
            payload["group_id"] = inner["groupId"]
        if inner.get("privateLinkServiceId"):
            payload["target_resource_id"] = inner["privateLinkServiceId"]
        state_obj = inner.get("privateLinkServiceConnectionState") or {}
        if isinstance(state_obj, dict) and state_obj.get("status"):
            payload["connection_state"] = state_obj["status"]
    elif canonical == "network/privatelinkservice":
        summary_label = format_private_link_service_label(props)
        if summary_label:
            payload["name"] = summary_label
        conns = props.get("privateEndpointConnections") or []
        if isinstance(conns, list):
            payload["connection_count"] = len(conns)
        visibility = props.get("visibility")
        if visibility not in (None, ""):
            payload["visibility"] = visibility
    elif canonical == "network/privatedns":
        zone_label = format_private_dns_zone_label(props)
        if zone_label:
            payload["name"] = zone_label
        count = props.get("numberOfRecordSets")
        if count is not None:
            try:
                payload["record_set_count"] = int(count)
            except (TypeError, ValueError):
                pass
        zone_type = props.get("zoneType")
        if zone_type not in (None, ""):
            payload["zone_type"] = zone_type
    else:
        for key in ("name", "tier", "size", "family", "capacity", "model"):
            if arm_sku.get(key) is not None:
                payload[key] = arm_sku[key]

    if not payload.get("name"):
        label = sku_text(arm_sku)
        if label:
            payload["name"] = label

    return {k: v for k, v in payload.items() if v not in (None, "", [], {})}


def enrich_sku_payload(
    arm_resource: dict[str, Any],
    canonical_type: str,
    payload: dict[str, Any],
    *,
    catalog_cache: VmSkuCatalogCache | None = None,
) -> dict[str, Any]:
    """Attach Azure catalog details when available (VM families today)."""
    canonical = (canonical_type or "").strip().lower()
    enriched = dict(payload)
    location = arm_resource.get("location")

    if canonical in {"compute/vm", "compute/vmss"}:
        vm_size = enriched.get("vm_size") or enriched.get("name")
        if vm_size and catalog_cache:
            catalog_entry = catalog_cache.lookup(location, str(vm_size))
            if catalog_entry:
                enriched["catalog"] = _compact_vm_catalog(catalog_entry)

    if canonical == "containers/aks" and enriched.get("node_pools") and catalog_cache:
        pool_catalogs: list[dict[str, Any]] = []
        for pool in enriched["node_pools"]:
            vm_size = pool.get("vm_size")
            entry = catalog_cache.lookup(location, vm_size) if vm_size else None
            pool_catalogs.append({
                "name": pool.get("name"),
                "vm_size": vm_size,
                "catalog": _compact_vm_catalog(entry) if entry else None,
            })
        enriched["node_pool_catalog"] = [p for p in pool_catalogs if p.get("catalog")]

    return enriched


def sku_display_label(
    arm_resource: dict[str, Any],
    canonical_type: str,
    payload: dict[str, Any],
    *,
    override: str | None = None,
) -> str | None:
    """Human-readable SKU string for resource_snapshots.sku."""
    if override:
        return override
    canonical = (canonical_type or "").strip().lower()
    if canonical == "compute/vmss":
        return vmss_display_sku(arm_resource)
    if canonical == "appservice/webapp":
        return format_app_service_webapp_label(
            arm_resource.get("properties") or {},
            plan_sku=payload.get("plan_sku"),
        )
    if canonical == "appservice/plan" and payload.get("name"):
        return str(payload["name"])
    if payload.get("name"):
        parts = [str(payload["name"])]
        if payload.get("capacity") is not None:
            parts.append(f"{payload['capacity']} instances")
        return " ".join(parts)
    return sku_text(_arm_sku_dict(arm_resource)) or None


def build_sync_sku_fields(
    arm_resource: dict[str, Any],
    canonical_type: str,
    *,
    catalog_cache: VmSkuCatalogCache | None = None,
    sku_label_override: str | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Return (display sku, sku_json) for DB persistence."""
    payload = extract_arm_sku_payload(arm_resource, canonical_type)
    if not payload:
        return sku_label_override, {}
    enriched = enrich_sku_payload(
        arm_resource,
        canonical_type,
        payload,
        catalog_cache=catalog_cache,
    )
    label = sku_display_label(
        arm_resource,
        canonical_type,
        enriched,
        override=sku_label_override,
    )
    return label, enriched

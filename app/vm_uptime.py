"""VM and VMSS uptime from Azure timeCreated / instanceView."""

from __future__ import annotations

import os
from concurrent import futures
from datetime import datetime, timezone
from typing import Any

import structlog

from app.focus_mapping import normalize_arm_id
from app.http_client import arm_patient_active
from app.resource_type_map import extract_rg_from_arm, internal_resource_type

log = structlog.get_logger(__name__)

_VMSS_INSTANCE_VIEW_WORKERS = max(1, int(os.getenv("ARM_VMSS_INSTANCE_VIEW_WORKERS", "4")))


def parse_azure_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def uptime_hours_since(created: datetime, *, now: datetime | None = None) -> float:
    ref = now or datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    delta = ref - created
    return max(0.0, delta.total_seconds() / 3600.0)


def time_created_from_instance_view(instance_view: dict[str, Any] | None) -> datetime | None:
    """Derive creation time from instanceView (timeCreated or provisioning status time)."""
    if not instance_view:
        return None
    direct = parse_azure_datetime(instance_view.get("timeCreated"))
    if direct:
        return direct
    statuses = instance_view.get("statuses") or []
    provision_times: list[datetime] = []
    fallback_times: list[datetime] = []
    for status in statuses:
        if not isinstance(status, dict):
            continue
        when = parse_azure_datetime(status.get("time"))
        if not when:
            continue
        code = str(status.get("code") or "").lower()
        if "provisioningstate/succeeded" in code:
            provision_times.append(when)
        else:
            fallback_times.append(when)
    if provision_times:
        return min(provision_times)
    if fallback_times:
        return min(fallback_times)
    return None


def time_created_from_vm(vm: dict[str, Any]) -> datetime | None:
    """Time created for a standalone VM (properties.timeCreated or instanceView)."""
    props = vm.get("properties") or {}
    created = parse_azure_datetime(props.get("timeCreated") or props.get("TimeCreated"))
    if created:
        return created
    return time_created_from_instance_view(props.get("instanceView"))


def vm_is_running(vm: dict[str, Any], *, power_state: str = "") -> bool:
    canonical = vm.get("_canonical_type") or internal_resource_type(vm.get("id") or "")
    if canonical == "compute/vmss":
        from app.vm_utils import _vmss_capacity

        props = vm.get("properties") or {}
        power = str(props.get("powerState") or power_state or "").strip().lower()
        if power:
            return power == "running"
        capacity = _vmss_capacity(vm, props)
        if capacity is not None:
            return capacity > 0
        prov = str(props.get("provisioningState") or "").lower()
        return prov in ("", "succeeded")
    norm = (power_state or "").replace("PowerState/", "").strip().lower()
    if norm:
        return norm == "running"
    props = vm.get("properties") or {}
    iv = props.get("instanceView") or {}
    for status in iv.get("statuses") or []:
        code = str((status or {}).get("code") or "")
        if code.lower().startswith("powerstate/"):
            return code.split("/", 1)[-1].lower() == "running"
    return False


def vm_uptime_facts(
    vm: dict[str, Any],
    *,
    power_state: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return time_created + uptime_hours for a VM or VMSS resource envelope."""
    canonical = vm.get("_canonical_type") or internal_resource_type(vm.get("id") or "")
    props = vm.get("properties") or {}
    created: datetime | None = None
    source = "vm"

    if canonical == "compute/vmss":
        created = parse_azure_datetime(
            props.get("oldest_instance_time_created")
            or props.get("timeCreated")
        )
        source = "vmss_instance"
    else:
        created = time_created_from_vm(vm)

    if not created:
        return {}

    hours = uptime_hours_since(created, now=now)
    return {
        "time_created": created.isoformat(),
        "uptime_hours": round(hours, 1),
        "uptime_source": source,
        "is_running": vm_is_running(vm, power_state=power_state),
    }


def _instance_id_from_vmss_vm(instance: dict[str, Any]) -> str:
    props = instance.get("properties") or {}
    for key in ("instanceId", "instance_id"):
        val = instance.get(key) or props.get(key)
        if val not in (None, ""):
            return str(val)
    name = instance.get("name") or ""
    if name:
        return name.rsplit("_", 1)[-1] if "_" in name else name
    return ""


def fetch_vmss_instance_uptime(
    client: Any,
    subscription_id: str,
    vmss: dict[str, Any],
) -> dict[str, Any]:
    """Fetch instanceView times for VMSS instances; return oldest/newest creation markers."""
    rid = normalize_arm_id(vmss.get("id") or "")
    rg = extract_rg_from_arm(rid)
    name = (vmss.get("name") or "").strip()
    if not rg or not name:
        return {}

    try:
        instances = client.list_vm_scale_set_vms(subscription_id, rg, name)
    except Exception as exc:
        log.warning("vmss.instances.list_failed", vmss=name, error=str(exc))
        return {}

    if not instances:
        return {"vmss_instance_count": 0}

    def _created_for_instance(instance: dict[str, Any]) -> datetime | None:
        instance_id = _instance_id_from_vmss_vm(instance)
        if not instance_id:
            return None
        try:
            iv = client.get_vm_scale_set_vm_instance_view(
                subscription_id, rg, name, instance_id,
            )
        except Exception as exc:
            log.debug(
                "vmss.instance_view.failed",
                vmss=name,
                instance_id=instance_id,
                error=str(exc),
            )
            return None
        props = instance.get("properties") or {}
        return (
            parse_azure_datetime(props.get("timeCreated"))
            or time_created_from_instance_view(iv)
        )

    workers = 1 if arm_patient_active() else min(_VMSS_INSTANCE_VIEW_WORKERS, len(instances))
    created_times: list[datetime] = []
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for created in pool.map(_created_for_instance, instances):
            if created:
                created_times.append(created)

    if not created_times:
        return {"vmss_instance_count": len(instances)}

    oldest = min(created_times)
    newest = max(created_times)
    return {
        "oldest_instance_time_created": oldest.isoformat(),
        "newest_instance_time_created": newest.isoformat(),
        "vmss_instance_count": len(instances),
        "vmss_instances_with_time": len(created_times),
    }


def enrich_vmss_with_instance_uptime(
    client: Any,
    subscription_id: str,
    vmss: dict[str, Any],
) -> dict[str, Any]:
    """Attach oldest instance timeCreated into VMSS properties for sync/analysis."""
    out = dict(vmss)
    props = dict(out.get("properties") or {})
    uptime_props = fetch_vmss_instance_uptime(client, subscription_id, vmss)
    if uptime_props:
        props.update(uptime_props)
        out["properties"] = props
    return out


def enrich_vmss_list_with_instance_uptime(
    client: Any,
    subscription_id: str,
    scale_sets: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    items = list(scale_sets or [])
    if not items:
        return []
    return [
        enrich_vmss_with_instance_uptime(client, subscription_id, item)
        for item in items
    ]

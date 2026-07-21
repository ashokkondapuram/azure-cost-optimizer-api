"""Azure Planned Maintenance integration.

Fetches scheduled maintenance events for all resource types via the ARM
Maintenance + Resource Health APIs and enriches resource analysis with
maintenance-awareness.

Supported resource types:
  - Virtual Machines (Microsoft.Compute/virtualMachines)
  - VMSS / AKS node-pool VMSS (Microsoft.Compute/virtualMachineScaleSets)
  - AKS Managed Clusters (Microsoft.ContainerService/managedClusters)
  - Any resource via Resource Health "Planned Maintenance" health events

API references:
  https://learn.microsoft.com/en-us/rest/api/maintenance/
  https://learn.microsoft.com/en-us/rest/api/resourcehealth/
"""
from __future__ import annotations

import concurrent.futures
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from app.auth import auth_headers
from app.http_client import _get, get_all_pages, BASE, AzureAPIError

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# API versions
# ---------------------------------------------------------------------------
_MAINTENANCE_API_VERSION = "2023-04-01"
_RESOURCE_HEALTH_API_VERSION = "2022-10-01"
_AKS_MAINTENANCE_API_VERSION = "2024-09-01"  # supports maintenanceConfigurations
_COMPUTE_API_VERSION = "2024-03-01"
_ACTIVITY_LOG_API_VERSION = "2015-04-01"
_ACTIVITY_LOG_LOOKBACK_DAYS = int(os.getenv("MAINTENANCE_ACTIVITY_LOG_DAYS", "14"))

_MAINTENANCE_OPERATION_KEYWORDS = (
    "maintenance",
    "livemigration",
    "redeploy",
    "upgrade",
    "reimage",
    "evict",
    "rollingupgrade",
    "osupgrade",
    "manualupgrade",
)


def _rg_from_id(resource_id: str) -> str:
    parts = resource_id.split("/")
    try:
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""


def _resource_name_from_id(resource_id: str) -> str:
    return (resource_id or "").rstrip("/").split("/")[-1]


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _is_planned_maintenance_event(event: dict[str, Any]) -> bool:
    props = event.get("properties") or {}
    return props.get("eventType") == "PlannedMaintenance"


def _health_event_row(event: dict[str, Any]) -> dict[str, Any]:
    props = event.get("properties") or {}
    impacted = props.get("impactedResource") or ""
    return {
        "id": event.get("name") or props.get("trackingId") or "",
        "source": "health_event",
        "resource_type": "Service health",
        "resource_name": _resource_name_from_id(impacted) or props.get("title") or "Subscription event",
        "resource_id": impacted or None,
        "resource_group": _rg_from_id(impacted),
        "title": props.get("title") or "Planned maintenance",
        "status": props.get("status") or props.get("eventSubType"),
        "window_start": props.get("impactStartTime"),
        "window_end": props.get("impactMitigationTime"),
        "detail": props.get("summary"),
    }


def _vm_maintenance_row(vm: dict[str, Any], status: dict[str, Any]) -> dict[str, Any] | None:
    start = status.get("maintenance_window_start") or status.get("pre_maintenance_window_start")
    end = status.get("maintenance_window_end") or status.get("pre_maintenance_window_end")
    if not start and not end and not status.get("upcoming"):
        return None
    rid = vm.get("id") or status.get("resource_id") or ""
    name = vm.get("name") or status.get("resource_name") or ""
    return {
        "id": f"vm:{rid}",
        "source": "vm",
        "resource_type": "Virtual machine",
        "resource_name": name,
        "resource_id": rid,
        "resource_group": _rg_from_id(rid),
        "location": vm.get("location"),
        "title": "Platform maintenance window",
        "status": status.get("last_operation_result") or ("upcoming" if status.get("upcoming") else "scheduled"),
        "window_start": start,
        "window_end": end,
        "detail": status.get("last_operation_message"),
    }


def _vmss_maintenance_rows(
    subscription_id: str,
    vmss: dict[str, Any],
    mc: "AzureMaintenanceClient",
) -> list[dict[str, Any]]:
    rid = vmss.get("id") or ""
    rg = _rg_from_id(rid)
    name = vmss.get("name") or ""
    if not rg or not name:
        return []

    instances = mc.list_vmss_instance_maintenance(subscription_id, rg, name)
    rows: list[dict[str, Any]] = []
    pending = sum(1 for inst in instances if inst.get("pending_model_update"))

    if pending > 0:
        rows.append({
            "id": f"vmss:{rid}",
            "source": "vmss",
            "resource_type": "VM scale set",
            "resource_name": name,
            "resource_id": rid,
            "resource_group": rg,
            "location": vmss.get("location"),
            "title": "Pending model updates",
            "status": f"{pending} instance{'s' if pending != 1 else ''} pending",
            "window_start": None,
            "window_end": None,
            "detail": f"{pending} of {len(instances)} instances are not on the latest model.",
            "pending_model_updates": pending,
            "instance_count": len(instances),
        })

    for inst in instances:
        start = inst.get("maintenance_window_start")
        end = inst.get("maintenance_window_end")
        if not start and not end and not inst.get("pending_model_update"):
            continue
        rows.append({
            "id": f"vmss-instance:{rid}:{inst.get('instance_id')}",
            "source": "vmss_instance",
            "resource_type": "VMSS instance",
            "resource_name": f"{name}/{inst.get('name') or inst.get('instance_id')}",
            "resource_id": rid,
            "resource_group": rg,
            "location": vmss.get("location"),
            "title": "Instance maintenance" if start or end else "Pending model update",
            "status": "pending_model_update" if inst.get("pending_model_update") else "scheduled",
            "window_start": start,
            "window_end": end,
            "detail": None,
            "instance_id": inst.get("instance_id"),
            "pending_model_update": inst.get("pending_model_update", False),
        })
    return rows


def _is_upcoming(not_before: str | None, not_after: str | None) -> bool:
    """Return True when the maintenance window is in the future or still in progress."""
    now = datetime.now(timezone.utc)
    start = _parse_dt(not_before)
    end = _parse_dt(not_after)
    if end and end < now:
        return False
    if start and start > now:
        return True
    if start and start <= now and end and end >= now:
        return True
    return False


def _operation_name_value(event: dict[str, Any]) -> str:
    op = event.get("operationName")
    if isinstance(op, dict):
        return str(op.get("value") or "")
    return str(op or "")


def _is_maintenance_activity_event(event: dict[str, Any]) -> bool:
    operation = _operation_name_value(event).lower()
    if not operation:
        return False
    if not any(keyword in operation for keyword in _MAINTENANCE_OPERATION_KEYWORDS):
        return False
    resource_id = str(event.get("resourceId") or "").lower()
    resource_type = event.get("resourceType")
    type_value = ""
    if isinstance(resource_type, dict):
        type_value = str(resource_type.get("value") or "").lower()
    else:
        type_value = str(resource_type or "").lower()
    return "microsoft.compute" in resource_id or "microsoft.compute" in type_value


def _activity_log_row(event: dict[str, Any]) -> dict[str, Any] | None:
    if not _is_maintenance_activity_event(event):
        return None

    operation = _operation_name_value(event)
    resource_id = event.get("resourceId") or ""
    event_ts = event.get("eventTimestamp") or event.get("submissionTimestamp")
    status_obj = event.get("status")
    status = status_obj.get("value") if isinstance(status_obj, dict) else str(status_obj or "Unknown")
    level_obj = event.get("level")
    level = level_obj.get("value") if isinstance(level_obj, dict) else str(level_obj or "")

    rid_lower = resource_id.lower()
    is_vmss = "virtualmachinescalesets" in rid_lower
    category = "vmss" if is_vmss else "vm"
    short_op = operation.rsplit("/", 1)[-1].replace("action", "") or "maintenance"
    event_key = event.get("eventDataId") or event.get("correlationId") or f"{operation}:{event_ts}"

    return {
        "id": f"activity:{event_key}",
        "source": category,
        "resource_type": "VM scale set" if is_vmss else "Virtual machine",
        "resource_name": _resource_name_from_id(resource_id),
        "resource_id": resource_id or None,
        "resource_group": _rg_from_id(resource_id),
        "title": f"Compute {short_op}",
        "status": status,
        "window_start": event_ts,
        "window_end": None,
        "detail": (
            (event.get("properties") or {}).get("statusMessage")
            or (event.get("properties") or {}).get("message")
            or level
            or operation
        ),
        "operation_name": operation,
        "event_timestamp": event_ts,
        "origin": "activity_log",
    }


# ---------------------------------------------------------------------------
# Maintenance Configurations (subscription-level schedules)
# ---------------------------------------------------------------------------

class AzureMaintenanceClient:
    """Client for Azure Planned Maintenance APIs."""

    def __init__(self, db=None):
        self._db = db

    def _headers(self) -> dict:
        return auth_headers(self._db)

    # ------------------------------------------------------------------
    # Maintenance Configurations
    # ------------------------------------------------------------------

    def list_maintenance_configurations(self, subscription_id: str) -> list[dict[str, Any]]:
        """List all maintenance configurations in a subscription.
        API: https://learn.microsoft.com/en-us/rest/api/maintenance/maintenance-configurations/list
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/providers"
            f"/Microsoft.Maintenance/maintenanceConfigurations"
        )
        try:
            return get_all_pages(url, self._headers(), {"api-version": _MAINTENANCE_API_VERSION})
        except AzureAPIError as exc:
            log.warning("maintenance.list_configs_failed", sub=subscription_id, error=str(exc))
            return []

    def list_configuration_assignments(
        self,
        subscription_id: str,
        resource_group: str | None = None,
    ) -> list[dict[str, Any]]:
        """List maintenance configuration assignments (which resources are enrolled).
        API: https://learn.microsoft.com/en-us/rest/api/maintenance/configuration-assignments/list
        """
        if resource_group:
            url = (
                f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
                f"/providers/Microsoft.Maintenance/configurationAssignments"
            )
        else:
            url = (
                f"{BASE}/subscriptions/{subscription_id}/providers"
                f"/Microsoft.Maintenance/configurationAssignments"
            )
        try:
            return get_all_pages(url, self._headers(), {"api-version": _MAINTENANCE_API_VERSION})
        except AzureAPIError as exc:
            log.warning("maintenance.list_assignments_failed", sub=subscription_id, error=str(exc))
            return []

    def list_updates_for_resource(
        self,
        subscription_id: str,
        resource_group: str,
        resource_provider: str,
        resource_type: str,
        resource_name: str,
    ) -> list[dict[str, Any]]:
        """List pending maintenance updates for a specific resource.
        API: https://learn.microsoft.com/en-us/rest/api/maintenance/updates/list
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/{resource_provider}/{resource_type}/{resource_name}"
            f"/providers/Microsoft.Maintenance/updates"
        )
        try:
            return get_all_pages(url, self._headers(), {"api-version": _MAINTENANCE_API_VERSION})
        except AzureAPIError as exc:
            log.warning(
                "maintenance.list_updates_failed",
                resource=resource_name,
                error=str(exc),
            )
            return []

    # ------------------------------------------------------------------
    # VM Redeployment / Maintenance (Compute ScheduledEvents)
    # ------------------------------------------------------------------

    def get_vm_maintenance_status(
        self,
        subscription_id: str,
        resource_group: str,
        vm_name: str,
    ) -> dict[str, Any]:
        """Get maintenance redeploy status and last/next maintenance window for a VM.
        API: https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines/get
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/virtualMachines/{vm_name}"
        )
        try:
            data = _get(url, self._headers(), {"api-version": _COMPUTE_API_VERSION})
            props = data.get("properties", {})
            maintenance_redeploy = props.get("maintenanceRedeployStatus") or {}
            return {
                "resource_id": data.get("id"),
                "resource_name": vm_name,
                "resource_type": "Microsoft.Compute/virtualMachines",
                "is_customer_initiated_maintenance_allowed": maintenance_redeploy.get(
                    "isCustomerInitiatedMaintenanceAllowed"
                ),
                "pre_maintenance_window_start": maintenance_redeploy.get(
                    "preMaintenanceWindowStartTime"
                ),
                "pre_maintenance_window_end": maintenance_redeploy.get(
                    "preMaintenanceWindowEndTime"
                ),
                "maintenance_window_start": maintenance_redeploy.get(
                    "maintenanceWindowStartTime"
                ),
                "maintenance_window_end": maintenance_redeploy.get(
                    "maintenanceWindowEndTime"
                ),
                "last_operation_result": maintenance_redeploy.get(
                    "lastOperationResultCode"
                ),
                "last_operation_message": maintenance_redeploy.get(
                    "lastOperationMessage"
                ),
                "upcoming": _is_upcoming(
                    maintenance_redeploy.get("maintenanceWindowStartTime"),
                    maintenance_redeploy.get("maintenanceWindowEndTime"),
                ),
            }
        except AzureAPIError as exc:
            log.warning("maintenance.vm_status_failed", vm=vm_name, error=str(exc))
            return {"resource_name": vm_name, "error": str(exc)}

    # ------------------------------------------------------------------
    # VMSS Maintenance
    # ------------------------------------------------------------------

    def get_vmss_maintenance_status(
        self,
        subscription_id: str,
        resource_group: str,
        vmss_name: str,
    ) -> dict[str, Any]:
        """Get maintenance status for a VMSS (platform-level OS/firmware updates).
        Includes per-instance maintenance status summary.
        API: https://learn.microsoft.com/en-us/rest/api/compute/virtual-machine-scale-sets/get
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/virtualMachineScaleSets/{vmss_name}"
        )
        try:
            data = _get(url, self._headers(), {"api-version": _COMPUTE_API_VERSION})
            props = data.get("properties", {})
            upgrade_policy = props.get("upgradePolicy") or {}
            automatic_repairs = props.get("automaticRepairsPolicy") or {}
            rolling_upgrade = props.get("rollingUpgradePolicy") or {}

            return {
                "resource_id": data.get("id"),
                "resource_name": vmss_name,
                "resource_type": "Microsoft.Compute/virtualMachineScaleSets",
                "upgrade_mode": upgrade_policy.get("mode"),  # Automatic | Rolling | Manual
                "automatic_os_upgrade_enabled": (
                    upgrade_policy.get("automaticOSUpgradePolicy", {}).get(
                        "enableAutomaticOSUpgrade", False
                    )
                ),
                "disable_automatic_rollback": (
                    upgrade_policy.get("automaticOSUpgradePolicy", {}).get(
                        "disableAutomaticRollback", False
                    )
                ),
                "rolling_upgrade_max_batch_pct": rolling_upgrade.get(
                    "maxBatchInstancePercent"
                ),
                "rolling_upgrade_max_unhealthy_pct": rolling_upgrade.get(
                    "maxUnhealthyInstancePercent"
                ),
                "rolling_upgrade_max_unhealthy_upgraded_pct": rolling_upgrade.get(
                    "maxUnhealthyUpgradedInstancePercent"
                ),
                "automatic_repairs_enabled": automatic_repairs.get("enabled", False),
                "automatic_repairs_grace_period": automatic_repairs.get("gracePeriod"),
                "platform_fault_domain_count": props.get("platformFaultDomainCount"),
            }
        except AzureAPIError as exc:
            log.warning("maintenance.vmss_status_failed", vmss=vmss_name, error=str(exc))
            return {"resource_name": vmss_name, "error": str(exc)}

    def list_vmss_instance_maintenance(
        self,
        subscription_id: str,
        resource_group: str,
        vmss_name: str,
    ) -> list[dict[str, Any]]:
        """List per-instance maintenance status for a VMSS — identifies instances
        pending reimage, update, or redeploy.
        API: https://learn.microsoft.com/en-us/rest/api/compute/virtual-machine-scale-set-vms/list
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Compute/virtualMachineScaleSets/{vmss_name}/virtualMachines"
        )
        try:
            instances = get_all_pages(
                url,
                self._headers(),
                {"api-version": _COMPUTE_API_VERSION, "$expand": "instanceView"},
            )
        except AzureAPIError as exc:
            log.warning(
                "maintenance.vmss_instances_failed", vmss=vmss_name, error=str(exc)
            )
            return []

        out: list[dict[str, Any]] = []
        for inst in instances:
            iv = (inst.get("properties") or {}).get("instanceView") or {}
            maintenance_redeploy = (inst.get("properties") or {}).get(
                "maintenanceRedeployStatus"
            ) or {}
            statuses = iv.get("statuses") or []
            maintenance_statuses = [
                s for s in statuses
                if "maintenance" in (s.get("code") or "").lower()
                or "redeploy" in (s.get("code") or "").lower()
            ]
            out.append({
                "instance_id": inst.get("instanceId"),
                "name": inst.get("name"),
                "latest_model_applied": (inst.get("properties") or {}).get(
                    "latestModelApplied", True
                ),
                "maintenance_window_start": maintenance_redeploy.get(
                    "maintenanceWindowStartTime"
                ),
                "maintenance_window_end": maintenance_redeploy.get(
                    "maintenanceWindowEndTime"
                ),
                "is_customer_initiated_maintenance_allowed": maintenance_redeploy.get(
                    "isCustomerInitiatedMaintenanceAllowed"
                ),
                "maintenance_statuses": maintenance_statuses,
                "pending_model_update": not (inst.get("properties") or {}).get(
                    "latestModelApplied", True
                ),
            })
        return out

    # ------------------------------------------------------------------
    # AKS Maintenance Configurations
    # ------------------------------------------------------------------

    def list_aks_maintenance_configurations(
        self,
        subscription_id: str,
        resource_group: str,
        cluster_name: str,
    ) -> list[dict[str, Any]]:
        """List maintenance configuration windows for an AKS cluster.
        API: https://learn.microsoft.com/en-us/rest/api/aks/maintenance-configurations/list

        Returns configured maintenance windows (time slots for node OS upgrades,
        control plane upgrades, and node image upgrades).
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ContainerService/managedClusters/{cluster_name}"
            f"/maintenanceConfigurations"
        )
        try:
            data = _get(url, self._headers(), {"api-version": _AKS_MAINTENANCE_API_VERSION})
            return data.get("value") or []
        except AzureAPIError as exc:
            log.warning(
                "maintenance.aks_configs_failed",
                cluster=cluster_name,
                error=str(exc),
            )
            return []

    def get_aks_maintenance_configuration(
        self,
        subscription_id: str,
        resource_group: str,
        cluster_name: str,
        config_name: str = "default",
    ) -> dict[str, Any]:
        """Get a specific AKS maintenance configuration (default = 'default')."""
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ContainerService/managedClusters/{cluster_name}"
            f"/maintenanceConfigurations/{config_name}"
        )
        try:
            return _get(url, self._headers(), {"api-version": _AKS_MAINTENANCE_API_VERSION})
        except AzureAPIError as exc:
            log.warning(
                "maintenance.aks_config_failed",
                cluster=cluster_name,
                config=config_name,
                error=str(exc),
            )
            return {}

    def get_aks_node_pool_vmss_maintenance(
        self,
        subscription_id: str,
        cluster_resource_group: str,
        cluster_name: str,
    ) -> list[dict[str, Any]]:
        """Discover AKS node pool VMSS resources and fetch their maintenance status.

        AKS node pools are backed by VMSS in the node resource group (MC_*).
        This method resolves that group automatically from the cluster properties.
        """
        try:
            cluster_url = (
                f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{cluster_resource_group}"
                f"/providers/Microsoft.ContainerService/managedClusters/{cluster_name}"
            )
            cluster = _get(
                cluster_url, self._headers(), {"api-version": _AKS_MAINTENANCE_API_VERSION}
            )
            node_rg = (cluster.get("properties") or {}).get("nodeResourceGroup") or ""
            if not node_rg:
                log.warning("maintenance.aks_node_rg_missing", cluster=cluster_name)
                return []
        except AzureAPIError as exc:
            log.warning("maintenance.aks_cluster_fetch_failed", cluster=cluster_name, error=str(exc))
            return []

        vmss_url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{node_rg}"
            f"/providers/Microsoft.Compute/virtualMachineScaleSets"
        )
        try:
            vmss_list = get_all_pages(
                vmss_url, self._headers(), {"api-version": _COMPUTE_API_VERSION}
            )
        except AzureAPIError as exc:
            log.warning("maintenance.aks_vmss_list_failed", node_rg=node_rg, error=str(exc))
            return []

        results: list[dict[str, Any]] = []

        def fetch_vmss(vmss: dict) -> dict[str, Any]:
            name = vmss.get("name") or ""
            status = self.get_vmss_maintenance_status(subscription_id, node_rg, name)
            instances = self.list_vmss_instance_maintenance(subscription_id, node_rg, name)
            pending = sum(1 for i in instances if i.get("pending_model_update"))
            return {
                "cluster_name": cluster_name,
                "node_resource_group": node_rg,
                "vmss_name": name,
                "vmss_id": vmss.get("id"),
                "maintenance_status": status,
                "instance_count": len(instances),
                "pending_model_updates": pending,
                "instances": instances,
            }

        workers = min(len(vmss_list), 4) if vmss_list else 1
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="aks_vmss_maint"
        ) as pool:
            results = list(pool.map(fetch_vmss, vmss_list))

        log.info(
            "maintenance.aks_vmss_fetched",
            cluster=cluster_name,
            vmss_count=len(results),
        )
        return results

    # ------------------------------------------------------------------
    # Resource Health — Planned Maintenance Events (all resource types)
    # ------------------------------------------------------------------

    def list_resource_health_events(
        self,
        subscription_id: str,
        *,
        filter_planned: bool = True,
    ) -> list[dict[str, Any]]:
        """List Resource Health events at subscription scope.
        With filter_planned=True, returns only Planned Maintenance events.
        API: https://learn.microsoft.com/en-us/rest/api/resourcehealth/events/list-by-subscription-id
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/providers"
            f"/Microsoft.ResourceHealth/events"
        )
        params: dict[str, str] = {"api-version": _RESOURCE_HEALTH_API_VERSION}
        if filter_planned:
            params["$filter"] = "properties/eventType eq 'PlannedMaintenance'"
        try:
            events = get_all_pages(url, self._headers(), params)
        except AzureAPIError as exc:
            log.warning(
                "maintenance.health_events_failed",
                sub=subscription_id,
                error=str(exc),
                filter_used=filter_planned,
            )
            if not filter_planned:
                return []
            try:
                events = get_all_pages(
                    url,
                    self._headers(),
                    {"api-version": _RESOURCE_HEALTH_API_VERSION},
                )
            except AzureAPIError as fallback_exc:
                log.warning(
                    "maintenance.health_events_unfiltered_failed",
                    sub=subscription_id,
                    error=str(fallback_exc),
                )
                return []
        if filter_planned:
            events = [e for e in events if _is_planned_maintenance_event(e)]
        return events

    def list_activity_log_maintenance_events(
        self,
        subscription_id: str,
        *,
        lookback_days: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query Azure Monitor activity logs for VM/VMSS maintenance operations.

        VMSS planned maintenance is not surfaced in Service Health; platform
        live migration, redeploy, and upgrade operations appear here instead.
        API: https://learn.microsoft.com/en-us/rest/api/monitor/activity-logs/list
        """
        days = lookback_days if lookback_days is not None else _ACTIVITY_LOG_LOOKBACK_DAYS
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=max(1, days))
        start_iso = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = end.strftime("%Y-%m-%dT%H:%M:%SZ")
        odata_filter = (
            f"eventTimestamp ge '{start_iso}' and eventTimestamp le '{end_iso}' "
            "and resourceProvider eq 'Microsoft.Compute'"
        )
        url = (
            f"{BASE}/subscriptions/{subscription_id}/providers"
            f"/microsoft.Insights/eventtypes/management/values"
        )
        try:
            events = get_all_pages(
                url,
                self._headers(),
                {"api-version": _ACTIVITY_LOG_API_VERSION, "$filter": odata_filter},
            )
        except AzureAPIError as exc:
            log.warning(
                "maintenance.activity_log_failed",
                sub=subscription_id,
                error=str(exc),
            )
            return []

        rows: list[dict[str, Any]] = []
        for event in events:
            row = _activity_log_row(event)
            if row:
                rows.append(row)
        log.info(
            "maintenance.activity_log_fetched",
            sub=subscription_id,
            events=len(events),
            maintenance_rows=len(rows),
            lookback_days=days,
        )
        return rows

    def list_availability_statuses(self, subscription_id: str) -> list[dict[str, Any]]:
        """List current availability statuses for resources in a subscription.

        API: https://learn.microsoft.com/en-us/rest/api/resourcehealth/availability-statuses/list-by-subscription-id
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/providers"
            f"/Microsoft.ResourceHealth/availabilityStatuses"
        )
        try:
            return get_all_pages(
                url,
                self._headers(),
                {"api-version": _RESOURCE_HEALTH_API_VERSION},
            )
        except AzureAPIError as exc:
            log.warning(
                "maintenance.list_availability_statuses_failed",
                sub=subscription_id,
                error=str(exc),
            )
            return []

    def get_resource_health_status(
        self,
        subscription_id: str,
        resource_group: str,
        resource_provider: str,
        resource_type: str,
        resource_name: str,
    ) -> dict[str, Any]:
        """Get current availability / health status for a resource.
        API: https://learn.microsoft.com/en-us/rest/api/resourcehealth/availability-statuses/get-by-resource
        """
        url = (
            f"{BASE}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/{resource_provider}/{resource_type}/{resource_name}"
            f"/providers/Microsoft.ResourceHealth/availabilityStatuses/current"
        )
        try:
            return _get(url, self._headers(), {"api-version": _RESOURCE_HEALTH_API_VERSION})
        except AzureAPIError as exc:
            log.warning(
                "maintenance.resource_health_failed",
                resource=resource_name,
                error=str(exc),
            )
            return {}

    # ------------------------------------------------------------------
    # Planned maintenance board (VMs, VMSS, health events)
    # ------------------------------------------------------------------

    def list_planned_maintenance(
        self,
        subscription_id: str,
        *,
        upcoming_only: bool = True,
    ) -> dict[str, Any]:
        """Unified planned maintenance feed for VMs, VMSS, and service health events."""
        from app.azure_resources import AzureResourcesClient
        from app.http_client import arm_patient_active

        rc = AzureResourcesClient(db=self._db)
        items: list[dict[str, Any]] = []
        patient = arm_patient_active()

        for event in self.list_resource_health_events(subscription_id, filter_planned=True):
            items.append(_health_event_row(event))

        vms = rc.list_vms(subscription_id, include_instance_view=False)

        def check_vm(vm: dict[str, Any]) -> dict[str, Any] | None:
            rg = _rg_from_id(vm.get("id", ""))
            name = vm.get("name", "")
            if not rg or not name:
                return None
            status = self.get_vm_maintenance_status(subscription_id, rg, name)
            if status.get("error"):
                return None
            return _vm_maintenance_row(vm, status)

        vm_cap = 2 if patient else 4
        vm_workers = min(len(vms), vm_cap) if vms else 1
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=vm_workers, thread_name_prefix="planned_vm_maint"
        ) as pool:
            for row in pool.map(check_vm, vms):
                if row:
                    items.append(row)

        vmss_list = rc.list_vm_scale_sets(subscription_id)
        vmss_cap = 2 if patient else 3
        vmss_workers = min(len(vmss_list), vmss_cap) if vmss_list else 1

        def check_vmss(vmss: dict[str, Any]) -> list[dict[str, Any]]:
            return _vmss_maintenance_rows(subscription_id, vmss, self)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=vmss_workers, thread_name_prefix="planned_vmss_maint"
        ) as pool:
            for rows in pool.map(check_vmss, vmss_list):
                items.extend(rows)

        if not upcoming_only:
            for row in self.list_activity_log_maintenance_events(subscription_id):
                items.append(row)

        from app.maintenance_sync import filter_upcoming_items

        if upcoming_only:
            items = filter_upcoming_items(items, upcoming_only=True)

        items.sort(key=lambda row: row.get("window_start") or "9999-12-31T23:59:59Z")

        by_source: dict[str, int] = {}
        for row in items:
            source = row.get("source") or "other"
            by_source[source] = by_source.get(source, 0) + 1

        return {
            "subscription_id": subscription_id,
            "count": len(items),
            "upcoming_only": upcoming_only,
            "summary": {
                "health_events": by_source.get("health_event", 0),
                "vms": by_source.get("vm", 0),
                "vmss": by_source.get("vmss", 0),
                "vmss_instances": by_source.get("vmss_instance", 0),
            },
            "items": items,
        }

    # ------------------------------------------------------------------
    # Subscription-wide Maintenance Summary
    # ------------------------------------------------------------------

    def get_subscription_maintenance_summary(
        self,
        subscription_id: str,
    ) -> dict[str, Any]:
        """Aggregate maintenance status across all VMs, VMSS, and AKS clusters
        in a subscription. Returns a summary suitable for the dashboard.
        """
        from app.azure_resources import AzureResourcesClient
        rc = AzureResourcesClient(db=self._db)

        vms = rc.list_vms(subscription_id, include_instance_view=False)
        vmss_list = rc.list_vm_scale_sets(subscription_id)
        aks_clusters = rc.list_aks_clusters(subscription_id)
        health_events = self.list_resource_health_events(subscription_id, filter_planned=True)

        vm_count = len(vms)
        vmss_count = len(vmss_list)
        aks_count = len(aks_clusters)

        # Summarise VMSS with pending model updates
        vmss_pending: list[dict[str, Any]] = []

        def check_vmss(vmss: dict) -> dict[str, Any] | None:
            rg = _rg_from_id(vmss.get("id", ""))
            name = vmss.get("name", "")
            if not rg or not name:
                return None
            instances = self.list_vmss_instance_maintenance(subscription_id, rg, name)
            pending = sum(1 for i in instances if i.get("pending_model_update"))
            if pending > 0:
                return {
                    "vmss_name": name,
                    "resource_group": rg,
                    "pending_model_updates": pending,
                    "instance_count": len(instances),
                }
            return None

        vmss_workers = min(len(vmss_list), 6) if vmss_list else 1
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=vmss_workers, thread_name_prefix="vmss_maint_summary"
        ) as pool:
            for result in pool.map(check_vmss, vmss_list):
                if result:
                    vmss_pending.append(result)

        # AKS maintenance configuration summary
        aks_without_maintenance: list[str] = []
        for cluster in aks_clusters:
            rg = _rg_from_id(cluster.get("id", ""))
            name = cluster.get("name", "")
            if not rg or not name:
                continue
            configs = self.list_aks_maintenance_configurations(
                subscription_id, rg, name
            )
            if not configs:
                aks_without_maintenance.append(name)

        return {
            "subscription_id": subscription_id,
            "resource_counts": {
                "vms": vm_count,
                "vmss": vmss_count,
                "aks_clusters": aks_count,
            },
            "planned_health_events": len(health_events),
            "health_event_titles": [
                e.get("properties", {}).get("title") or e.get("name") or ""
                for e in health_events[:10]
            ],
            "vmss_pending_model_updates": vmss_pending,
            "aks_clusters_without_maintenance_config": aks_without_maintenance,
            "aks_maintenance_config_coverage_pct": (
                round(
                    (aks_count - len(aks_without_maintenance)) / aks_count * 100, 1
                )
                if aks_count
                else 100.0
            ),
        }


# ---------------------------------------------------------------------------
# Convenience top-level functions
# ---------------------------------------------------------------------------

def enrich_resources_with_maintenance(
    resources: list[dict[str, Any]],
    subscription_id: str,
    db=None,
) -> list[dict[str, Any]]:
    """Attach maintenance status to a list of ARM resources (VMs and VMSS).

    Resources that are not VMs or VMSS are passed through unchanged.
    Maintenance info is attached under the key ``maintenance_status``.
    """
    client = AzureMaintenanceClient(db=db)
    health_events = client.list_resource_health_events(subscription_id, filter_planned=True)
    health_titles = {
        (e.get("properties") or {}).get("impactedResource") or "": e
        for e in health_events
    }

    def enrich(resource: dict[str, Any]) -> dict[str, Any]:
        rtype = (resource.get("type") or "").lower()
        rid = resource.get("id", "")
        rg = _rg_from_id(rid)
        name = resource.get("name", "")

        if rtype == "microsoft.compute/virtualmachines" and rg and name:
            status = client.get_vm_maintenance_status(subscription_id, rg, name)
            resource["maintenance_status"] = status

        elif rtype == "microsoft.compute/virtualmachinescalesets" and rg and name:
            status = client.get_vmss_maintenance_status(subscription_id, rg, name)
            resource["maintenance_status"] = status

        # Attach any matching Resource Health planned event
        matched_event = health_titles.get(rid)
        if matched_event:
            resource["planned_health_event"] = {
                "title": (matched_event.get("properties") or {}).get("title"),
                "impact_start": (matched_event.get("properties") or {}).get(
                    "impactStartTime"
                ),
                "impact_mitigation": (matched_event.get("properties") or {}).get(
                    "impactMitigationTime"
                ),
            }

        return resource

    workers = min(len(resources), 8) if resources else 1
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="maint_enrich"
    ) as pool:
        enriched = list(pool.map(enrich, resources))

    log.info(
        "maintenance.enrich_done",
        total=len(enriched),
        health_events=len(health_events),
    )
    return enriched

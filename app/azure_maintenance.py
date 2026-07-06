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
from datetime import datetime, timezone
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


def _is_upcoming(not_before: str | None, not_after: str | None) -> bool:
    """Return True when the maintenance window overlaps with now or is in the future."""
    now = datetime.now(timezone.utc)
    end = _parse_dt(not_after)
    if end and end < now:
        return False
    return True


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
            params["$filter"] = "eventType eq 'PlannedMaintenance'"
        try:
            return get_all_pages(url, self._headers(), params)
        except AzureAPIError as exc:
            log.warning(
                "maintenance.health_events_failed", sub=subscription_id, error=str(exc)
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

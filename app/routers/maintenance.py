"""Maintenance Page Router

Dedicated API page for Azure Planned Maintenance across all resource types.

Endpoints
---------
GET  /maintenance/{subscription_id}/summary
     High-level summary: planned events, VMSS pending updates, AKS config coverage
GET  /maintenance/{subscription_id}/health-events
     All planned Resource Health events
GET  /maintenance/{subscription_id}/vmss
     VMSS maintenance status list (optionally filter pending-only)
GET  /maintenance/{subscription_id}/aks/{resource_group}/{cluster_name}
     AKS cluster maintenance config + node pool VMSS maintenance
GET  /maintenance/{subscription_id}/vm/{resource_group}/{vm_name}
     Single VM maintenance window status
GET  /maintenance/{subscription_id}/configurations
     All maintenance configurations enrolled in the subscription
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.user_auth import require_viewer

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])


def _db(db: Session = Depends(get_db), _=Depends(require_viewer)):
    return db


@router.get("/{subscription_id}/summary")
def maintenance_summary(
    subscription_id: str,
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """Subscription-wide maintenance summary dashboard payload."""
    from app.azure_maintenance import AzureMaintenanceClient
    mc = AzureMaintenanceClient(db=db)
    return mc.get_subscription_maintenance_summary(subscription_id)


@router.get("/{subscription_id}/health-events")
def health_events(
    subscription_id: str,
    planned_only: bool = Query(True),
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """Resource Health planned maintenance events."""
    from app.azure_maintenance import AzureMaintenanceClient
    mc = AzureMaintenanceClient(db=db)
    events = mc.list_resource_health_events(
        subscription_id, filter_planned=planned_only
    )
    return {
        "subscription_id": subscription_id,
        "count": len(events),
        "events": [
            {
                "name": e.get("name"),
                "title": (e.get("properties") or {}).get("title"),
                "event_type": (e.get("properties") or {}).get("eventType"),
                "status": (e.get("properties") or {}).get("eventSubType"),
                "impact_start": (e.get("properties") or {}).get("impactStartTime"),
                "impact_mitigation": (e.get("properties") or {}).get(
                    "impactMitigationTime"
                ),
                "impacted_resource": (e.get("properties") or {}).get(
                    "impactedResource"
                ),
                "description": (e.get("properties") or {}).get("summary"),
            }
            for e in events
        ],
    }


@router.get("/{subscription_id}/vmss")
def vmss_maintenance(
    subscription_id: str,
    pending_only: bool = Query(False, description="Only return VMSS with pending instance model updates"),
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """VMSS maintenance status across the subscription."""
    from app.azure_resources import AzureResourcesClient
    from app.azure_maintenance import AzureMaintenanceClient

    rc = AzureResourcesClient(db=db)
    mc = AzureMaintenanceClient(db=db)

    vmss_list = rc.list_vm_scale_sets(subscription_id, include_maintenance=True)

    results = []
    for vmss in vmss_list:
        rid = vmss.get("id", "")
        parts = rid.split("/")
        try:
            rg_idx = [p.lower() for p in parts].index("resourcegroups")
            rg = parts[rg_idx + 1]
        except (ValueError, IndexError):
            rg = ""
        name = vmss.get("name", "")
        instances = []
        pending = 0
        if rg and name:
            instances = mc.list_vmss_instance_maintenance(subscription_id, rg, name)
            pending = sum(1 for i in instances if i.get("pending_model_update"))

        entry = {
            "vmss_id": rid,
            "vmss_name": name,
            "resource_group": rg,
            "location": vmss.get("location"),
            "maintenance_status": vmss.get("maintenance_status") or {},
            "instance_count": len(instances),
            "pending_model_updates": pending,
        }
        if pending_only and pending == 0:
            continue
        results.append(entry)

    return {
        "subscription_id": subscription_id,
        "count": len(results),
        "pending_only_filter": pending_only,
        "items": results,
    }


@router.get("/{subscription_id}/aks/{resource_group}/{cluster_name}")
def aks_maintenance(
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """AKS cluster maintenance configurations + node pool VMSS maintenance."""
    from app.azure_maintenance import AzureMaintenanceClient
    mc = AzureMaintenanceClient(db=db)

    configs = mc.list_aks_maintenance_configurations(
        subscription_id, resource_group, cluster_name
    )
    node_pool_vmss = mc.get_aks_node_pool_vmss_maintenance(
        subscription_id, resource_group, cluster_name
    )
    total_pending = sum(v.get("pending_model_updates", 0) for v in node_pool_vmss)

    return {
        "subscription_id": subscription_id,
        "resource_group": resource_group,
        "cluster_name": cluster_name,
        "maintenance_configurations": configs,
        "has_maintenance_config": bool(configs),
        "node_pool_vmss": node_pool_vmss,
        "total_node_pools": len(node_pool_vmss),
        "total_pending_instance_updates": total_pending,
    }


@router.get("/{subscription_id}/vm/{resource_group}/{vm_name}")
def vm_maintenance(
    subscription_id: str,
    resource_group: str,
    vm_name: str,
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """Single VM planned maintenance window and redeploy status."""
    from app.azure_maintenance import AzureMaintenanceClient
    mc = AzureMaintenanceClient(db=db)
    return mc.get_vm_maintenance_status(subscription_id, resource_group, vm_name)


@router.get("/{subscription_id}/configurations")
def maintenance_configurations(
    subscription_id: str,
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """All maintenance configurations and assignments for the subscription."""
    from app.azure_maintenance import AzureMaintenanceClient
    mc = AzureMaintenanceClient(db=db)
    configs = mc.list_maintenance_configurations(subscription_id)
    assignments = mc.list_configuration_assignments(subscription_id)
    return {
        "subscription_id": subscription_id,
        "configurations": {"count": len(configs), "items": configs},
        "assignments": {"count": len(assignments), "items": assignments},
    }

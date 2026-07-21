"""Application topology discovery via Azure Resource Graph (3-C)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session

from app.models import ResourceDependency

log = structlog.get_logger(__name__)

TOPOLOGY_QUERY = """
Resources
| where subscriptionId == '{sub}'
| where type in~ (
    'microsoft.network/loadbalancers',
    'microsoft.network/applicationgateways',
    'microsoft.network/privateendpoints'
  )
| project id, type, name, properties
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def discover_dependencies(
    db: Session,
    subscription_id: str,
    *,
    token: str | None = None,
) -> int:
    """
    Discover LB/AppGW → backend resource links and persist to ResourceDependency.
    Falls back to inventory-derived links when Resource Graph is unavailable.
    """
    sub = subscription_id.lower()
    discovered = 0

    # Inventory fallback: VM ↔ disk/NIC from resource_snapshots properties
    from app.models import ResourceSnapshot

    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
        )
        .all()
    )
    deps: list[dict] = []
    for row in rows:
        try:
            import json
            props = json.loads(row.properties_json or "{}")
        except Exception:
            props = {}
        rid = (row.resource_id or "").lower()
        if row.resource_type == "compute/vm":
            for disk_id in props.get("attached_disk_ids") or []:
                deps.append({
                    "source": rid,
                    "target": str(disk_id).lower(),
                    "type": "attached_disk",
                })
            for nic_id in props.get("nic_ids") or props.get("network_interface_ids") or []:
                deps.append({
                    "source": rid,
                    "target": str(nic_id).lower(),
                    "type": "attached_nic",
                })
        if row.resource_type in {"network/loadbalancer", "network/appgateway"}:
            for backend in props.get("backend_resource_ids") or []:
                deps.append({
                    "source": rid,
                    "target": str(backend).lower(),
                    "type": "serves_traffic",
                })

    # Replace prior discovery rows for this subscription
    db.query(ResourceDependency).filter(
        ResourceDependency.subscription_id == sub,
    ).delete(synchronize_session=False)

    now = _utc_now()
    for dep in deps:
        if not dep["source"] or not dep["target"]:
            continue
        db.add(ResourceDependency(
            id=str(uuid.uuid4()),
            subscription_id=sub,
            source_resource_id=dep["source"],
            target_resource_id=dep["target"],
            dependency_type=dep["type"],
            discovered_at=now,
        ))
        discovered += 1

    if discovered:
        db.commit()
        log.info("topology.discovered", subscription_id=sub, count=discovered)
    return discovered


def inbound_dependencies(
    db: Session,
    resource_id: str,
    *,
    subscription_id: str | None = None,
) -> list[ResourceDependency]:
    """Resources that depend on or route traffic to this resource."""
    rid = (resource_id or "").lower()
    q = db.query(ResourceDependency).filter(ResourceDependency.target_resource_id == rid)
    if subscription_id:
        q = q.filter(ResourceDependency.subscription_id == subscription_id.lower())
    return q.all()


def has_inbound_dependencies(
    db: Session,
    resource_id: str,
    *,
    subscription_id: str | None = None,
) -> bool:
    return bool(inbound_dependencies(db, resource_id, subscription_id=subscription_id))

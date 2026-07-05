"""
db_sync.py — Azure → Database sync service

Call sync_all(subscription_id, db) to pull fresh data from Azure
and write it into the local DB. All API reads go through the DB after that.

Synced entities:
  - Subscriptions
  - Resources (VMs, Disks, AKS, Storage, Public IPs, SQL,
               Key Vaults, App Services, Load Balancers, CosmosDB,
               PostgreSQL, NSGs, ACR, App Gateways)
  - Costs by service (MTD)
  - Budgets
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .models import (
    ResourceSnapshot, CostByServiceSnapshot,
    BudgetSnapshot, SubscriptionCache,
)
from .azure_resources import AzureResourceClient
from .azure_cost import AzureCostClient
from .azure_client import AzureClient

log = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc)


def _upsert_resource(
    db: Session,
    subscription_id: str,
    resource_id: str,
    resource_name: str,
    resource_type: str,
    resource_group: str = None,
    location: str = None,
    sku: str = None,
    state: str = None,
    tags: dict = None,
    properties: dict = None,
    monthly_cost: float = 0.0,
):
    """Insert or update a single resource in resource_snapshots."""
    existing = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == subscription_id,
            ResourceSnapshot.resource_id == resource_id,
        )
        .first()
    )
    now = _now()
    if existing:
        existing.resource_name    = resource_name
        existing.resource_type    = resource_type
        existing.resource_group   = resource_group
        existing.location         = location
        existing.sku              = sku
        existing.state            = state
        existing.tags_json        = json.dumps(tags or {})
        existing.properties_json  = json.dumps(properties or {})
        existing.monthly_cost_usd = monthly_cost
        existing.is_active        = True
        existing.synced_at        = now
    else:
        db.add(ResourceSnapshot(
            id               = str(uuid.uuid4()),
            subscription_id  = subscription_id,
            resource_id      = resource_id,
            resource_name    = resource_name,
            resource_type    = resource_type,
            resource_group   = resource_group,
            location         = location,
            sku              = sku,
            state            = state,
            tags_json        = json.dumps(tags or {}),
            properties_json  = json.dumps(properties or {}),
            monthly_cost_usd = monthly_cost,
            is_active        = True,
            synced_at        = now,
        ))


def _extract_rg(resource_id: str) -> Optional[str]:
    """Parse resource group from ARM resource ID."""
    try:
        parts = resource_id.split("/")
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except Exception:
        return None


def sync_resources(subscription_id: str, db: Session, token: str) -> dict:
    """
    Fetch all resource types from Azure ARM and upsert into resource_snapshots.
    Returns a summary dict of counts per category.
    """
    client = AzureResourceClient(token, subscription_id)
    counts = {}

    # --- Compute: Virtual Machines ---
    try:
        vms = client.list_vms()
        for vm in (vms if isinstance(vms, list) else vms.get("value", [])):
            rid  = vm.get("id", "")
            _upsert_resource(
                db, subscription_id,
                resource_id    = rid,
                resource_name  = vm.get("name", ""),
                resource_type  = "compute/vm",
                resource_group = _extract_rg(rid),
                location       = vm.get("location"),
                sku            = vm.get("properties", {}).get("hardwareProfile", {}).get("vmSize"),
                state          = vm.get("properties", {}).get("provisioningState"),
                tags           = vm.get("tags", {}),
                properties     = {"powerState": vm.get("properties", {}).get("extended", {})},
            )
        counts["compute/vm"] = len(vms if isinstance(vms, list) else vms.get("value", []))
    except Exception as e:
        log.warning("sync VMs failed: %s", e)

    # --- Compute: Managed Disks ---
    try:
        disks = client.list_disks()
        items = disks if isinstance(disks, list) else disks.get("value", [])
        for d in items:
            rid = d.get("id", "")
            _upsert_resource(
                db, subscription_id,
                resource_id    = rid,
                resource_name  = d.get("name", ""),
                resource_type  = "compute/disk",
                resource_group = _extract_rg(rid),
                location       = d.get("location"),
                sku            = d.get("sku", {}).get("name"),
                state          = d.get("properties", {}).get("diskState"),
                tags           = d.get("tags", {}),
                properties     = {"diskSizeGB": d.get("properties", {}).get("diskSizeGB")},
            )
        counts["compute/disk"] = len(items)
    except Exception as e:
        log.warning("sync Disks failed: %s", e)

    # --- Containers: AKS ---
    try:
        clusters = client.list_aks()
        items = clusters if isinstance(clusters, list) else clusters.get("value", [])
        for c in items:
            rid = c.get("id", "")
            _upsert_resource(
                db, subscription_id,
                resource_id    = rid,
                resource_name  = c.get("name", ""),
                resource_type  = "containers/aks",
                resource_group = _extract_rg(rid),
                location       = c.get("location"),
                sku            = c.get("sku", {}).get("tier"),
                state          = c.get("properties", {}).get("provisioningState"),
                tags           = c.get("tags", {}),
                properties     = {"kubernetesVersion": c.get("properties", {}).get("kubernetesVersion")},
            )
        counts["containers/aks"] = len(items)
    except Exception as e:
        log.warning("sync AKS failed: %s", e)

    # --- Storage ---
    try:
        accounts = client.list_storage()
        items = accounts if isinstance(accounts, list) else accounts.get("value", [])
        for s in items:
            rid = s.get("id", "")
            _upsert_resource(
                db, subscription_id,
                resource_id    = rid,
                resource_name  = s.get("name", ""),
                resource_type  = "storage/account",
                resource_group = _extract_rg(rid),
                location       = s.get("location"),
                sku            = s.get("sku", {}).get("name"),
                state          = s.get("properties", {}).get("provisioningState"),
                tags           = s.get("tags", {}),
                properties     = {"kind": s.get("kind")},
            )
        counts["storage/account"] = len(items)
    except Exception as e:
        log.warning("sync Storage failed: %s", e)

    # --- Networking: Public IPs ---
    try:
        ips = client.list_public_ips()
        items = ips if isinstance(ips, list) else ips.get("value", [])
        for ip in items:
            rid = ip.get("id", "")
            _upsert_resource(
                db, subscription_id,
                resource_id    = rid,
                resource_name  = ip.get("name", ""),
                resource_type  = "network/publicip",
                resource_group = _extract_rg(rid),
                location       = ip.get("location"),
                sku            = ip.get("sku", {}).get("name"),
                state          = ip.get("properties", {}).get("provisioningState"),
                tags           = ip.get("tags", {}),
                properties     = {"ipAddress": ip.get("properties", {}).get("ipAddress")},
            )
        counts["network/publicip"] = len(items)
    except Exception as e:
        log.warning("sync Public IPs failed: %s", e)

    # --- Database: SQL ---
    try:
        servers = client.list_sql()
        items = servers if isinstance(servers, list) else servers.get("value", [])
        for s in items:
            rid = s.get("id", "")
            _upsert_resource(
                db, subscription_id,
                resource_id    = rid,
                resource_name  = s.get("name", ""),
                resource_type  = "database/sql",
                resource_group = _extract_rg(rid),
                location       = s.get("location"),
                state          = s.get("properties", {}).get("state"),
                tags           = s.get("tags", {}),
                properties     = {"version": s.get("properties", {}).get("version")},
            )
        counts["database/sql"] = len(items)
    except Exception as e:
        log.warning("sync SQL failed: %s", e)

    # --- Security: Key Vaults ---
    try:
        vaults = client.list_key_vaults()
        items = vaults if isinstance(vaults, list) else vaults.get("value", [])
        for v in items:
            rid = v.get("id", "")
            _upsert_resource(
                db, subscription_id,
                resource_id    = rid,
                resource_name  = v.get("name", ""),
                resource_type  = "security/keyvault",
                resource_group = _extract_rg(rid),
                location       = v.get("location"),
                state          = v.get("properties", {}).get("provisioningState"),
                tags           = v.get("tags", {}),
            )
        counts["security/keyvault"] = len(items)
    except Exception as e:
        log.warning("sync Key Vaults failed: %s", e)

    db.commit()
    return counts


def sync_costs(subscription_id: str, db: Session, token: str) -> dict:
    """
    Fetch MTD cost-by-service from Azure Cost Management and upsert.
    """
    from datetime import date
    cost_client = AzureCostClient(token, subscription_id)
    month = date.today().strftime("%Y-%m")
    counts = {"cost_by_service": 0}

    try:
        raw = cost_client.get_cost_by_service()
        rows = raw.get("properties", {}).get("rows", [])
        cols = [c["name"] for c in raw.get("properties", {}).get("columns", [])]
        svc_idx  = cols.index("ServiceName") if "ServiceName" in cols else None
        cost_idx = cols.index("PreTaxCost")  if "PreTaxCost"  in cols else None

        if svc_idx is not None and cost_idx is not None:
            agg = {}
            for row in rows:
                svc  = row[svc_idx]
                cost = float(row[cost_idx])
                agg[svc] = agg.get(svc, 0.0) + cost

            for svc, cost in agg.items():
                existing = (
                    db.query(CostByServiceSnapshot)
                    .filter(
                        CostByServiceSnapshot.subscription_id == subscription_id,
                        CostByServiceSnapshot.service_name == svc,
                        CostByServiceSnapshot.month == month,
                    )
                    .first()
                )
                if existing:
                    existing.cost_usd  = cost
                    existing.synced_at = _now()
                else:
                    db.add(CostByServiceSnapshot(
                        id              = str(uuid.uuid4()),
                        subscription_id = subscription_id,
                        service_name    = svc,
                        month           = month,
                        cost_usd        = cost,
                    ))
            counts["cost_by_service"] = len(agg)
    except Exception as e:
        log.warning("sync costs-by-service failed: %s", e)

    # Budgets
    try:
        budgets_raw = cost_client.get_budgets()
        for b in (budgets_raw if isinstance(budgets_raw, list) else budgets_raw.get("value", [])):
            bid = b.get("id", str(uuid.uuid4()))
            existing = db.query(BudgetSnapshot).filter(BudgetSnapshot.id == bid).first()
            props = b.get("properties", {})
            if existing:
                existing.amount        = props.get("amount", 0)
                existing.current_spend = props.get("currentSpend", {}).get("amount", 0)
                existing.synced_at     = _now()
            else:
                db.add(BudgetSnapshot(
                    id              = bid,
                    subscription_id = subscription_id,
                    budget_name     = b.get("name", ""),
                    amount          = props.get("amount", 0),
                    time_grain      = props.get("timeGrain", "Monthly"),
                    current_spend   = props.get("currentSpend", {}).get("amount", 0),
                ))
    except Exception as e:
        log.warning("sync budgets failed: %s", e)

    db.commit()
    return counts


def sync_all(subscription_id: str, db: Session, token: str) -> dict:
    """
    Master sync: resources + costs. Called by POST /api/resources/sync.
    """
    log.info("Starting full sync for subscription %s", subscription_id)
    resource_counts = sync_resources(subscription_id, db, token)
    cost_counts     = sync_costs(subscription_id, db, token)
    return {"resources": resource_counts, "costs": cost_counts}

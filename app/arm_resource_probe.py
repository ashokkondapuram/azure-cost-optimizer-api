"""Lazy ARM GET for a single resource by full resource ID."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session

from app.arm_api_versions import api_version_for_arm_type
from app.auth import auth_headers
from app.focus_mapping import normalize_arm_id
from app.http_client import BASE, AzureAPIError, _get
from app.models import CostByResourceSnapshot, ResourceSnapshot

log = structlog.get_logger()


def arm_type_from_id(resource_id: str) -> str:
    """Lowercase provider/type from a full ARM resource ID."""
    parts = (resource_id or "").strip("/").split("/")
    try:
        idx = [p.lower() for p in parts].index("providers")
        if idx + 2 < len(parts):
            return f"{parts[idx + 1]}/{parts[idx + 2]}".lower()
    except ValueError:
        pass
    return ""


def resource_name_from_id(resource_id: str) -> str:
    rid = (resource_id or "").strip("/")
    return rid.rsplit("/", 1)[-1] if rid else ""


def get_arm_resource(resource_id: str, db: Session, token: str | None = None) -> dict:
    """GET a single resource from ARM. Raises AzureAPIError on failure (404 = not found)."""
    rid = normalize_arm_id(resource_id)
    if not rid:
        raise AzureAPIError(400, "BadRequest", "Invalid resource ID")
    arm_type = arm_type_from_id(rid)
    api_version = api_version_for_arm_type(arm_type)
    url = f"{BASE}{rid}"
    headers = auth_headers(db)
    return _get(url, headers, {"api-version": api_version})


def _inventory_row_for_id(db: Session, subscription_id: str, resource_id: str) -> ResourceSnapshot | None:
    sub = subscription_id.lower()
    rid = normalize_arm_id(resource_id)
    if not rid:
        return None
    for row in (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
        )
        .all()
    ):
        if normalize_arm_id(row.resource_id) != rid:
            continue
        try:
            import json

            props = json.loads(row.properties_json or "{}")
        except Exception:
            props = {}
        if props.get("source") == "cost_export":
            continue
        return row
    return None


def _update_cost_azure_status(
    db: Session,
    subscription_id: str,
    resource_id: str,
    *,
    exists: bool,
    month: str | None = None,
) -> None:
    from app.cost_db import _resolve_cost_month

    sub = subscription_id.lower()
    rid = normalize_arm_id(resource_id)
    if not rid:
        return
    resolved_month = month or _resolve_cost_month(db, subscription_id, "MonthToDate", None)
    if not resolved_month:
        return
    row = (
        db.query(CostByResourceSnapshot)
        .filter(
            CostByResourceSnapshot.subscription_id == sub,
            CostByResourceSnapshot.resource_id == rid,
            CostByResourceSnapshot.month == resolved_month,
        )
        .first()
    )
    if row is None:
        return
    row.azure_exists = exists
    row.azure_checked_at = datetime.now(timezone.utc)


def probe_billed_resource(
    db: Session,
    subscription_id: str,
    resource_id: str,
    token: str,
) -> dict:
    """
    Resolve Azure existence and properties for a billed resource (lazy load).

    Checks local inventory first, then ARM GET. Updates cost_by_resource.azure_exists.
    """
    from app.auth import arm_auth_context
    from app.billed_resources import billed_row_from_cost

    sub = subscription_id.lower()
    rid = normalize_arm_id(resource_id)
    inv = _inventory_row_for_id(db, sub, rid)
    if inv is not None:
        _update_cost_azure_status(db, sub, rid, exists=True)
        db.commit()
        from app.resource_store import rows_to_list

        row = rows_to_list([inv])[0]
        return {
            "status": "ok",
            "azureStatus": "exists",
            "source": "inventory",
            "resource": row,
        }

    with arm_auth_context(db=db, token=token):
        try:
            arm_payload = get_arm_resource(rid, db, token)
        except AzureAPIError as exc:
            if exc.status == 404:
                _update_cost_azure_status(db, sub, rid, exists=False)
                db.commit()
                cost_row = (
                    db.query(CostByResourceSnapshot)
                    .filter(
                        CostByResourceSnapshot.subscription_id == sub,
                        CostByResourceSnapshot.resource_id == rid,
                    )
                    .order_by(CostByResourceSnapshot.month.desc())
                    .first()
                )
                stub = billed_row_from_cost(cost_row, None) if cost_row else {
                    "id": rid,
                    "name": resource_name_from_id(rid),
                    "azureStatus": "missing",
                    "state": "Doesn't exist on Azure",
                }
                return {
                    "status": "ok",
                    "azureStatus": "missing",
                    "source": "arm",
                    "resource": stub,
                }
            raise

    _update_cost_azure_status(db, sub, rid, exists=True)
    db.commit()
    props = arm_payload.get("properties") or {}
    return {
        "status": "ok",
        "azureStatus": "exists",
        "source": "arm",
        "resource": {
            "id": normalize_arm_id(arm_payload.get("id") or rid),
            "name": arm_payload.get("name") or resource_name_from_id(rid),
            "type": arm_payload.get("type") or arm_type_from_id(rid),
            "resourceGroup": (arm_payload.get("id") or rid).split("/resourceGroups/")[-1].split("/")[0]
            if "/resourceGroups/" in (arm_payload.get("id") or rid)
            else "",
            "location": arm_payload.get("location"),
            "properties": props,
            "tags": arm_payload.get("tags") or {},
            "state": props.get("provisioningState") or props.get("powerState", {}).get("code"),
            "azureStatus": "exists",
        },
    }

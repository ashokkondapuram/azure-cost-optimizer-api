"""Shared helpers for live Azure ARM inventory reads."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session
import structlog

from app.arm_resource_enrichment import enrich_arm_resources_for_type
from app.auth import arm_auth_context, get_token
from app.cost_db import resource_cost_map_from_db
from app.http_client import AzureAPIError
from app.resource_store import apply_costs_to_resources

log = structlog.get_logger(__name__)


def paginate_list(rows: list, limit: int | None, offset: int) -> list | dict[str, Any]:
    if limit is None:
        return rows
    total = len(rows)
    page = rows[offset: offset + limit]
    return {
        "items": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(page) < total,
    }


def fetch_live_resources(
    subscription_id: str,
    db: Session,
    resource_client: Any,
    resource_type: str,
    live_fn: Callable[[], list],
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list | dict[str, Any]:
    """Fetch inventory from Azure ARM, enrich, and attach DB cost hints."""
    subscription_id = subscription_id.lower()
    try:
        with arm_auth_context(db=db, token=get_token(db)):
            rows = live_fn()
            rows = enrich_arm_resources_for_type(resource_client, subscription_id, rows, resource_type)
    except AzureAPIError as exc:
        log.warning("arm_live_read_failed", resource_type=resource_type, status=exc.status)
        raise HTTPException(
            status_code=503,
            detail=(
                "Azure inventory is temporarily unavailable. "
                "Run resource sync or retry in a few minutes."
            ),
        ) from exc
    cost_map = resource_cost_map_from_db(db, subscription_id)
    rows = apply_costs_to_resources(rows, cost_map, db=db)
    return paginate_list(rows, limit, offset)


def wrap_azure_source(payload: Any, *, subscription_id: str | None = None) -> dict[str, Any]:
    """Tag a live Azure response for /azure/* routes."""
    if isinstance(payload, dict) and "source" in payload:
        return payload
    body: dict[str, Any] = {"source": "azure"}
    if subscription_id:
        body["subscription_id"] = subscription_id.lower()
    if isinstance(payload, dict) and {"items", "total"} <= set(payload.keys()):
        body.update(payload)
        return body
    if isinstance(payload, list):
        body["count"] = len(payload)
        body["value"] = payload
        return body
    body["value"] = payload
    return body

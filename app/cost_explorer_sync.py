"""
Sync Azure costs for Dashboard, Cost explorer, and billed-resource inventory.

Scope: subscription MTD total, daily trends, service breakdown, resource-type
aggregates, and per-resource (ResourceId) MTD costs for the billed-resources list.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import structlog
from sqlalchemy.orm import Session

from app.cost_utils import aggregate_cost_rows_by_resource_type, aggregate_cost_rows_by_service
from app.http_client import arm_patient_sync
from app.models import CostByResourceTypeSnapshot, CostDailyByServiceSnapshot, CostSnapshot
from app.optimizer.component_map import CANONICAL_TO_COMPONENT
from app.resource_type_map import internal_resource_type

log = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resource_type_display_name(arm_type: str, canonical: str) -> str:
    label = CANONICAL_TO_COMPONENT.get(canonical)
    if label:
        return label
    if "/" in arm_type:
        return arm_type.split("/", 1)[-1].replace("virtualmachines", "Virtual machines").title()
    return arm_type or "Unknown"


def _persist_mtd_by_resource_type_agg(
    db: Session,
    subscription_id: str,
    month: str,
    by_type: dict[str, dict],
) -> int:
    db.query(CostByResourceTypeSnapshot).filter(
        CostByResourceTypeSnapshot.subscription_id == subscription_id,
        CostByResourceTypeSnapshot.month == month,
    ).delete(synchronize_session=False)

    written = 0
    for arm_type, amounts in by_type.items():
        pretax = float(amounts.get("pretax") or 0.0)
        usd = float(amounts.get("usd") or 0.0)
        currency = str(amounts.get("currency") or "CAD")
        canonical = internal_resource_type("", blob_resource_type=arm_type)
        db.add(
            CostByResourceTypeSnapshot(
                id=str(uuid.uuid4()),
                subscription_id=subscription_id,
                arm_resource_type=arm_type,
                canonical_resource_type=canonical,
                month=month,
                cost_usd=usd,
                cost_billing=pretax,
                billing_currency=currency,
            )
        )
        written += 1
    return written


def _replace_daily_subscription_costs(
    db: Session,
    subscription_id: str,
    rows: list[dict],
    *,
    mtd_start: str,
    mtd_end: str,
) -> int:
    """Replace MTD daily subscription totals used by dashboard weekly/daily charts."""
    from app.db_sync import _upsert_daily_service_cost

    sub = subscription_id.lower()
    db.query(CostDailyByServiceSnapshot).filter(
        CostDailyByServiceSnapshot.subscription_id == sub,
        CostDailyByServiceSnapshot.cost_date >= mtd_start,
        CostDailyByServiceSnapshot.cost_date <= mtd_end,
    ).delete(synchronize_session=False)
    db.query(CostSnapshot).filter(
        CostSnapshot.subscription_id == sub,
        CostSnapshot.granularity == "Daily",
        CostSnapshot.cost_date >= mtd_start,
        CostSnapshot.cost_date <= mtd_end,
    ).delete(synchronize_session=False)

    written = 0
    for row in rows:
        cost_date = (row.get("date") or "").strip()[:10]
        if not cost_date:
            continue
        currency = row.get("currency") or "CAD"
        pretax = float(row.get("cost") or 0.0)
        usd = float(row.get("cost_usd") if row.get("cost_usd") is not None else pretax)
        _upsert_daily_service_cost(
            db,
            sub,
            cost_date,
            row.get("service_name") or "__subscription__",
            {"pretax": pretax, "usd": usd, "currency": currency},
        )
        written += 1
    return written


def sync_cost_explorer(subscription_id: str, db: Session, token: str) -> dict:
    """
    Pull Azure Cost Management data for Dashboard, Cost explorer, and billed resources.

    5 API calls per subscription:
      1. subscription MTD total (dedicated summary query - not batched)
      2. MTD by ServiceName (by-service chart)
      3. MTD by ResourceType (resource-type chart)
      4. daily trend
      5. MTD per ResourceId (billed resource list)
    """
    from app.auth import arm_auth_context
    from app.azure_cost import (
        AzureCostClient,
        CostExportReadError,
        daily_subscription_rows_from_response,
    )
    from app.db_sync import (
        _compute_service_changes,
        _previous_service_totals,
        _record_cost_sync_run,
        _replace_mtd_by_resource_agg,
        _replace_mtd_by_service_agg,
        _service_totals_from_service_response,
        sync_resource_costs_from_cost_table,
    )
    from app.billed_resources import reconcile_billed_azure_status
    from app.cost_utils import parse_cost_by_resource_details

    subscription_id = subscription_id.lower()
    today = date.today()
    month = today.strftime("%Y-%m")
    mtd_start = today.replace(day=1).isoformat()
    mtd_end = today.isoformat()

    counts = {
        "cost_by_service": 0,
        "cost_by_resource": 0,
        "cost_by_resource_type": 0,
        "api_rows": 0,
        "daily_rows": 0,
        "mtd_rows": 0,
        "subscription_total_billing": 0.0,
        "breakdown_rows": 0,
        "api_calls": 5,
        "mtd_month": month,
        "mtd_start": mtd_start,
        "mtd_end": mtd_end,
        "changes": None,
        "source": "azure_cost_management",
        "worker": "cost_explorer",
    }

    log.info(
        "cost_explorer_sync.start",
        subscription_id=subscription_id,
        scope="subscription_resource_type_and_billed_resources",
    )

    with arm_auth_context(db=db, token=token):
        client = AzureCostClient(db=db, token=token)
        try:
            with arm_patient_sync():
                subscription_totals_resp = client.query_subscription_totals(subscription_id)
                by_service_resp = client.query_cost_by_service(subscription_id)
                by_type_resp = client.query_cost_mtd_by_resource_type(subscription_id)
                daily_resp = client.query_cost_daily_subscription(subscription_id)
                by_resource_resp = client.query_cost_by_resource(subscription_id)
        except CostExportReadError:
            raise
        except Exception as exc:
            raise CostExportReadError(str(exc)) from exc

    subscription_pretax = float(subscription_totals_resp.get("pretax_total") or 0.0)
    subscription_usd = float(subscription_totals_resp.get("cost_usd_total") or 0.0)
    subscription_currency = subscription_totals_resp.get("billing_currency") or "CAD"
    counts["subscription_total_billing"] = round(subscription_pretax, 2)

    export_rows = daily_subscription_rows_from_response(daily_resp)
    counts["api_rows"] = len(export_rows)
    counts["daily_rows"] = len(export_rows)
    counts["mtd_rows"] = len(export_rows)

    current_services = _service_totals_from_service_response(by_service_resp)
    service_rows = (by_service_resp.get("properties") or {}).get("rows") or []
    type_rows = (by_type_resp.get("properties") or {}).get("rows") or []
    counts["breakdown_rows"] = len(service_rows)
    previous_services, previous_synced_at = _previous_service_totals(db, subscription_id, month)
    service_changes = _compute_service_changes(previous_services, current_services)
    counts["changes"] = {
        "has_previous": previous_synced_at is not None,
        "previous_synced_at": previous_synced_at.isoformat() if previous_synced_at else None,
        "mtd_start": mtd_start,
        "mtd_end": mtd_end,
        "total_billing": counts["subscription_total_billing"],
        "total_delta_billing": round(sum(c["delta_billing"] for c in service_changes), 2),
        "total_delta_usd": round(sum(c["delta_usd"] for c in service_changes), 2),
        "billing_currency": subscription_currency,
        "services": service_changes[:25],
    }

    # FIX: When the API returns no data, record an empty CostSyncRun for audit
    # visibility and log a diagnostic hint, then return instead of silently dropping.
    if not export_rows and not type_rows and subscription_pretax == 0:
        log.warning(
            "cost_explorer_sync.empty_api_response",
            subscription_id=subscription_id,
            hint="Verify the service principal has Cost Management Reader role on this subscription.",
        )
        try:
            _record_cost_sync_run(
                db,
                subscription_id,
                month,
                mtd_start,
                mtd_end,
                current_services,
                service_changes,
                previous_synced_at,
                subscription_total_billing=0.0,
                subscription_total_usd=0.0,
                subscription_currency=subscription_currency,
            )
            db.commit()
        except Exception as rec_exc:
            log.exception(
                "cost_explorer_sync.record_empty_run_failed",
                subscription_id=subscription_id,
                error=str(rec_exc),
            )
        return counts

    # Track which write sections fail for partial-failure visibility
    write_errors: list[str] = []

    try:
        service_agg = aggregate_cost_rows_by_service(by_service_resp)
        counts["cost_by_service"] = _replace_mtd_by_service_agg(
            db, subscription_id, month, service_agg,
        )
    except Exception as exc:
        write_errors.append("cost_by_service")
        log.exception("cost_explorer_sync.mtd_by_service_failed", subscription_id=subscription_id, error=str(exc))

    try:
        type_agg = aggregate_cost_rows_by_resource_type(by_type_resp)
        counts["cost_by_resource_type"] = _persist_mtd_by_resource_type_agg(
            db, subscription_id, month, type_agg,
        )
    except Exception as exc:
        write_errors.append("cost_by_resource_type")
        log.exception("cost_explorer_sync.mtd_by_resource_type_failed", subscription_id=subscription_id, error=str(exc))

    try:
        counts["daily_by_service"] = _replace_daily_subscription_costs(
            db,
            subscription_id,
            export_rows,
            mtd_start=mtd_start,
            mtd_end=mtd_end,
        )
    except Exception as exc:
        write_errors.append("daily_snapshots")
        log.exception("cost_explorer_sync.daily_snapshots_failed", subscription_id=subscription_id, error=str(exc))

    try:
        by_resource = parse_cost_by_resource_details(by_resource_resp)
        counts["cost_by_resource"] = _replace_mtd_by_resource_agg(
            db, subscription_id, month, by_resource,
        )
        if counts["cost_by_resource"] > 0:
            counts["resource_snapshots_updated"] = sync_resource_costs_from_cost_table(
                subscription_id, db, month=month,
            )
        counts["azure_status_reconciled"] = reconcile_billed_azure_status(
            db, subscription_id, month,
        )
    except Exception as exc:
        write_errors.append("cost_by_resource")
        log.exception("cost_explorer_sync.mtd_by_resource_failed", subscription_id=subscription_id, error=str(exc))

    if write_errors:
        log.warning(
            "cost_explorer_sync.partial_write",
            subscription_id=subscription_id,
            failed_sections=write_errors,
        )
        counts["partial_write_errors"] = write_errors

    try:
        _record_cost_sync_run(
            db,
            subscription_id,
            month,
            mtd_start,
            mtd_end,
            current_services,
            service_changes,
            previous_synced_at,
            subscription_total_billing=subscription_pretax,
            subscription_total_usd=subscription_usd,
            subscription_currency=subscription_currency,
        )
    except Exception as exc:
        log.exception("cost_explorer_sync.record_run_failed", subscription_id=subscription_id, error=str(exc))

    db.commit()
    try:
        from app.perf_cache import invalidate_subscription
        invalidate_subscription(subscription_id)
    except Exception as exc:
        log.warning("cost_explorer_sync.cache_invalidate_failed", subscription_id=subscription_id, error=str(exc)[:200])
    log.info("cost_explorer_sync.complete", subscription_id=subscription_id, **counts)
    return counts


def resource_type_display_name(arm_type: str, canonical: str | None = None) -> str:
    canon = canonical or internal_resource_type("", blob_resource_type=arm_type)
    return _resource_type_display_name(arm_type, canon)

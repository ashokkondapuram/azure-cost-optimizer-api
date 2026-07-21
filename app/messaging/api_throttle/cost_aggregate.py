"""Assemble throttled cost API phase results into data pipeline payloads."""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog

from app.messaging.data_collector import SyncDataCollector

log = structlog.get_logger(__name__)


def assemble_cost_data_payload(
    *,
    subscription_id: str,
    phase_results: dict[str, Any],
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Transform raw API responses into sections for data.cost.synced."""
    from app.azure_cost import daily_subscription_rows_from_response
    from app.cost_utils import aggregate_cost_rows_by_resource_type, aggregate_cost_rows_by_service, parse_cost_by_resource_details
    from app.db_sync import _compute_service_changes, _previous_service_totals, _service_totals_from_service_response

    subscription_id = subscription_id.lower()
    month = meta.get("month") or date.today().strftime("%Y-%m")
    mtd_start = meta.get("mtd_start", "")
    mtd_end = meta.get("mtd_end", "")

    subscription_totals_resp = phase_results.get("subscription_totals") or {}
    by_service_resp = phase_results.get("cost_by_service") or {}
    by_type_resp = phase_results.get("cost_by_resource_type") or {}
    daily_resp = phase_results.get("daily_subscription") or {}
    by_resource_resp = phase_results.get("cost_by_resource") or {}

    subscription_pretax = float(subscription_totals_resp.get("pretax_total") or 0.0)
    subscription_usd = float(subscription_totals_resp.get("cost_usd_total") or 0.0)
    subscription_currency = subscription_totals_resp.get("billing_currency") or "CAD"

    export_rows = daily_subscription_rows_from_response(daily_resp)
    current_services = _service_totals_from_service_response(by_service_resp)

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        previous_services, previous_synced_at = _previous_service_totals(db, subscription_id, month)
    finally:
        db.close()

    service_changes = _compute_service_changes(previous_services, current_services)
    counts = {
        "cost_by_service": 0,
        "cost_by_resource": 0,
        "cost_by_resource_type": 0,
        "api_rows": len(export_rows),
        "daily_rows": len(export_rows),
        "mtd_rows": len(export_rows),
        "subscription_total_billing": round(subscription_pretax, 2),
        "source": "azure_cost_management",
        "worker": "cost_explorer",
        "api_throttle": True,
        "mtd_month": month,
        "mtd_start": mtd_start,
        "mtd_end": mtd_end,
        "changes": {
            "has_previous": previous_synced_at is not None,
            "previous_synced_at": previous_synced_at.isoformat() if previous_synced_at else None,
            "mtd_start": mtd_start,
            "mtd_end": mtd_end,
            "total_billing": round(subscription_pretax, 2),
            "total_delta_billing": round(sum(c["delta_billing"] for c in service_changes), 2),
            "total_delta_usd": round(sum(c["delta_usd"] for c in service_changes), 2),
            "billing_currency": subscription_currency,
            "services": service_changes[:25],
        },
    }

    collector = SyncDataCollector(stage="cost")
    collector.add_section(
        "cost_meta",
        {
            "month": month,
            "mtd_start": mtd_start,
            "mtd_end": mtd_end,
            "daily_history_start": meta.get("daily_history_start"),
            "period_responses": {
                key.removeprefix("period_total_"): value
                for key, value in phase_results.items()
                if key.startswith("period_total_")
            },
            "subscription_totals": subscription_totals_resp,
        },
    )
    collector.add_section("cost_by_service", aggregate_cost_rows_by_service(by_service_resp))
    collector.add_section("cost_by_resource_type", aggregate_cost_rows_by_resource_type(by_type_resp))
    collector.add_section("daily_export_rows", export_rows)
    collector.add_section("cost_by_resource", parse_cost_by_resource_details(by_resource_resp))
    collector.add_section(
        "cost_sync_run",
        {
            "mtd_start": mtd_start,
            "mtd_end": mtd_end,
            "current_services": current_services,
            "service_changes": service_changes,
            "previous_synced_at": previous_synced_at.isoformat() if previous_synced_at else None,
            "subscription_total_billing": subscription_pretax,
            "subscription_total_usd": subscription_usd,
            "subscription_currency": subscription_currency,
        },
    )
    counts["cost_by_service"] = len(collector.sections.get("cost_by_service") or {})
    counts["cost_by_resource_type"] = len(collector.sections.get("cost_by_resource_type") or {})
    counts["cost_by_resource"] = len(collector.sections.get("cost_by_resource") or {})
    collector.summary = counts

    log.info(
        "api_throttle.cost_assembled",
        subscription_id=subscription_id,
        phases=len(phase_results),
        **{k: counts[k] for k in ("cost_by_service", "cost_by_resource", "api_rows")},
    )
    return collector.to_payload()

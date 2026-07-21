"""Azure API phase definitions for throttled sync stages."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any


def build_cost_batch_id() -> str:
    return str(uuid.uuid4())


def cost_api_phases(*, subscription_id: str) -> list[dict[str, Any]]:
    """Return ordered cost Management API phases for a subscription sync."""
    from app.cost_timeframes import SYNCED_PERIOD_TIMEFRAMES, azure_timeframe_payload

    today = date.today()
    mtd_start = today.replace(day=1).isoformat()
    mtd_end = today.isoformat()
    daily_history_start = (today - timedelta(days=89)).isoformat()

    phases: list[dict[str, Any]] = [
        {"phase": "subscription_totals", "api_params": {}},
        {"phase": "cost_by_service", "api_params": {}},
        {"phase": "cost_by_resource_type", "api_params": {}},
        {
            "phase": "daily_subscription",
            "api_params": {
                "timeframe": "Custom",
                "from_date": daily_history_start,
                "to_date": mtd_end,
            },
        },
        {"phase": "cost_by_resource", "api_params": {}},
    ]

    for period_tf in SYNCED_PERIOD_TIMEFRAMES:
        if period_tf == "MonthToDate":
            continue
        tf_payload = azure_timeframe_payload(period_tf)
        api_params: dict[str, Any] = {"period_timeframe": period_tf}
        if tf_payload.get("timePeriod"):
            api_params["from_date"] = tf_payload["timePeriod"]["from"]
            api_params["to_date"] = tf_payload["timePeriod"]["to"]
            api_params["timeframe"] = tf_payload.get("timeframe", "Custom")
        else:
            api_params["timeframe"] = tf_payload.get("timeframe", period_tf)
        phases.append({"phase": f"period_total_{period_tf}", "api_params": api_params})

    for index, phase in enumerate(phases):
        phase["phase_index"] = index
        phase["total_phases"] = len(phases)
        phase["subscription_id"] = subscription_id.lower()
        phase["mtd_start"] = mtd_start
        phase["mtd_end"] = mtd_end
        phase["daily_history_start"] = daily_history_start
        phase["month"] = today.strftime("%Y-%m")

    return phases


def metrics_api_phases_stub(*, subscription_id: str, scoped_types: list[str] | None = None) -> list[dict[str, Any]]:
    """Stub phase list for metrics throttling (single batch placeholder)."""
    return [
        {
            "phase": "metrics_batch_stub",
            "phase_index": 0,
            "total_phases": 1,
            "subscription_id": subscription_id.lower(),
            "api_params": {"scoped_types": scoped_types or []},
        }
    ]


def inventory_api_phases_stub(*, subscription_id: str, scoped_types: list[str] | None = None) -> list[dict[str, Any]]:
    """Stub phase list for inventory throttling (single batch placeholder)."""
    return [
        {
            "phase": "inventory_batch_stub",
            "phase_index": 0,
            "total_phases": 1,
            "subscription_id": subscription_id.lower(),
            "api_params": {"scoped_types": scoped_types or []},
        }
    ]
